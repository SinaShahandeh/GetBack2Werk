#!/usr/bin/env python3
"""
Audio Feedback Manager - Provides various strategies to prevent microphone from picking up speaker output.
"""

import time
import logging
import threading
from typing import Optional, Callable
import numpy as np
import pyaudio
import collections

logger = logging.getLogger(__name__)

class AudioFeedbackManager:
    """Manages audio feedback prevention using various strategies."""
    
    def __init__(self, 
                 strategy: str = "smart_muting",
                 ai_speech_delay: float = 0.5,
                 push_to_talk_key: str = "space"):
        """
        Initialize the feedback manager.
        
        Args:
            strategy: "smart_muting", "push_to_talk", "echo_cancellation", or "api_handled"
            ai_speech_delay: Seconds to wait after AI stops speaking before unmuting
            push_to_talk_key: Key for push-to-talk mode
        """
        self.strategy = strategy
        self.ai_speech_delay = ai_speech_delay
        self.push_to_talk_key = push_to_talk_key
        
        # State tracking
        self.ai_is_speaking = False
        self.microphone_muted = False
        self.last_ai_audio_time = 0
        self.push_to_talk_pressed = False
        self.manual_mute = False
        
        # Echo cancellation
        self.reference_audio_buffer = []
        self.max_buffer_size = 1000  # Keep last 1000 audio chunks for reference
        # Placeholder: minimal attributes kept for compatibility
        self.echo_cancellation_enabled = False  # Real algorithm removed
        
        # Setup keyboard listener for push-to-talk
        if strategy == "push_to_talk":
            self._setup_keyboard_listener()
        
        # Log strategy info
        if strategy == "api_handled":
            logger.info("Using API-handled noise cancellation - no client-side audio processing")
        elif strategy == "smart_muting":
            logger.info("Using smart muting - microphone muted while AI speaks")
        elif strategy == "echo_cancellation":
            logger.info("Using echo cancellation - client-side processing")
        elif strategy == "push_to_talk":
            logger.info("Using push-to-talk - manual control required")
        
    def _setup_keyboard_listener(self):
        """Setup keyboard listener for push-to-talk."""
        try:
            import keyboard
            
            def on_key_event(event):
                if event.name == self.push_to_talk_key:
                    if event.event_type == keyboard.KEY_DOWN:
                        self.push_to_talk_pressed = True
                        logger.info("🎙️ Push-to-talk activated")
                    elif event.event_type == keyboard.KEY_UP:
                        self.push_to_talk_pressed = False
                        logger.info("🔇 Push-to-talk released")
            
            keyboard.hook(on_key_event)
            logger.info(f"Push-to-talk enabled - hold '{self.push_to_talk_key}' to speak")
            
        except ImportError:
            logger.warning("keyboard library not installed. Install with: pip install keyboard")
            logger.warning("Falling back to smart_muting strategy")
            self.strategy = "smart_muting"
    
    def mark_ai_speaking_start(self):
        """Mark that AI has started speaking."""
        self.ai_is_speaking = True
        self.microphone_muted = True
        self.last_ai_audio_time = time.time()
        
        if self.strategy == "smart_muting":
            logger.info("🔇 AI speaking - microphone muted")
    
    def mark_ai_speaking_end(self):
        """Mark that AI has finished speaking."""
        if self.ai_is_speaking:
            self.ai_is_speaking = False
            self.last_ai_audio_time = time.time()
            
            if self.strategy == "smart_muting":
                logger.info("🎙️ AI finished speaking - microphone will unmute shortly")
    
    def add_reference_audio(self, audio_data: bytes):
        """Add AI's audio output as reference for echo cancellation."""
        # Placeholder keeps method for interface but does nothing substantial
        if self.strategy == "echo_cancellation":
            pass  # No-op since algorithm is removed
    
    def should_process_microphone_input(self) -> bool:
        """Determine if microphone input should be processed based on current strategy."""
        current_time = time.time()
        
        if self.manual_mute:
            return False
        
        if self.strategy == "api_handled":
            # Always process - let the OpenAI API handle noise reduction and turn detection
            return True
        
        elif self.strategy == "push_to_talk":
            return self.push_to_talk_pressed
        
        elif self.strategy == "smart_muting":
            # Don't process if AI is currently speaking
            if self.ai_is_speaking:
                return False
            
            # Don't process if not enough time has passed since AI stopped
            if current_time - self.last_ai_audio_time < self.ai_speech_delay:
                return False
            
            # Unmute microphone if enough time has passed
            if self.microphone_muted and current_time - self.last_ai_audio_time >= self.ai_speech_delay:
                self.microphone_muted = False
                logger.info("🎙️ Microphone unmuted")
            
            return not self.microphone_muted
        
        elif self.strategy == "echo_cancellation":
            # Always process but will apply echo cancellation
            return True
        
        return True
    
    def process_microphone_audio(self, audio_data: bytes) -> Optional[bytes]:
        """
        Process microphone audio data based on current strategy.
        Returns None if audio should be suppressed, otherwise returns processed audio.
        """
        if not self.should_process_microphone_input():
            return None
        
        if self.strategy == "api_handled":
            # No client-side processing - let the API handle everything
            return audio_data
        
        elif self.strategy == "echo_cancellation":
            return self._apply_echo_cancellation(audio_data)
        
        return audio_data
    
    def _apply_echo_cancellation(self, audio_data: bytes) -> bytes:
        """Placeholder echo cancellation - pass-through."""
        logger.debug("Echo cancellation placeholder - no processing applied")
        return audio_data
    
    def set_manual_mute(self, muted: bool):
        """Manually mute/unmute the microphone."""
        self.manual_mute = muted
        logger.info(f"🎙️ Microphone {'muted' if muted else 'unmuted'} manually")
    
    def get_status(self) -> dict:
        """Get current status of the feedback manager."""
        return {
            "strategy": self.strategy,
            "ai_is_speaking": self.ai_is_speaking,
            "microphone_muted": self.microphone_muted,
            "manual_mute": self.manual_mute,
            "push_to_talk_pressed": self.push_to_talk_pressed if self.strategy == "push_to_talk" else None,
            "time_since_ai_stopped": time.time() - self.last_ai_audio_time if self.last_ai_audio_time > 0 else 0
        }


