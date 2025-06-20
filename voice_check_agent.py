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
import mss
import base64
from io import BytesIO
from PIL import Image

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class VoiceCheckAgent:
    def __init__(self, check_interval_minutes: int = 5, feedback_strategy: str = "smart_muting", screenshot: bool = False, noise_reduction_type: str = "none"):
        self.check_interval_minutes = check_interval_minutes
        self.conversation_history: List[Dict[str, Any]] = []
        self.websocket = None
        self.session_id = None
        self.is_running = False
        self.audio_format = pyaudio.paInt16
        self.channels = 1
        self.rate = 24000
        self.chunk = 512  # Smaller chunk to let echo canceller adapt faster
        self.audio = pyaudio.PyAudio()
        self.input_stream = None
        self.output_stream = None
        self.should_disconnect = False
        self.alarm_triggered = False
        self.disconnect_reason = None  # Track the reason for disconnection
        
        # Store noise reduction setting for API-handled strategy
        self.noise_reduction_type = noise_reduction_type
        
        # Audio feedback prevention
        self.feedback_manager = AudioFeedbackManager(strategy=feedback_strategy)
        logger.info(f"Audio feedback prevention: {feedback_strategy}")
        if feedback_strategy == "api_handled":
            logger.info(f"Noise reduction type: {noise_reduction_type}")
        
        # OpenAI API configuration
        self.api_key = os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        
        # Audio recording of user mic (processed data sent to API)
        self.mic_record_file = None  # wave file handle
        
        # Screenshot functionality
        self.screenshot = screenshot
        logger.info(f"Screenshot capture enabled: {self.screenshot}")
    
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
            self.websocket = await websockets.connect(uri, additional_headers=headers)
            logger.info("Connected to OpenAI Realtime WebSocket")
            
            # Configure session
            await self.configure_session()
            
        except Exception as e:
            logger.error(f"Failed to connect to WebSocket: {e}")
            raise
    
    def _format_history_for_prompt(self) -> str:
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
    
    async def configure_session(self):
        """Configure the Realtime session with system prompt and settings."""
        history_prompt = self._format_history_for_prompt()
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
        if self.feedback_manager.strategy == "api_handled" and self.noise_reduction_type != "none":
            session_update["session"]["input_audio_noise_reduction"] = {
                "type": self.noise_reduction_type
            }
            logger.info(f"🔧 Added API noise reduction: {self.noise_reduction_type}")
        
        await self.websocket.send(json.dumps(session_update))
        logger.info("Configured Realtime session with tools and conversation history")
    
    def _resize_image_for_api(self, img: Image.Image, max_file_size_mb: float = 18.0) -> Image.Image:
        """
        Resize image to comply with OpenAI Realtime API limits:
        - Maximum 20MB file size (using 18MB safety margin)
        - Longest dimension ≤ 2048px 
        - Shortest dimension ≤ 768px
        - Maximum effective resolution of 2048x768
        """
        width, height = img.size
        
        # Calculate scale factor to fit within dimension limits
        max_long_dimension = 2048
        max_short_dimension = 768
        
        # Determine which is the longer dimension
        if width >= height:
            # Width is longer dimension
            scale_long = max_long_dimension / width if width > max_long_dimension else 1.0
            scale_short = max_short_dimension / height if height > max_short_dimension else 1.0
        else:
            # Height is longer dimension  
            scale_long = max_long_dimension / height if height > max_long_dimension else 1.0
            scale_short = max_short_dimension / width if width > max_short_dimension else 1.0
        
        # Use the more restrictive scale factor
        scale_factor = min(scale_long, scale_short, 1.0)
        
        # Additional check for effective resolution limit (2048x768 = ~1.57M pixels)
        max_pixels = 2048 * 768
        current_pixels = width * height * (scale_factor ** 2)
        if current_pixels > max_pixels:
            pixel_scale = (max_pixels / (width * height)) ** 0.5
            scale_factor = min(scale_factor, pixel_scale)
        
        # Apply scaling if needed
        if scale_factor < 1.0:
            new_width = int(width * scale_factor)
            new_height = int(height * scale_factor)
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            logger.info(f"📐 Resized image from {width}x{height} to {new_width}x{new_height} (scale: {scale_factor:.2f})")
        
        # Check file size and reduce quality if needed
        quality = 95
        while quality >= 30:
            buffered = BytesIO()
            img.save(buffered, format="PNG", optimize=True)
            size_mb = len(buffered.getvalue()) / (1024 * 1024)
            
            if size_mb <= max_file_size_mb:
                logger.info(f"📐 Final image size: {size_mb:.1f}MB at quality {quality}")
                break
                
            # Reduce dimensions by 10% if size is still too large
            if quality <= 50:
                current_width, current_height = img.size
                new_width = int(current_width * 0.9)
                new_height = int(current_height * 0.9)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                logger.info(f"📐 Further reduced to {new_width}x{new_height} for size constraints")
            
            quality -= 10
        
        return img

    def _capture_and_crop_screenshot_base64(self) -> List[str]:
        """
        Captures the entire virtual screen, applies intelligent resizing for API limits,
        crops it into non-overlapping chunks, saves them locally, and returns them as a list
        of base64 encoded strings optimized for OpenAI Realtime API.
        """
        screenshots_dir = os.path.join(os.getcwd(), "screenshots")
        os.makedirs(screenshots_dir, exist_ok=True)
        
        with mss.mss() as sct:
            sct_img = sct.grab(sct.monitors[0])
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

            # Apply intelligent resizing for API compliance
            img = self._resize_image_for_api(img)
            img_width, img_height = img.size
            
            # Use smaller crop size for better API performance
            crop_width, crop_height = 720, 720  # Reduced from 800x800 for better performance
            
            base64_images = []
            
            # If the image is smaller than the crop size, just use the whole image.
            if img_width <= crop_width and img_height <= crop_height:
                buffered = BytesIO()
                img.save(buffered, format="PNG", optimize=True)
                img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
                base64_images.append(img_base64)
                logger.info("📸 Screenshot is smaller than crop size, using the whole image.")
                return base64_images

            num_crops_x = img_width // crop_width
            num_crops_y = img_height // crop_height

            if num_crops_x * num_crops_y > 4:
                # If we can get more than 4, let's just take 4 from the corners
                coords = [
                    (0, 0),
                    (num_crops_x - 1, 0),
                    (0, num_crops_y - 1),
                    (num_crops_x - 1, num_crops_y - 1),
                ]
            else:
                # Otherwise, take all possible crops
                coords = [(i, j) for i in range(num_crops_x) for j in range(num_crops_y)]

            for i, j in coords:
                left = i * crop_width
                top = j * crop_height
                right = left + crop_width
                bottom = top + crop_height
                
                cropped_img = img.crop((left, top, right, bottom))
                
                filename = os.path.join(
                    screenshots_dir,
                    f"screenshot_crop_{i}_{j}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png",
                )
                cropped_img.save(filename, "PNG", optimize=True)
                logger.info(f"📸 Screenshot crop saved locally to {filename}")

                buffered = BytesIO()
                cropped_img.save(buffered, format="PNG", optimize=True)
                img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
                base64_images.append(img_base64)

            return base64_images

    def setup_audio_streams(self):
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
    
    async def send_audio_chunk(self, audio_data: bytes):
        """Send audio data to the Realtime API with feedback prevention."""
        if not self.websocket:
            return
        
        # Use feedback manager to process audio
        processed_audio = self.feedback_manager.process_microphone_audio(audio_data)
        if processed_audio is None:
            return  # Audio suppressed by feedback manager
        
        # Save to recording file
        if self.mic_record_file:
            try:
                self.mic_record_file.writeframes(processed_audio)
            except Exception as rec_err:
                logger.warning(f"Failed to write mic audio: {rec_err}")
        
        import base64
        
        audio_event = {
            "type": "input_audio_buffer.append",
            "audio": base64.b64encode(processed_audio).decode('utf-8')
        }
        
        await self.websocket.send(json.dumps(audio_event))
    
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
                import base64
                audio_bytes = base64.b64decode(audio_data)
                if self.output_stream:
                    self.output_stream.write(audio_bytes)
                
                # Use feedback manager to track AI speaking
                self.feedback_manager.mark_ai_speaking_start()
                self.feedback_manager.add_reference_audio(audio_bytes)
                
        elif event_type == 'response.audio_transcript.done' or event_type == 'response.done':
            # AI finished speaking
            self.feedback_manager.mark_ai_speaking_end()
        
        elif event_type == 'response.text.done':
            # Log text response and add to conversation history
            text = event.get('text', '')
            if text:
                self.add_to_history('assistant', text)
                logger.info(f"Assistant: {text}")
        
        elif event_type == 'conversation.item.input_audio_transcription.completed':
            # Log user transcription
            transcript = event.get('transcript', '')
            if transcript:
                self.add_to_history('user', transcript)
                logger.info(f"User: {transcript}")
        
        # Enhanced logging for function calls
        elif event_type == 'response.function_call_arguments.delta':
            # Log when function call arguments are being streamed
            function_name = event.get('name', 'unknown')
            delta = event.get('delta', '')
            logger.info(f"🔧 Function call arguments delta - {function_name}: {delta}")
            
        elif event_type == 'response.function_call_arguments.done':
            # Log when function call arguments are complete
            function_name = event.get('name', 'unknown')
            arguments = event.get('arguments', '{}')
            logger.info(f"🔧 Function call arguments complete - {function_name}: {arguments}")
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
                reason = args.get('reason', 'Check-in completed successfully')
                print(f"✅ DISCONNECT TOOL CALLED")
                print(f"Reason: {reason}")
                logger.info(f"✅ Disconnect requested by tool: {reason}")
                self.should_disconnect = True
                self.disconnect_reason = f"tool_disconnect: {reason}"  # Mark as tool-initiated disconnect
                
                # Send function call result
                result_event = {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": json.dumps({"status": "success", "message": "Socket will be disconnected"})
                    }
                }
                await self.websocket.send(json.dumps(result_event))
                logger.info(f"✅ Disconnect tool result sent successfully")
                
                # Wait 10 seconds to allow LLM to output final confirmation before disconnecting
                print(f"🔌 WAITING 10 SECONDS FOR LLM CONFIRMATION BEFORE DISCONNECTING")
                logger.info(f"🔌 Waiting 10 seconds for LLM final message before disconnect")
                await asyncio.sleep(10)  # Allow time for LLM to send final confirmation
                await self.disconnect()
                return  # Exit the function to prevent further processing
                
            elif function_name == 'Sound_Alarm':
                reason = args.get('reason', 'User needs attention')
                urgency = args.get('urgency', 'medium')
                print(f"🚨 ALARM TOOL CALLED")
                print(f"Reason: {reason}")
                print(f"Urgency: {urgency}")
                logger.warning(f"🚨 ALARM TRIGGERED: {reason} (Urgency: {urgency})")
                self.alarm_triggered = True
                self.sound_alarm(reason, urgency)
                
                # Send function call result
                result_event = {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": json.dumps({"status": "success", "message": f"Alarm sounded: {reason}"})
                    }
                }
                await self.websocket.send(json.dumps(result_event))
                logger.info(f"🚨 Alarm tool result sent successfully")
                
            else:
                print(f"❌ UNKNOWN TOOL CALLED: {function_name}")
                logger.warning(f"❌ Unknown tool called: {function_name}")
                
        except Exception as e:
            print(f"❌ ERROR IN TOOL EXECUTION")
            print(f"Function: {function_name}")
            print(f"Error: {str(e)}")
            logger.error(f"❌ Error handling function call {function_name}: {e}")
            
            # Send error response
            error_event = {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps({"status": "error", "message": str(e)})
                }
            }
            await self.websocket.send(json.dumps(error_event))
        
        print(f"{'='*60}\n")
    
    def sound_alarm(self, reason: str, urgency: str):
        """Sound an alarm based on urgency level."""
        # You can implement different alarm sounds/notifications here
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
    
    async def send_check_in_message(self, screenshot_base64_list: List[str] | None = None):
        """Send the periodic check-in message, with an optional screenshot."""
        content = [{"type": "input_text", "text": "check on me"}]
        if screenshot_base64_list:
            for b64_image in screenshot_base64_list:
                # Format image properly for OpenAI Realtime API
                content.append({
                    "type": "input_image",
                    "image": f"data:image/png;base64,{b64_image}"
                })
            logger.info(f"📸 Attaching {len(screenshot_base64_list)} screenshot crops to check-in message.")

        check_message = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": content
            }
        }
        
        await self.websocket.send(json.dumps(check_message))
        
        # Trigger response
        response_create = {
            "type": "response.create"
        }
        await self.websocket.send(json.dumps(response_create))
        
        logger.info("Sent check-in message")
    
    async def audio_input_loop(self):
        """Continuously capture audio input and send to API."""
        while self.is_running and self.websocket and not self.should_disconnect:
            try:
                if self.input_stream:
                    audio_data = self.input_stream.read(self.chunk, exception_on_overflow=False)
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
            
            # Capture screenshot if enabled
            screenshot_base64_list = None
            if self.screenshot:
                logger.info("📸 Capturing and cropping screenshot...")
                try:
                    screenshot_base64_list = self._capture_and_crop_screenshot_base64()
                    if screenshot_base64_list:
                        logger.info(f"📸 {len(screenshot_base64_list)} screenshot crops captured successfully.")
                    else:
                        logger.info("📸 No screenshot crops were generated.")
                except Exception as e:
                    logger.error(f"Failed to capture and crop screenshot: {e}")

            # Connect to Realtime API
            session_token = await self.create_session()
            await self.connect_websocket(session_token)
            
            # Setup audio
            self.setup_audio_streams()
            
            # Send check-in message
            await self.send_check_in_message(screenshot_base64_list=screenshot_base64_list)
            
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
        if hasattr(self, 'audio'):
            self.audio.terminate()
        
        logger.info("Voice Check Agent stopped")
    
    def save_conversation_history(self, filename: str = None):
        """Save conversation history to a JSON file."""
        if filename is None:
            filename = f"conversation_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(filename, 'w') as f:
            json.dump(self.conversation_history, f, indent=2)
        
        logger.info(f"Conversation history saved to {filename}")

