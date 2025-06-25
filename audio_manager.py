import logging
import os
import wave
from datetime import datetime

import pyaudio

from audio_feedback_manager import AudioFeedbackManager

logger = logging.getLogger(__name__)


class AudioManager:
    """Manages audio input/output streams and recording."""

    def __init__(self, feedback_strategy: str = "api_handled", noise_reduction_type: str = "far_field"):
        self.audio_format = pyaudio.paInt16
        self.channels = 1
        self.rate = 24000  # Will be updated to device native rate
        self.chunk = 1024  # Increased for better speech recognition
        self.native_rate = None  # Will store device's actual sample rate
        self.send_sample_rate = 16000  # Gemini Live API requirement
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
            # Get the default input device's native sample rate
            default_input_device = self.audio.get_default_input_device_info()
            self.native_rate = int(default_input_device['defaultSampleRate'])
            
            logger.info(f"Default input device: {default_input_device['name']}")
            logger.info(f"Native sample rate: {self.native_rate} Hz")
            logger.info(f"Using sample rate: {self.send_sample_rate} Hz for input (Gemini requirement)")
            
            # Use 16kHz for input to match Gemini Live API requirement (like reference code)
            try:
                self.input_stream = self.audio.open(
                    format=self.audio_format,
                    channels=self.channels,
                    rate=self.send_sample_rate,  # 16kHz
                    input=True,
                    frames_per_buffer=self.chunk
                )
                self.native_rate = self.send_sample_rate  # Update native rate to what we're actually using
                logger.info(f"Successfully opened input stream at {self.send_sample_rate}Hz")
            except Exception as e:
                logger.warning(f"Failed to open stream at {self.send_sample_rate}Hz: {e}")
                logger.info(f"Falling back to native rate: {self.native_rate}Hz")
                # Fallback to native rate if 16kHz not supported
                self.input_stream = self.audio.open(
                    format=self.audio_format,
                    channels=self.channels,
                    rate=self.native_rate,
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
            self.mic_record_file.setframerate(self.native_rate)  # Use native rate for recording
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