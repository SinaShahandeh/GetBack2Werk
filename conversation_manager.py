import json
import logging
import os
from datetime import datetime
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


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