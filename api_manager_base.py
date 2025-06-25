"""
Abstract base class for API managers.
Defines the common interface for different real-time AI API implementations.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, AsyncIterator, List
import asyncio
import logging

logger = logging.getLogger(__name__)


class RealtimeAPIManager(ABC):
    """Abstract base class for real-time API managers."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.is_connected = False
        
    @abstractmethod
    async def create_session(self) -> str:
        """Create a new session and return session identifier."""
        pass
    
    @abstractmethod
    async def connect(self, session_token: str) -> Any:
        """Connect to the real-time API."""
        pass
    
    @abstractmethod
    async def disconnect(self):
        """Disconnect from the API."""
        pass
    
    @abstractmethod
    async def configure_session(self, system_prompt: str, tools: List[Dict[str, Any]], **kwargs):
        """Configure the session with system prompt and tools."""
        pass
    
    @abstractmethod
    async def send_audio(self, audio_data: bytes, source_sample_rate: int = 24000):
        """Send audio data to the API."""
        pass
    
    @abstractmethod
    async def send_text(self, text: str, image_data: Optional[bytes] = None):
        """Send text (and optionally image) to the API."""
        pass
    
    @abstractmethod
    async def receive_messages(self) -> AsyncIterator[Dict[str, Any]]:
        """Receive messages from the API."""
        pass
    
    @abstractmethod
    async def send_tool_response(self, tool_responses: List[Dict[str, Any]]):
        """Send tool/function responses back to the API."""
        pass


class APIMessage:
    """Standardized message format across different APIs."""
    
    def __init__(self, 
                 message_type: str,
                 content: Optional[str] = None,
                 audio_data: Optional[bytes] = None,
                 tool_calls: Optional[List[Dict[str, Any]]] = None,
                 metadata: Optional[Dict[str, Any]] = None):
        self.message_type = message_type  # 'text', 'audio', 'tool_call', 'error', 'session_update'
        self.content = content
        self.audio_data = audio_data
        self.tool_calls = tool_calls
        self.metadata = metadata or {} 