#!/usr/bin/env python3
"""
Simple launcher script for the Voice Check Agent with an easy-to-use interface.
"""

import os
import sys
import asyncio
from dotenv import load_dotenv
from voice_check_agent import VoiceCheckAgent

# Load environment variables from .env file
load_dotenv()

def check_requirements():
    """Check if all requirements are met before starting."""
    errors = []
    
    # Check for OpenAI API key
    if not os.getenv('OPENAI_API_KEY'):
        errors.append("❌ OPENAI_API_KEY environment variable not set")
    
    # Check for required modules
    try:
        import pyaudio
        import websockets
        import aiohttp
        import dotenv
    except ImportError as e:
        errors.append(f"❌ Missing required module: {e.name}")
    
    if errors:
        print("Setup Issues Found:")
        for error in errors:
            print(f"  {error}")
        print("\nPlease fix these issues before running the agent.")
        print("See README.md for detailed setup instructions.")
        return False
    
    print("✅ All requirements met!")
    return True

def get_user_preferences():
    """Get user preferences for the session."""
    print("\n" + "="*50)
    print("🤖 Voice Check Agent Launcher")
    print("="*50)
    
    # Get check interval
    while True:
        try:
            interval_input = input("\n⏰ Check-in interval in minutes (default: 10): ").strip()
            if not interval_input:
                interval = 10
                break
            interval = int(interval_input)
            if interval > 0:
                break
            else:
                print("Please enter a positive number.")
        except ValueError:
            print("Please enter a valid number.")
    
    # Confirm settings
    print(f"\n📋 Session Configuration:")
    print(f"   Check-in interval: {interval} minutes")
    print(f"   System prompt: Loaded from system_prompt.py")
    
    # Final confirmation
    confirm = input("\n🚀 Start the agent? (y/n): ").strip().lower()
    if confirm not in ['y', 'yes']:
        print("Cancelled.")
        return None
    
    return interval

async def main():
    """Main launcher function."""
    print("Voice Check Agent Launcher")
    print("-" * 30)
    
    # Check requirements
    if not check_requirements():
        sys.exit(1)
    
    # Get user preferences
    interval = get_user_preferences()
    if interval is None:
        sys.exit(0)
    
    # Start the agent
    print(f"\n🔊 Starting Voice Check Agent...")
    print(f"💡 Tip: Speak clearly into your microphone")
    print(f"💡 Press Ctrl+C to stop the agent")
    print("-" * 50)
    
    agent = VoiceCheckAgent(check_interval_minutes=interval)
    
    try:
        await agent.start()
    except KeyboardInterrupt:
        print("\n\n👋 Shutting down Voice Check Agent...")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("Check the logs above for more details.")
    finally:
        print("💾 Saving conversation history...")
        agent.save_conversation_history()
        print("✅ Done!")

if __name__ == "__main__":
    # Handle KeyboardInterrupt gracefully
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        sys.exit(0) 