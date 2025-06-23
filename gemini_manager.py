"""
Google Gemini Live Streaming API implementation.
"""

import asyncio
import json
import logging
import base64
import io
from typing import Dict, Any, Optional, AsyncIterator, List
from datetime import datetime

from google import genai
from google.genai import types
import mss
from PIL import Image
import numpy as np
import soundfile as sf
import librosa

from api_manager_base import RealtimeAPIManager, APIMessage

logger = logging.getLogger(__name__)


class GeminiLiveManager(RealtimeAPIManager):
    """Manages Google Gemini Live Streaming API connections."""

    def __init__(self, api_key: str):
        super().__init__(api_key)
        self.client = genai.Client(
            http_options={"api_version": "v1beta"},
            api_key=api_key
        )
        self.session = None
        self._session_context = None
        self.model = "gemini-2.5-flash-preview-native-audio-dialog"
        self.audio_input_queue = asyncio.Queue()
        self.message_queue = asyncio.Queue()
        self._receive_task = None

    async def create_session(self) -> str:
        """Create a new Gemini session and return session identifier."""
        # Gemini doesn't require pre-creating sessions like OpenAI
        # We'll create the session when connecting
        logger.info("Preparing to create Gemini Live session")
        return f"gemini_session_{datetime.now().timestamp()}"

    async def connect(self, session_token: str) -> Any:
        """Connect to Gemini Live API."""
        try:
            # We'll establish the actual connection when configuring the session
            self.is_connected = True
            logger.info("Ready to connect to Gemini Live API")
            return True
        except Exception as e:
            logger.error(f"Failed to prepare Gemini connection: {e}")
            raise

    async def disconnect(self):
        """Disconnect from Gemini Live API."""
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            
        if hasattr(self, '_session_context') and self._session_context and self.session:
            # Properly exit the async context manager
            try:
                await self._session_context.__aexit__(None, None, None)
            except Exception as e:
                logger.error(f"Error closing session context: {e}")
            self.session = None
            self._session_context = None
            
        self.is_connected = False
        logger.info("Disconnected from Gemini Live API")

    async def configure_session(self, system_prompt: str, tools: List[Dict[str, Any]], **kwargs):
        """Configure and start the Gemini session."""
        # Convert tools to Gemini format
        gemini_tools = self._convert_tools_to_gemini_format(tools)
        
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Zephyr")
                )
            ),
            tools=gemini_tools,
            system_instruction=types.Content(
                parts=[types.Part(text=system_prompt)],
                role="user"
            )
        )
        
        # Start the session using async context manager
        self._session_context = self.client.aio.live.connect(
            model=self.model,
            config=config
        )
        self.session = await self._session_context.__aenter__()
        
        # Start receiving messages in background
        self._receive_task = asyncio.create_task(self._receive_loop())
        
        logger.info("Configured Gemini Live session")

    async def send_audio(self, audio_data: bytes):
        """Send audio data to Gemini."""
        if not self.session:
            return
            
        try:
            # Gemini expects 16-bit PCM at 16kHz
            # Input is 24kHz, so we need to resample
            audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
            
            # Resample from 24kHz to 16kHz
            audio_16khz = librosa.resample(audio_array, orig_sr=24000, target_sr=16000)
            
            # Convert back to int16
            audio_16khz_int16 = (audio_16khz * 32768).astype(np.int16)
            audio_bytes = audio_16khz_int16.tobytes()
            
            # Use send_realtime_input for audio
            await self.session.send_realtime_input(
                {
                    "media_chunks": [{
                        "mime_type": "audio/pcm;rate=16000",
                        "data": base64.b64encode(audio_bytes).decode('utf-8')
                    }]
                }
            )
        except Exception as e:
            logger.error(f"Error sending audio to Gemini: {e}")

    async def send_text(self, text: str, image_data: Optional[bytes] = None):
        """Send text and optionally image to Gemini."""
        # Add screenshot if requested
        if image_data is None and "check on me" in text.lower():
            logger.info("Taking screenshot for 'check on me' request")
            image_data = await self._take_screenshot()
        
        if image_data:
            # Send image and text together using send_client_content
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            await self.session.send_client_content([
                {
                    "mime_type": "image/png",
                    "data": image_base64
                },
                text
            ])
            logger.info("Sent screenshot and text")
        else:
            # Just send text using send_client_content
            await self.session.send_client_content(text)

    async def receive_messages(self) -> AsyncIterator[APIMessage]:
        """Receive messages from Gemini."""
        while True:
            try:
                message = await self.message_queue.get()
                yield message
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error receiving messages: {e}")
                yield APIMessage(
                    message_type='error',
                    content=str(e)
                )

    async def send_tool_response(self, tool_responses: List[Dict[str, Any]]):
        """Send tool responses to Gemini."""
        for response in tool_responses:
            # Use send_tool_response method
            await self.session.send_tool_response({
                response['name']: response['result']
            })

    async def _receive_loop(self):
        """Background task to receive messages from Gemini."""
        try:
            async for response in self.session.receive():
                # Debug log to see response structure
                logger.debug(f"Received response type: {type(response)}")
                
                # Handle audio data directly from response.data
                # The warnings about inline_data are from the library itself
                if hasattr(response, 'data') and response.data:
                    await self.message_queue.put(APIMessage(
                        message_type='audio',
                        audio_data=response.data,
                        metadata={'sample_rate': 24000}
                    ))
                
                # Handle text responses
                if hasattr(response, 'text') and response.text:
                    await self.message_queue.put(APIMessage(
                        message_type='text',
                        content=response.text,
                        metadata={'is_assistant': True}
                    ))
                
                # Handle server content for function calls and other events
                if hasattr(response, 'server_content') and response.server_content:
                    server_content = response.server_content
                    
                    # Check for model turn with function calls
                    if hasattr(server_content, 'model_turn') and server_content.model_turn:
                        for part in server_content.model_turn.parts:
                            # Handle function calls
                            if hasattr(part, 'function_call') and part.function_call:
                                fc = part.function_call
                                await self.message_queue.put(APIMessage(
                                    message_type='tool_call',
                                    tool_calls=[{
                                        'name': fc.name,
                                        'arguments': fc.args,
                                        'call_id': fc.id if hasattr(fc, 'id') else fc.name
                                    }]
                                ))
                    
                    # Check for turn_complete event
                    if hasattr(server_content, 'turn_complete') and server_content.turn_complete:
                        logger.debug("Turn complete")
                
                # Handle setup_complete event
                if hasattr(response, 'setup_complete') and response.setup_complete:
                    logger.info("Gemini session setup complete")
                
        except asyncio.CancelledError:
            logger.info("Receive loop cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in receive loop: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await self.message_queue.put(APIMessage(
                message_type='error',
                content=str(e)
            ))

    def _convert_tools_to_gemini_format(self, tools: List[Dict[str, Any]]) -> List[types.Tool]:
        """Convert OpenAI-style tools to Gemini format."""
        gemini_tools = []
        
        for tool in tools:
            if tool['type'] == 'function':
                func = tool['function']
                
                # Create function declaration
                func_decl = types.FunctionDeclaration(
                    name=func['name'],
                    description=func['description'],
                    parameters=func.get('parameters', {})
                )
                
                gemini_tools.append(types.Tool(
                    function_declarations=[func_decl]
                ))
        
        return gemini_tools

    async def _take_screenshot(self) -> bytes:
        """Take a screenshot and return as PNG bytes."""
        try:
            with mss.mss() as sct:
                # Capture the primary monitor
                monitor = sct.monitors[1]  # 0 is all monitors, 1 is primary
                screenshot = sct.grab(monitor)
                
                # Convert to PIL Image
                img = Image.frombytes(
                    'RGB',
                    (screenshot.width, screenshot.height),
                    screenshot.rgb
                )
                
                # Resize if too large (Gemini has size limits)
                max_size = (1920, 1080)
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
                
                # Convert to PNG bytes
                img_buffer = io.BytesIO()
                img.save(img_buffer, format='PNG', optimize=True)
                img_buffer.seek(0)
                
                logger.info(f"Screenshot captured: {img.size}")
                return img_buffer.getvalue()
                
        except Exception as e:
            logger.error(f"Error taking screenshot: {e}")
            return None 