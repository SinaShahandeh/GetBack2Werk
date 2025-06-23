#!/usr/bin/env python3
"""
Voice Check Agent - A Python app that uses OpenAI's Realtime API or Google's Gemini Live API 
for voice-to-voice communication with periodic check-ins to help users stay productive.
"""

import asyncio
import json
import logging
import os
import threading
import time
from datetime import datetime
from typing import List, Dict, Any
import pyaudio
import wave
import numpy as np
from dotenv import load_dotenv
from system_prompt import system_prompt
from audio_feedback_manager import AudioFeedbackManager
import base64

from api_manager import get_api_manager, ToolHandler
from api_manager_base import APIMessage
from audio_manager import AudioManager
from conversation_manager import ConversationManager

# Load environment variables from .env file
load_dotenv()

# Configure logging - enable debug for conversation history tracking
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class VoiceCheckAgent:
    """Main Voice Check Agent class that orchestrates all components."""
    
    def __init__(self, 
                 check_interval_minutes: int = 5, 
                 feedback_strategy: str = "api_handled", 
                 noise_reduction_type: str = "far_field",
                 api_provider: str = "openai"):
        self.check_interval_minutes = check_interval_minutes
        self.is_running = False
        self.should_disconnect = False
        self.alarm_triggered = False
        self.disconnect_reason = None
        self.api_provider = api_provider.lower()
        
        # Get the appropriate API key
        if self.api_provider == "openai":
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                raise ValueError("OPENAI_API_KEY not found in environment variables")
        elif self.api_provider == "gemini":
            api_key = os.getenv('GEMINI_API_KEY')
            if not api_key:
                raise ValueError("GEMINI_API_KEY not found in environment variables")
        else:
            raise ValueError(f"Unknown API provider: {api_provider}")
        
        # Initialize components
        self.api_manager = get_api_manager(self.api_provider, api_key)
        self.audio_manager = AudioManager(feedback_strategy, noise_reduction_type)
        self.conversation_manager = ConversationManager()
        self.tool_handler = ToolHandler()
        
        # Session state
        self.session_id = None
        
        logger.info(f"Initialized Voice Check Agent with {self.api_provider.upper()} API")
    
    def _get_tools_definition(self) -> List[Dict[str, Any]]:
        """Get the tools definition in OpenAI format."""
        return [
            {
                "type": "function",
                "function": {
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
                }
            },
            {
                "type": "function",
                "function": {
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
            }
        ]
    
    async def configure_session(self):
        """Configure the API session with system prompt and settings."""
        history_prompt = self.conversation_manager.format_history_for_prompt()
        current_system_prompt = system_prompt + history_prompt
        
        # Get tools definition
        tools = self._get_tools_definition()
        
        # Configure the session based on the API provider
        await self.api_manager.configure_session(
            system_prompt=current_system_prompt,
            tools=tools,
            noise_reduction_type=self.audio_manager.noise_reduction_type
        )
        
        logger.info(f"Configured {self.api_provider} session with tools and conversation history")
    
    async def handle_api_messages(self):
        """Handle incoming messages from the API."""
        try:
            async for message in self.api_manager.receive_messages():
                await self.process_api_message(message)
                
                # Check if we should disconnect after processing
                if self.should_disconnect:
                    logger.info("Agent requested disconnection - ending session")
                    break
                    
        except Exception as e:
            logger.error(f"Error handling API messages: {e}")
    
    async def process_api_message(self, message: APIMessage):
        """Process a message from the API."""
        if message.message_type == 'audio':
            # Play audio response
            if message.audio_data:
                self.audio_manager.play_audio_output(message.audio_data)
                
        elif message.message_type == 'text':
            # Log text response and add to conversation history
            if message.content:
                if message.metadata.get('is_assistant'):
                    self.conversation_manager.add_to_history('assistant', message.content)
                    logger.info(f"Assistant: {message.content}")
                elif message.metadata.get('is_user'):
                    self.conversation_manager.add_to_history('user', message.content)
                    logger.info(f"User: {message.content}")
                    
        elif message.message_type == 'tool_call':
            # Handle function calls
            if message.tool_calls:
                logger.info(f"🔧 Received {len(message.tool_calls)} tool calls")
                await self.tool_handler.handle_function_call(message.tool_calls, self)
                
        elif message.message_type == 'error':
            logger.error(f"API error: {message.content}")
            
        elif message.message_type == 'session_update':
            # Handle session updates
            self.session_id = message.metadata.get('session_id')
            if self.session_id:
                logger.info(f"Session updated: {self.session_id}")
    
    async def send_check_in_message(self):
        """Send the periodic check-in message."""
        check_in_text = "check on me"
        
        # For Gemini, the screenshot will be automatically added in send_text
        await self.api_manager.send_text(check_in_text)
        
        logger.info(f"Sent check-in message via {self.api_provider}")
    
    async def send_audio_chunk(self, audio_data: bytes):
        """Send audio data to the API with feedback prevention."""
        if not self.api_manager.is_connected:
            return
        
        # Use audio manager to process audio
        processed_audio = self.audio_manager.process_audio_input(audio_data)
        if processed_audio is None:
            return  # Audio suppressed by feedback manager
        
        await self.api_manager.send_audio(processed_audio)
    
    async def audio_input_loop(self):
        """Continuously capture audio input and send to API."""
        while self.is_running and self.api_manager.is_connected and not self.should_disconnect:
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
            logger.info(f"Starting check-in cycle with {self.api_provider}...")
            
            # Reset flags
            self.should_disconnect = False
            self.alarm_triggered = False
            self.disconnect_reason = None  # Reset disconnect reason for new cycle
            
            # Connect to API
            session_token = await self.api_manager.create_session()
            await self.api_manager.connect(session_token)
            
            # Setup audio
            self.audio_manager.setup_streams()
            
            # Configure session
            await self.configure_session()
            
            # Send check-in message
            await self.send_check_in_message()
            
            # Start audio input and message handling
            audio_task = asyncio.create_task(self.audio_input_loop())
            message_task = asyncio.create_task(self.handle_api_messages())
            
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
            if self.api_manager.is_connected:
                await self.disconnect()
            else:
                logger.info("API already disconnected during check-in")
            
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
        """Disconnect from the API to save costs during idle periods."""
        try:
            # Log the reason for disconnection
            if self.disconnect_reason and self.disconnect_reason.startswith("tool_disconnect:"):
                logger.info(f"🔌 Starting disconnect process - INITIATED BY TOOL: {self.disconnect_reason}")
            else:
                logger.info("🔌 Starting disconnect process...")
            
            # Close audio streams
            self.audio_manager.close_streams()
            
            # Disconnect from API
            await self.api_manager.disconnect()
            
            # Log completion with reason
            if self.disconnect_reason and self.disconnect_reason.startswith("tool_disconnect:"):
                logger.info(f"✅ Disconnected by TOOL USE: {self.disconnect_reason}")
            else:
                logger.info("✅ Successfully disconnected to save costs")
            
        except Exception as e:
            logger.error(f"❌ Error during disconnection: {e}")

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
            logger.info(f"Starting Voice Check Agent with {self.api_provider.upper()} (check interval: {self.check_interval_minutes} minutes)")
            
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
    parser.add_argument('--api',
                       choices=['openai', 'gemini'],
                       default='gemini',
                       help='API provider to use (default: gemini)')
    
    args = parser.parse_args()
    
    agent = VoiceCheckAgent(
        check_interval_minutes=args.interval, 
        feedback_strategy=args.feedback_strategy,
        noise_reduction_type=args.noise_reduction,
        api_provider=args.api
    )
    
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