class AudioDeviceManager:
    """Helper class to manage audio devices and prevent feedback through device separation."""
    
    @staticmethod
    def list_audio_devices():
        """List available audio devices."""
        audio = pyaudio.PyAudio()
        devices = []
        
        print("\n🎧 Available Audio Devices:")
        print("=" * 50)
        
        for i in range(audio.get_device_count()):
            device_info = audio.get_device_info_by_index(i)
            devices.append(device_info)
            
            device_type = []
            if device_info['maxInputChannels'] > 0:
                device_type.append("INPUT")
            if device_info['maxOutputChannels'] > 0:
                device_type.append("OUTPUT")
            
            print(f"Device {i}: {device_info['name']}")
            print(f"  Type: {' & '.join(device_type)}")
            print(f"  Sample Rate: {device_info['defaultSampleRate']}")
            print(f"  Input Channels: {device_info['maxInputChannels']}")
            print(f"  Output Channels: {device_info['maxOutputChannels']}")
            print()
        
        audio.terminate()
        return devices
    
    @staticmethod
    def get_device_recommendation():
        """Get recommendations for device configuration to prevent feedback."""
        print("\n💡 Recommendations to prevent audio feedback:")
        print("=" * 50)
        print("1. BEST: Use headphones - completely eliminates feedback")
        print("2. GOOD: Use different input/output devices:")
        print("   - Input: External microphone or webcam mic")
        print("   - Output: Built-in speakers or external speakers")
        print("3. OK: Use built-in devices with software feedback prevention")
        print("\n📝 To use different devices:")
        print("   - Note the device numbers from the list above")
        print("   - Modify your audio stream creation to use specific devices")
        print("   - Example: pyaudio.PyAudio().open(input_device_index=1, output_device_index=0)") 