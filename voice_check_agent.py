#!/usr/bin/env python3
"""
Voice Check Agent - A Python app that uses OpenAI's Realtime API for voice-to-voice communication
with periodic check-ins to help users stay productive.
"""

import asyncio
import json
import logging
import os
import threading
import time
from datetime import datetime
from typing import List, Dict, Any
import websockets
import pyaudio
import wave
import numpy as np
from dotenv import load_dotenv
from system_prompt import system_prompt
import openai
from audio_feedback_manager import AudioFeedbackManager
import base64

# Load environment variables from .env file
load_dotenv()

# Configure logging - enable debug for conversation history tracking
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class RealtimeSessionManager:
    """Manages OpenAI Realtime API session creation and WebSocket connection."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")
    
    async def create_session(self) -> str:
        """Create a new OpenAI Realtime session and return the session token."""
        import aiohttp
        
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
                logger.info("Created new Realtime session")
                return data['client_secret']['value']
    
    async def connect_websocket(self, session_token: str):
        """Connect to OpenAI Realtime WebSocket."""
        uri = f"wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2025-06-03"
        
        try:
            # Create headers for authentication
            headers = [
                ('Authorization', f'Bearer {session_token}'),
                ('OpenAI-Beta', 'realtime=v1')
            ]
            
            # Use additional_headers for websockets 11.0+
            websocket = await websockets.connect(uri, additional_headers=headers)
            logger.info("Connected to OpenAI Realtime WebSocket")
            return websocket
            
        except Exception as e:
            logger.error(f"Failed to connect to WebSocket: {e}")
            raise


class AudioManager:
    """Manages audio input/output streams and recording."""
    
    def __init__(self, feedback_strategy: str = "api_handled", noise_reduction_type: str = "far_field"):
        self.audio_format = pyaudio.paInt16
        self.channels = 1
        self.rate = 24000
        self.chunk = 512  # Smaller chunk to let echo canceller adapt faster
        self.audio = pyaudio.PyAudio()
        self.input_stream = None
        self.output_stream = None
        self.mic_record_file = None
        
        # Audio feedback prevention
        self.feedback_manager = AudioFeedbackManager(strategy=feedback_strategy)
        self.noise_reduction_type = noise_reduction_type
        logger.info(f"Audio feedback prevention: {feedback_strategy}")
        if feedback_strategy == "api_handled":
            logger.info(f"Noise reduction type: {noise_reduction_type}")
    
    def setup_streams(self):
        """Setup PyAudio input and output streams."""
        try:
            self.input_stream = self.audio.open(
                format=self.audio_format,
                channels=self.channels,
                rate=self.rate,
                input=True,
                frames_per_buffer=self.chunk
            )
            
            self.output_stream = self.audio.open(
                format=self.audio_format,
                channels=self.channels,
                rate=self.rate,
                output=True,
                frames_per_buffer=self.chunk
            )
            
            # Prepare directory for recordings
            recordings_dir = os.path.join(os.getcwd(), "recordings")
            os.makedirs(recordings_dir, exist_ok=True)

            filename = os.path.join(
                recordings_dir,
                f"user_mic_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav",
            )

            # Open wave file for writing
            self.mic_record_file = wave.open(filename, "wb")
            self.mic_record_file.setnchannels(self.channels)
            self.mic_record_file.setsampwidth(2)  # paInt16 -> 2 bytes
            self.mic_record_file.setframerate(self.rate)
            logger.info(f"Mic audio will be recorded to {filename}")
            logger.info("Audio streams initialized")
            
        except Exception as e:
            logger.error(f"Failed to setup audio streams: {e}")
            raise
    
    def process_audio_input(self, audio_data: bytes) -> bytes:
        """Process audio input through feedback manager and record to file."""
        # Use feedback manager to process audio
        processed_audio = self.feedback_manager.process_microphone_audio(audio_data)
        if processed_audio is None:
            return None  # Audio suppressed by feedback manager
        
        # Save to recording file
        if self.mic_record_file:
            try:
                self.mic_record_file.writeframes(processed_audio)
            except Exception as rec_err:
                logger.warning(f"Failed to write mic audio: {rec_err}")
        
        return processed_audio
    
    def play_audio_output(self, audio_bytes: bytes):
        """Play audio output and track AI speaking state."""
        if self.output_stream:
            self.output_stream.write(audio_bytes)
        
        # Use feedback manager to track AI speaking
        self.feedback_manager.mark_ai_speaking_start()
        self.feedback_manager.add_reference_audio(audio_bytes)
    
    def mark_ai_speaking_end(self):
        """Mark that AI has finished speaking."""
        self.feedback_manager.mark_ai_speaking_end()
    
    def close_streams(self):
        """Close audio streams and recording file."""
        if self.input_stream:
            logger.info("🔌 Closing input audio stream")
            self.input_stream.stop_stream()
            self.input_stream.close()
            self.input_stream = None
        
        if self.output_stream:
            logger.info("🔌 Closing output audio stream")
            self.output_stream.stop_stream()
            self.output_stream.close()
            self.output_stream = None
        
        # Close recording file
        if self.mic_record_file:
            try:
                self.mic_record_file.close()
                logger.info("🎙️ Mic recording file closed")
            except Exception as e:
                logger.warning(f"Error closing mic recording file: {e}")
            finally:
                self.mic_record_file = None
    
    def terminate(self):
        """Terminate audio system."""
        if hasattr(self, 'audio'):
            self.audio.terminate()


class ConversationManager:
    """Manages conversation history and formatting."""
    
    def __init__(self):
        self.conversation_history: List[Dict[str, Any]] = []
    
    def add_to_history(self, role: str, content: str):
        """Add a message to conversation history."""
        self.conversation_history.append({
            'timestamp': datetime.now().isoformat(),
            'role': role,
            'content': content
        })
        
        # Keep only last 500 messages to manage memory
        if len(self.conversation_history) > 500:
            self.conversation_history = self.conversation_history[-500:]
    
    def format_history_for_prompt(self) -> str:
        """Formats the conversation history to be included in the system prompt."""
        if not self.conversation_history:
            return ""
        
        # Let's take the last 10 messages to avoid a very long prompt
        recent_history = self.conversation_history[-10:]
        
        formatted_history = "\n\n--- Previous Conversation Summary ---\n"
        for msg in recent_history:
            # Use title case for roles
            role = msg["role"].title()
            formatted_history += f"{role}: {msg['content']}\n"
        formatted_history += "--- End of Conversation Summary ---\n"
        return formatted_history
    
    def save_to_file(self, filename: str = None):
        """Save conversation history to a JSON file."""
        # Debug logging
        logger.info(f"💾 ConversationManager.save_to_file called with {len(self.conversation_history)} messages")
        
        # Ensure a dedicated directory exists for conversation history files
        histories_dir = os.path.join(os.getcwd(), "conversation_histories")
        os.makedirs(histories_dir, exist_ok=True)

        # Generate default filename when none provided
        if filename is None:
            filename = f"conversation_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        # If a bare filename (no path) is provided, place it in the histories directory
        if not os.path.isabs(filename) and os.path.dirname(filename) == "":
            filename = os.path.join(histories_dir, filename)
        else:
            # If a path is provided, make sure its parent directories exist
            os.makedirs(os.path.dirname(filename), exist_ok=True)

        # Write the conversation history to the JSON file
        with open(filename, 'w') as f:
            json.dump(self.conversation_history, f, indent=2)

        logger.info(f"💾 Conversation history saved to {filename} with {len(self.conversation_history)} messages")


class ToolHandler:
    """Handles function/tool calls from the OpenAI Realtime API."""
    
    def __init__(self, voice_agent):
        self.voice_agent = voice_agent
    
    async def handle_function_call(self, event: Dict[str, Any]):
        """Handle function calls from the assistant."""
        function_name = event.get('name')
        arguments = event.get('arguments', '{}')
        call_id = event.get('call_id')
        
        print(f"\n{'='*60}")
        print(f"🔧 TOOL CALL DETECTED")
        print(f"Function: {function_name}")
        print(f"Call ID: {call_id}")
        print(f"Arguments: {arguments}")
        print(f"{'='*60}")
        
        try:
            args = json.loads(arguments)
            logger.info(f"🔧 Executing tool: {function_name} with args: {args}")
            
            if function_name == 'Disconnect_Socket':
                await self._handle_disconnect_tool(args, call_id)
                return  # Exit to prevent further processing
                
            elif function_name == 'Sound_Alarm':
                await self._handle_alarm_tool(args, call_id)
                
            else:
                print(f"❌ UNKNOWN TOOL CALLED: {function_name}")
                logger.warning(f"❌ Unknown tool called: {function_name}")
                
        except Exception as e:
            print(f"❌ ERROR IN TOOL EXECUTION")
            print(f"Function: {function_name}")
            print(f"Error: {str(e)}")
            logger.error(f"❌ Error handling function call {function_name}: {e}")
            
            # Send error response
            await self._send_tool_error(call_id, str(e))
        
        print(f"{'='*60}\n")
    
    async def _handle_disconnect_tool(self, args: dict, call_id: str):
        """Handle disconnect socket tool call."""
        reason = args.get('reason', 'Check-in completed successfully')
        print(f"✅ DISCONNECT TOOL CALLED")
        print(f"Reason: {reason}")
        logger.info(f"✅ Disconnect requested by tool: {reason}")
        
        self.voice_agent.should_disconnect = True
        self.voice_agent.disconnect_reason = f"tool_disconnect: {reason}"
        
        # Send function call result
        await self._send_tool_result(call_id, {
            "status": "success", 
            "message": "Socket will be disconnected"
        })
        
        # Wait 10 seconds to allow LLM to output final confirmation before disconnecting
        print(f"🔌 WAITING 10 SECONDS FOR LLM CONFIRMATION BEFORE DISCONNECTING")
        logger.info(f"🔌 Waiting 10 seconds for LLM final message before disconnect")
        await asyncio.sleep(10)
        await self.voice_agent.disconnect()
    
    async def _handle_alarm_tool(self, args: dict, call_id: str):
        """Handle sound alarm tool call."""
        reason = args.get('reason', 'User needs attention')
        urgency = args.get('urgency', 'medium')
        print(f"🚨 ALARM TOOL CALLED")
        print(f"Reason: {reason}")
        print(f"Urgency: {urgency}")
        logger.warning(f"🚨 ALARM TRIGGERED: {reason} (Urgency: {urgency})")
        
        self.voice_agent.alarm_triggered = True
        self._sound_alarm(reason, urgency)
        
        # Send function call result
        await self._send_tool_result(call_id, {
            "status": "success", 
            "message": f"Alarm sounded: {reason}"
        })
    
    def _sound_alarm(self, reason: str, urgency: str):
        """Sound an alarm based on urgency level."""
        if urgency == "high":
            print("\n🚨🚨🚨 HIGH PRIORITY ALARM 🚨🚨🚨")
            print(f"REASON: {reason}")
            print("🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨")
        elif urgency == "medium":
            print("\n⚠️⚠️ ATTENTION NEEDED ⚠️⚠️")
            print(f"REASON: {reason}")
            print("⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️")
        else:
            print(f"\n📢 Gentle reminder: {reason}")
    
    async def _send_tool_result(self, call_id: str, result: dict):
        """Send tool execution result."""
        result_event = {
            "type": "conversation.item.create",
            "item": {
                "type": "function_call_output",
                "call_id": call_id,
                "output": json.dumps(result)
            }
        }
        await self.voice_agent.websocket.send(json.dumps(result_event))
        logger.info(f"✅ Tool result sent successfully")
    
    async def _send_tool_error(self, call_id: str, error_message: str):
        """Send tool execution error."""
        error_event = {
            "type": "conversation.item.create",
            "item": {
                "type": "function_call_output",
                "call_id": call_id,
                "output": json.dumps({"status": "error", "message": error_message})
            }
        }
        await self.voice_agent.websocket.send(json.dumps(error_event))


class VoiceCheckAgent:
    """Main Voice Check Agent class that orchestrates all components."""
    
    def __init__(self, check_interval_minutes: int = 5, feedback_strategy: str = "api_handled", noise_reduction_type: str = "far_field"):
        self.check_interval_minutes = check_interval_minutes
        self.is_running = False
        self.should_disconnect = False
        self.alarm_triggered = False
        self.disconnect_reason = None
        
        # Initialize components
        api_key = os.getenv('OPENAI_API_KEY')
        self.session_manager = RealtimeSessionManager(api_key)
        self.audio_manager = AudioManager(feedback_strategy, noise_reduction_type)
        self.conversation_manager = ConversationManager()
        self.tool_handler = ToolHandler(self)
        
        # WebSocket connection
        self.websocket = None
        self.session_id = None
    
    async def configure_session(self):
        """Configure the Realtime session with system prompt and settings."""
        history_prompt = self.conversation_manager.format_history_for_prompt()
        current_system_prompt = system_prompt + history_prompt

        session_update = {
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "instructions": current_system_prompt,
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
                "tools": [
                    {
                        "type": "function",
                        "name": "Disconnect_Socket",
                        "description": "Disconnect the socket after a successful check-in when the user is doing well and being productive.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "reason": {
                                    "type": "string",
                                    "description": "The reason for disconnecting (e.g., 'User is being productive')"
                                }
                            },
                            "required": ["reason"]
                        }
                    },
                    {
                        "type": "function",
                        "name": "Sound_Alarm",
                        "description": "Sound an alarm when the user is wasting time or not being productive.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "reason": {
                                    "type": "string",
                                    "description": "The reason for sounding the alarm (e.g., 'User is wasting time on social media')"
                                },
                                "urgency": {
                                    "type": "string",
                                    "enum": ["low", "medium", "high"],
                                    "description": "The urgency level of the alarm"
                                }
                            },
                            "required": ["reason", "urgency"]
                        }
                    }
                ],
                "tool_choice": "auto",
                "temperature": 0.8
            }
        }
        
        # Add noise reduction if using api_handled strategy
        if self.audio_manager.feedback_manager.strategy == "api_handled" and self.audio_manager.noise_reduction_type != "none":
            session_update["session"]["input_audio_noise_reduction"] = {
                "type": self.audio_manager.noise_reduction_type
            }
            logger.info(f"🔧 Added API noise reduction: {self.audio_manager.noise_reduction_type}")
        
        await self.websocket.send(json.dumps(session_update))
        logger.info("Configured Realtime session with tools and conversation history")
    
    async def connect_websocket(self, session_token: str):
        """Connect to OpenAI Realtime WebSocket."""
        self.websocket = await self.session_manager.connect_websocket(session_token)
        self.session_id = session_token
    
    async def handle_websocket_messages(self):
        """Handle incoming messages from the WebSocket."""
        try:
            async for message in self.websocket:
                # Check if websocket was closed during function execution
                if not self.websocket:
                    logger.info("WebSocket was closed during execution - ending message loop")
                    break
                    
                data = json.loads(message)
                await self.process_realtime_event(data)
                
                # Check if we should disconnect after processing
                if self.should_disconnect:
                    logger.info("Agent requested disconnection - ending session")
                    break
                    
        except websockets.exceptions.ConnectionClosed:
            logger.info("WebSocket connection closed")
        except Exception as e:
            logger.error(f"Error handling WebSocket messages: {e}")
            # If there's an error and websocket is closed, break the loop
            if not self.websocket:
                logger.info("Breaking message loop due to closed websocket")
    
    async def process_realtime_event(self, event: Dict[str, Any]):
        """Process events from the Realtime API."""
        event_type = event.get('type')
        
        if event_type == 'session.created':
            self.session_id = event.get('session', {}).get('id')
            logger.info(f"Session created: {self.session_id}")
            
        elif event_type == 'response.audio.delta':
            # Play audio response and track AI speaking state
            audio_data = event.get('delta', '')
            if audio_data:
                audio_bytes = base64.b64decode(audio_data)
                self.audio_manager.play_audio_output(audio_bytes)
        
        elif event_type == 'response.audio_transcript.done':
            # AI finished speaking AND capture transcript for conversation history
            self.audio_manager.mark_ai_speaking_end()
            transcript = event.get('transcript', '')
            if transcript:
                self.conversation_manager.add_to_history('assistant', f"[Audio] {transcript}")
                logger.info(f"Assistant (Audio): {transcript}")
        
        elif event_type == 'response.done':
            # AI finished response
            self.audio_manager.mark_ai_speaking_end()
        
        elif event_type == 'response.text.done':
            # Log text response and add to conversation history
            text = event.get('text', '')
            if text:
                self.conversation_manager.add_to_history('assistant', text)
                logger.info(f"Assistant: {text}")
        
        elif event_type == 'conversation.item.input_audio_transcription.completed':
            # Log user transcription
            transcript = event.get('transcript', '')
            if transcript:
                self.conversation_manager.add_to_history('user', transcript)
                logger.info(f"User: {transcript}")
                logger.debug(f"💾 Conversation history now has {len(self.conversation_manager.conversation_history)} messages")
        
        # Enhanced logging for function calls
        elif event_type == 'response.function_call_arguments.delta':
            # Log when function call arguments are being streamed
            function_name = event.get('name', 'unknown')
            delta = event.get('delta', '')
            logger.info(f"🔧 Function call arguments delta - {function_name}: {delta}")
            
        elif event_type == 'response.function_call_arguments.done':
            # Log when function call arguments are complete and add to conversation history
            function_name = event.get('name', 'unknown')
            arguments = event.get('arguments', '{}')
            logger.info(f"🔧 Function call arguments complete - {function_name}: {arguments}")
            
            # Add function call to conversation history
            self.conversation_manager.add_to_history('assistant', f"[Function Call] {function_name}({arguments})")
            logger.debug(f"💾 Added function call to conversation history")
            
            # Directly handle the function call now that we have the full arguments
            await self.handle_function_call(event)
        
        elif event_type.startswith('response.function_call'):
            # Catch any other function call related events
            logger.info(f"🔧 Function call event: {event_type} - {event}")
        
        elif event_type == 'error':
            logger.error(f"Realtime API error: {event}")
        
        # Log any unhandled event types for debugging
        else:
            logger.debug(f"Unhandled event type: {event_type}")
            if 'function' in event_type.lower() or 'tool' in event_type.lower():
                logger.warning(f"⚠️ Potentially missed tool/function event: {event_type} - {event}")
    
    async def handle_function_call(self, event: Dict[str, Any]):
        """Handle function calls from the assistant."""
        await self.tool_handler.handle_function_call(event)
    
    async def send_check_in_message(self):
        """Send the periodic check-in message."""
        check_message = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "check on me"}]
            }
        }
        
        await self.websocket.send(json.dumps(check_message))
        
        # Trigger response
        response_create = {
            "type": "response.create"
        }
        await self.websocket.send(json.dumps(response_create))
        
        logger.info("Sent check-in message")
    
    async def send_audio_chunk(self, audio_data: bytes):
        """Send audio data to the Realtime API with feedback prevention."""
        if not self.websocket:
            return
        
        # Use audio manager to process audio
        processed_audio = self.audio_manager.process_audio_input(audio_data)
        if processed_audio is None:
            return  # Audio suppressed by feedback manager
        
        audio_event = {
            "type": "input_audio_buffer.append",
            "audio": base64.b64encode(processed_audio).decode('utf-8')
        }
        
        await self.websocket.send(json.dumps(audio_event))
    
    async def audio_input_loop(self):
        """Continuously capture audio input and send to API."""
        while self.is_running and self.websocket and not self.should_disconnect:
            try:
                if self.audio_manager.input_stream:
                    audio_data = self.audio_manager.input_stream.read(
                        self.audio_manager.chunk, exception_on_overflow=False
                    )
                    await self.send_audio_chunk(audio_data)
                await asyncio.sleep(0.01)  # Small delay to prevent overwhelming the API
                
            except Exception as e:
                logger.error(f"Error in audio input loop: {e}")
                break
    
    async def perform_check_in_cycle(self):
        """Perform a complete check-in cycle: connect -> check-in -> handle response -> disconnect if requested."""
        try:
            logger.info("Starting check-in cycle...")
            
            # Reset flags
            self.should_disconnect = False
            self.alarm_triggered = False
            self.disconnect_reason = None  # Reset disconnect reason for new cycle
            
            # Connect to Realtime API
            session_token = await self.session_manager.create_session()
            await self.connect_websocket(session_token)
            
            # Setup audio
            self.audio_manager.setup_streams()
            
            # Configure session
            await self.configure_session()
            
            # Send check-in message
            await self.send_check_in_message()
            
            # Start audio input and message handling
            audio_task = asyncio.create_task(self.audio_input_loop())
            message_task = asyncio.create_task(self.handle_websocket_messages())
            
            # Wait for either disconnection request or a timeout
            timeout_duration = 120  # 2 minutes max for check-in
            try:
                await asyncio.wait_for(
                    asyncio.gather(audio_task, message_task, return_exceptions=True),
                    timeout=timeout_duration
                )
            except asyncio.TimeoutError:
                logger.warning("Check-in cycle timed out")
            
            # Cancel any remaining tasks
            audio_task.cancel()
            message_task.cancel()
            
            # Always disconnect after check-in (if not already disconnected)
            if self.websocket:
                await self.disconnect()
            else:
                logger.info("Socket already disconnected during check-in")
            
            if self.alarm_triggered:
                logger.info("Alarm was triggered during check-in")
            elif self.should_disconnect:
                logger.info("Check-in completed successfully - agent requested disconnection")
            else:
                logger.info("Check-in cycle completed (timeout or other reason)")
            
        except Exception as e:
            logger.error(f"Error in check-in cycle: {e}")
            await self.disconnect()

    async def disconnect(self):
        """Disconnect from the WebSocket to save costs during idle periods."""
        try:
            # Log the reason for disconnection
            if self.disconnect_reason and self.disconnect_reason.startswith("tool_disconnect:"):
                logger.info(f"🔌 Starting disconnect process - INITIATED BY TOOL: {self.disconnect_reason}")
            else:
                logger.info("🔌 Starting disconnect process...")
            
            # Close audio streams
            self.audio_manager.close_streams()
            
            # Close WebSocket
            if self.websocket:
                try:
                    logger.info("🔌 Closing WebSocket connection")
                    await self.websocket.close()
                    
                    # Log completion with reason
                    if self.disconnect_reason and self.disconnect_reason.startswith("tool_disconnect:"):
                        logger.info(f"✅ Socket closed by TOOL USE: {self.disconnect_reason}")
                    else:
                        logger.info("✅ Successfully disconnected from Realtime API to save costs")
                        
                except Exception as close_error:
                    logger.warning(f"🔌 Error closing websocket (may already be closed): {close_error}")
                finally:
                    self.websocket = None
            else:
                logger.info("🔌 No WebSocket to close")
            
        except Exception as e:
            logger.error(f"❌ Error during disconnection: {e}")
            # Ensure websocket is set to None even if there's an error
            self.websocket = None

    def check_in_timer(self):
        """Timer function that triggers check-ins every specified interval."""
        while self.is_running:
            time.sleep(self.check_interval_minutes * 60)
            if self.is_running:
                # Schedule the check-in cycle in the event loop
                try:
                    # Create new event loop for this thread if needed
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(self.perform_check_in_cycle())
                    loop.close()
                except Exception as e:
                    logger.error(f"Error running check-in cycle: {e}")
    
    async def start(self):
        """Start the voice check agent."""
        try:
            logger.info(f"Starting Voice Check Agent (check interval: {self.check_interval_minutes} minutes)")
            
            self.is_running = True
            
            # Start timer thread for periodic check-ins
            timer_thread = threading.Thread(target=self.check_in_timer, daemon=True)
            timer_thread.start()
            
            # Perform initial check-in immediately
            await self.perform_check_in_cycle()
            
            # Keep the main thread alive
            logger.info("Agent is running. Check-ins will occur automatically.")
            logger.info("Press Ctrl+C to stop the agent.")
            
            # Wait for interruption
            try:
                while self.is_running:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                logger.info("Received interrupt signal")
                
        except Exception as e:
            logger.error(f"Error starting agent: {e}")
        finally:
            await self.stop()
    
    async def stop(self):
        """Stop the voice check agent and cleanup resources."""
        logger.info("Stopping Voice Check Agent")
        self.is_running = False
        
        # Ensure disconnection
        await self.disconnect()
        
        # Terminate audio system
        self.audio_manager.terminate()
        
        logger.info("Voice Check Agent stopped")
    
    def save_conversation_history(self, filename: str = None):
        """Save conversation history to a JSON file."""
        logger.info(f"💾 Saving conversation history with {len(self.conversation_manager.conversation_history)} messages")
        if self.conversation_manager.conversation_history:
            logger.info(f"💾 Sample messages: {self.conversation_manager.conversation_history[:2]}")
        else:
            logger.warning("💾 No conversation history to save!")
        self.conversation_manager.save_to_file(filename)

async def main():
    """Main function to run the Voice Check Agent."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Voice Check Agent')
    parser.add_argument('--interval', type=int, default=5, 
                       help='Check-in interval in minutes (default: 5)')
    parser.add_argument('--feedback-strategy', 
                       choices=['smart_muting', 'push_to_talk', 'echo_cancellation', 'api_handled'], 
                       default='api_handled',
                       help='Audio feedback prevention strategy (default: api_handled)')
    parser.add_argument('--noise-reduction', 
                       choices=['none', 'near_field', 'far_field'],
                       default='far_field',
                       help='Noise reduction type for api_handled strategy (default: far_field)')
    
    args = parser.parse_args()
    
    agent = VoiceCheckAgent(check_interval_minutes=args.interval, 
                           feedback_strategy=args.feedback_strategy,
                           noise_reduction_type=args.noise_reduction)
    
    try:
        await agent.start()
    except KeyboardInterrupt:
        print("\nShutting down...")
        logger.info("💾 Keyboard interrupt - saving conversation history before exit")
    except Exception as e:
        logger.error(f"💾 Error in main: {e} - saving conversation history before exit")
    finally:
        try:
            agent.save_conversation_history()
        except Exception as e:
            logger.error(f"💾 Error saving conversation history: {e}")

if __name__ == "__main__":
    asyncio.run(main())