async def main():
    """Main function to run the Voice Check Agent."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Voice Check Agent')
    parser.add_argument('--interval', type=int, default=5, 
                       help='Check-in interval in minutes (default: 5)')
    parser.add_argument('--feedback-strategy', 
                       choices=['smart_muting', 'push_to_talk', 'echo_cancellation', 'api_handled'], 
                       default='smart_muting',
                       help='Audio feedback prevention strategy (default: smart_muting)')
    parser.add_argument('--noise-reduction', 
                       choices=['none', 'near_field', 'far_field'],
                       default='none',
                       help='Noise reduction type for api_handled strategy (default: none)')
    parser.add_argument('--no-screenshot', action='store_true', default=False,
                          help='Disable screenshot capture at the start of each check-in')
    
    args = parser.parse_args()
    
    # Validate noise reduction option
    if args.feedback_strategy != 'api_handled' and args.noise_reduction != 'none':
        logger.warning("⚠️ Noise reduction option is only used with api_handled strategy. Ignoring.")
        args.noise_reduction = 'none'
    
    agent = VoiceCheckAgent(check_interval_minutes=args.interval, 
                           feedback_strategy=args.feedback_strategy,
                           screenshot=not args.no_screenshot,
                           noise_reduction_type=args.noise_reduction)
    
    try:
        await agent.start()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        agent.save_conversation_history()

if __name__ == "__main__":
    asyncio.run(main())