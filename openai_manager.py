"""
OpenAI Realtime API implementation.
"""

import asyncio
import json
import logging
import base64
from typing import Dict, Any, Optional, AsyncIterator, List

import aiohttp
import websockets

from api_manager_base import RealtimeAPIManager, APIMessage

logger = logging.getLogger(__name__)


class OpenAIRealtimeManager(RealtimeAPIManager):
    """Manages OpenAI Realtime API session creation and WebSocket connection."""

    def __init__(self, api_key: str):
        super().__init__(api_key)
        self.websocket = None
        self.session_token = None

    async def create_session(self) -> str:
        """Create a new OpenAI Realtime session and return the session token."""
        async with aiohttp.ClientSession() as session:
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }

            payload = {
                'model': 'gpt-4o-realtime-preview-2025-06-03',
                'voice': 'sage'
            }

            async with session.post(
                'https://api.openai.com/v1/realtime/sessions',
                headers=headers,
                json=payload
            ) as response:
                if response.status != 200:
                    raise Exception(f"Failed to create session: {response.status}")

                data = await response.json()
                logger.info("Created new OpenAI Realtime session")
                self.session_token = data['client_secret']['value']
                return self.session_token

    async def connect(self, session_token: str) -> websockets.WebSocketClientProtocol:
        """Connect to OpenAI Realtime WebSocket."""
        uri = f"wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2025-06-03"

        try:
            # Create headers for authentication
            headers = [
                ('Authorization', f'Bearer {session_token}'),
                ('OpenAI-Beta', 'realtime=v1')
            ]

            # Use additional_headers for websockets 11.0+
            self.websocket = await websockets.connect(uri, additional_headers=headers)
            self.is_connected = True
            logger.info("Connected to OpenAI Realtime WebSocket")
            return self.websocket

        except Exception as e:
            logger.error(f"Failed to connect to WebSocket: {e}")
            raise

    async def disconnect(self):
        """Disconnect from the WebSocket."""
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
            self.is_connected = False
            logger.info("Disconnected from OpenAI WebSocket")

    async def configure_session(self, system_prompt: str, tools: List[Dict[str, Any]], **kwargs):
        """Configure the OpenAI session with system prompt and tools."""
        session_update = {
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "instructions": system_prompt,
                "voice": "sage",
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {
                    "model": "whisper-1"
                },
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 500
                },
                "tools": tools,
                "tool_choice": "auto",
                "temperature": 0.8
            }
        }
        
        await self.websocket.send(json.dumps(session_update))
        logger.info("Configured OpenAI Realtime session")

    async def send_audio(self, audio_data: bytes, source_sample_rate: int = 24000):
        """Send audio data to OpenAI."""
        if not self.websocket:
            return
            
        # OpenAI expects 24kHz PCM16, so we may need to resample if input is different
        # For now, we'll assume the audio is already in the correct format
        audio_event = {
            "type": "input_audio_buffer.append",
            "audio": base64.b64encode(audio_data).decode('utf-8')
        }
        
        await self.websocket.send(json.dumps(audio_event))

    async def send_text(self, text: str, image_data: Optional[bytes] = None):
        """Send text to OpenAI. Note: OpenAI Realtime API doesn't support images."""
        if image_data:
            logger.warning("OpenAI Realtime API doesn't support image input")
            
        message = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}]
            }
        }
        
        await self.websocket.send(json.dumps(message))
        
        # Trigger response
        response_create = {
            "type": "response.create"
        }
        await self.websocket.send(json.dumps(response_create))

    async def receive_messages(self) -> AsyncIterator[APIMessage]:
        """Receive and convert OpenAI messages to standardized format."""
        async for message in self.websocket:
            data = json.loads(message)
            api_message = self._convert_openai_message(data)
            if api_message:
                yield api_message

    async def send_tool_response(self, tool_responses: List[Dict[str, Any]]):
        """Send tool responses to OpenAI."""
        for response in tool_responses:
            result_event = {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": response['call_id'],
                    "output": json.dumps(response['result'])
                }
            }
            await self.websocket.send(json.dumps(result_event))

    def _convert_openai_message(self, event: Dict[str, Any]) -> Optional[APIMessage]:
        """Convert OpenAI event to standardized APIMessage."""
        event_type = event.get('type')
        
        if event_type == 'response.audio.delta':
            audio_data = event.get('delta', '')
            if audio_data:
                return APIMessage(
                    message_type='audio',
                    audio_data=base64.b64decode(audio_data),
                    metadata={'event_type': event_type}
                )
                
        elif event_type == 'response.audio_transcript.done':
            transcript = event.get('transcript', '')
            if transcript:
                return APIMessage(
                    message_type='text',
                    content=transcript,
                    metadata={'event_type': event_type, 'is_assistant': True}
                )
                
        elif event_type == 'conversation.item.input_audio_transcription.completed':
            transcript = event.get('transcript', '')
            if transcript:
                return APIMessage(
                    message_type='text',
                    content=transcript,
                    metadata={'event_type': event_type, 'is_user': True}
                )
                
        elif event_type == 'response.function_call_arguments.done':
            function_name = event.get('name')
            arguments = event.get('arguments', '{}')
            call_id = event.get('call_id')
            
            return APIMessage(
                message_type='tool_call',
                tool_calls=[{
                    'name': function_name,
                    'arguments': json.loads(arguments),
                    'call_id': call_id
                }],
                metadata={'event_type': event_type}
            )
            
        elif event_type == 'error':
            return APIMessage(
                message_type='error',
                content=str(event),
                metadata={'event_type': event_type}
            )
            
        elif event_type == 'session.created':
            return APIMessage(
                message_type='session_update',
                metadata={'event_type': event_type, 'session_id': event.get('session', {}).get('id')}
            )
            
        return None 