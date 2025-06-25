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

    async def send_audio(self, audio_data: bytes, source_sample_rate: int = 24000):
        """Send audio data to Gemini."""
        if not self.session:
            return
            
        try:
            # Gemini expects 16-bit PCM at 16kHz
            # Input could be at various sample rates (24kHz, 48kHz), so we need to resample
            audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
            
            # Check if audio contains actual signal (not silence)
            audio_rms = np.sqrt(np.mean(audio_array ** 2))
            if audio_rms < 0.001:  # Very quiet audio, might be silence
                logger.debug(f"Audio chunk RMS: {audio_rms:.6f} (very quiet, skipping)")
                return  # Skip sending silent audio
            else:
                logger.debug(f"Audio chunk RMS: {audio_rms:.6f} (has signal)")
            
            # Only resample if needed
            if source_sample_rate != 16000:
                logger.debug(f"Resampling audio from {source_sample_rate}Hz to 16kHz")
                audio_16khz = librosa.resample(audio_array, orig_sr=source_sample_rate, target_sr=16000)
            else:
                audio_16khz = audio_array
            
            # Convert back to int16
            audio_16khz_int16 = (audio_16khz * 32768).astype(np.int16)
            audio_bytes = audio_16khz_int16.tobytes()
            
            # Send audio using session.send() with raw data format (like reference code)
            audio_msg = {"data": audio_bytes, "mime_type": "audio/pcm"}
            await self.session.send(input=audio_msg)
            logger.debug(f"Sent {len(audio_bytes)} bytes of audio to Gemini")
        except Exception as e:
            if "keepalive ping timeout" in str(e) or "ConnectionClosedError" in str(e):
                logger.warning(f"WebSocket connection lost: {e}")
                # Don't spam logs with traceback for expected connection issues
                return
            else:
                logger.error(f"Error sending audio to Gemini: {e}")
                import traceback
                logger.error(traceback.format_exc())
                # Raise KeyboardInterrupt to stop the agent for debugging
                raise KeyboardInterrupt(f"API Error in send_audio: {e}")

    async def send_text(self, text: str, image_data: Optional[bytes] = None):
        """Send text and optionally image to Gemini."""
        # Add screenshot if requested
        if image_data is None and "check on me" in text.lower():
            logger.info("Taking screenshot for 'check on me' request")
            image_data = await self._take_screenshot()
        
        try:
            # Send text first
            logger.info(f"Sending text: {text}")
            await self.session.send_client_content(
                turns=[{
                    "role": "user", 
                    "parts": [{"text": text}]
                }],
                turn_complete=False  # Don't complete turn yet if we have image
            )
            logger.info("Sent text message successfully")
            
            # Send image using send_realtime_input if we have one
            if image_data:
                logger.info("Sending screenshot using send_realtime_input")
                # Convert to PIL Image for send_realtime_input
                img = Image.open(io.BytesIO(image_data))
                await self.session.send_realtime_input(media=img)
                logger.info("Sent screenshot successfully")
            
            # Complete the turn
            await self.session.send_client_content(
                turns=[{
                    "role": "user", 
                    "parts": [{"text": ""}]  # Empty text to complete turn
                }],
                turn_complete=True
            )
            
        except Exception as e:
            logger.error(f"Error sending text to Gemini: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # Raise KeyboardInterrupt to stop the agent for debugging
            raise KeyboardInterrupt(f"API Error in send_text: {e}")

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
                # Raise KeyboardInterrupt to stop the agent for debugging
                raise KeyboardInterrupt(f"API Error in receive_messages: {e}")

    async def send_tool_response(self, tool_responses: List[Dict[str, Any]]):
        """Send tool responses to Gemini."""
        if not self.session:
            logger.warning("🔧 Cannot send tool response - no active session")
            return
            
        try:
            logger.info(f"🔧 SENDING TOOL RESPONSES TO GEMINI: {len(tool_responses)} responses")
            
            # Convert to proper Gemini format
            function_responses = []
            for response in tool_responses:
                logger.info(f"🔧 Processing tool response: {response['name']} (call_id: {response.get('call_id', 'none')})")
                
                # Try a simpler format - just match the ID and provide the response
                function_response = {
                    "id": response.get('call_id', response['name']),
                    "name": response['name'],
                    "response": response['result']
                }
                function_responses.append(function_response)
                logger.info(f"🔧 Converted to Gemini format: {function_response}")
            
            # Try the format without wrapping in functionResponses
            logger.info(f"🔧 SENDING INDIVIDUAL FUNCTION RESPONSES")
            for func_response in function_responses:
                try:
                    logger.info(f"🔧 Sending individual response: {json.dumps(func_response, indent=2)}")
                    await self.session.send_tool_response(func_response)
                    logger.info("🔧 ✅ Individual response sent successfully")
                except Exception as e:
                    logger.error(f"🔧 ❌ Error sending individual response: {e}")
                    # Try alternative format wrapped in functionResponses
                    logger.info("🔧 Trying wrapped format...")
                    gemini_response = {"functionResponses": [func_response]}
                    await self.session.send_tool_response(gemini_response)
                    logger.info("🔧 ✅ Wrapped response sent successfully")
            logger.info("🔧 ✅ TOOL RESPONSE SENT TO GEMINI SUCCESSFULLY")
            
        except Exception as e:
            logger.error(f"🔧 ❌ ERROR SENDING TOOL RESPONSE TO GEMINI: {e}")
            import traceback
            logger.error(f"🔧 ❌ FULL TRACEBACK: {traceback.format_exc()}")
            # Raise KeyboardInterrupt to stop the agent for debugging
            raise KeyboardInterrupt(f"API Error in send_tool_response: {e}")

    async def _receive_loop(self):
        """Background task to receive messages from Gemini."""
        try:
            while True:
                # Get the next turn from the session (like reference code)
                turn = self.session.receive()
                async for response in turn:
                    # Debug log to see response structure
                    logger.debug(f"Received response type: {type(response)}")
                    
                    # Handle audio data directly from response.data
                    if hasattr(response, 'data') and response.data:
                        logger.info(f"Received audio data: {len(response.data)} bytes")
                        await self.message_queue.put(APIMessage(
                            message_type='audio',
                            audio_data=response.data,
                            metadata={'sample_rate': 24000}
                        ))
                    
                    # Handle text responses
                    if hasattr(response, 'text') and response.text:
                        logger.info(f"Received text: {response.text}")
                        await self.message_queue.put(APIMessage(
                            message_type='text',
                            content=response.text,
                            metadata={'is_assistant': True}
                        ))
                        print(response.text, end="")  # Also print to console like reference
                    
                    # Handle server content for function calls and other events
                    if hasattr(response, 'server_content') and response.server_content:
                        server_content = response.server_content
                        
                        # Check for model turn with function calls
                        if hasattr(server_content, 'model_turn') and server_content.model_turn:
                            logger.info(f"🔧 Model turn detected with {len(server_content.model_turn.parts)} parts")
                            for part in server_content.model_turn.parts:
                                # Handle function calls
                                if hasattr(part, 'function_call') and part.function_call:
                                    fc = part.function_call
                                    logger.info(f"🔧 FUNCTION CALL DETECTED IN GEMINI:")
                                    logger.info(f"🔧   Name: {fc.name}")
                                    logger.info(f"🔧   Args: {fc.args}")
                                    logger.info(f"🔧   ID: {getattr(fc, 'id', 'no_id')}")
                                    
                                    tool_call = {
                                        'name': fc.name,
                                        'arguments': fc.args,
                                        'call_id': fc.id if hasattr(fc, 'id') else fc.name
                                    }
                                    logger.info(f"🔧 SENDING TOOL CALL TO HANDLER: {tool_call}")
                                    
                                    await self.message_queue.put(APIMessage(
                                        message_type='tool_call',
                                        tool_calls=[tool_call]
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
            if "keepalive ping timeout" in str(e) or "ConnectionClosedError" in str(e):
                logger.warning(f"WebSocket connection lost in receive loop: {e}")
                # Signal that connection is lost
                await self.message_queue.put(APIMessage(
                    message_type='error',
                    content="Connection lost - WebSocket timeout"
                ))
            else:
                logger.error(f"Error in receive loop: {e}")
                import traceback
                logger.error(traceback.format_exc())
                # Raise KeyboardInterrupt to stop the agent for debugging
                raise KeyboardInterrupt(f"API Error in _receive_loop: {e}")

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
                screenshot_bytes = img_buffer.getvalue()
                logger.debug(f"Screenshot bytes length: {len(screenshot_bytes)}, type: {type(screenshot_bytes)}")
                return screenshot_bytes
                
        except Exception as e:
            logger.error(f"Error taking screenshot: {e}")
            return None 