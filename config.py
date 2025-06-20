"""
Configuration file for the Voice Check Agent.
Modify these settings to customize the agent's behavior.
"""

# Audio settings
AUDIO_CONFIG = {
    'sample_rate': 24000,      # Audio sample rate in Hz
    'channels': 1,             # Number of audio channels (1 = mono)
    'chunk_size': 1024,        # Audio buffer chunk size
    'audio_format': 'pcm16'    # Audio format for the API
}

# OpenAI Realtime API settings
REALTIME_CONFIG = {
    'model': 'gpt-4o-realtime-preview-2025-06-03',
    'voice': 'sage',           # Available: alloy, echo, fable, onyx, nova, shimmer, sage
    'temperature': 0.8,        # Response creativity (0.0-1.0)
    'max_tokens': None,        # Max tokens per response (None = no limit)
}

# Voice Activity Detection (VAD) settings
VAD_CONFIG = {
    'threshold': 0.5,          # Voice detection sensitivity (0.0-1.0)
    'prefix_padding_ms': 300,  # Audio to include before speech
    'silence_duration_ms': 500 # Silence duration to end turn
}

# Agent behavior settings
AGENT_CONFIG = {
    'default_check_interval': 10,     # Default check-in interval in minutes
    'max_conversation_history': 50,   # Maximum conversation items to keep
    'enable_transcription': True,     # Enable audio transcription
    'auto_save_history': True,        # Automatically save conversation history
}

# Check-in messages and triggers
CHECK_IN_CONFIG = {
    'trigger_message': 'check on me',  # Message that triggers check-ins
    'initial_delay_seconds': 5,       # Delay before first check-in
}

# Logging configuration
LOGGING_CONFIG = {
    'level': 'INFO',           # Logging level: DEBUG, INFO, WARNING, ERROR
    'format': '%(asctime)s - %(levelname)s - %(message)s',
    'enable_file_logging': False,     # Save logs to file
    'log_file': 'voice_agent.log'     # Log file name
}

# Audio device settings (None = use system default)
AUDIO_DEVICE_CONFIG = {
    'input_device_index': None,   # Microphone device index
    'output_device_index': None,  # Speaker device index
} 