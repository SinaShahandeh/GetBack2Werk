#!/usr/bin/env python3
"""
Test script for the Voice Check Agent
This demonstrates the connect/disconnect cycle functionality
"""

import asyncio
import sys
from voice_check_agent import VoiceCheckAgent

async def test_agent():
    """Test the voice check agent with a short interval."""
    print("🚀 Testing Voice Check Agent with Smart Disconnect")
    print("=" * 50)
    print("This test will:")
    print("1. Start the agent with a 1-minute check-in interval")
    print("2. Perform an initial check-in")
    print("3. Show how the agent connects/disconnects automatically")
    print("4. Save costs by only connecting during actual check-ins")
    print("=" * 50)
    
    # Create agent with 1-minute interval for testing
    agent = VoiceCheckAgent(check_interval_minutes=1)
    
    try:
        print("\n📱 Starting agent...")
        await agent.start()
    except KeyboardInterrupt:
        print("\n⏹️  Test stopped by user")
    except Exception as e:
        print(f"\n❌ Error during test: {e}")
    finally:
        print("\n💾 Saving conversation history...")
        agent.save_conversation_history("test_conversation.json")
        print("✅ Test completed!")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        print("Voice Check Agent Test")
        print("=" * 30)
        print("This script tests the voice agent with smart connect/disconnect functionality.")
        print("\nUsage:")
        print("  python test_voice_agent.py")
        print("\nWhat happens:")
        print("1. Agent starts and immediately performs a check-in")
        print("2. You can talk to the agent via voice")
        print("3. Agent will decide to disconnect or sound alarm based on your response")
        print("4. If disconnected, agent waits 1 minute then reconnects for next check-in")
        print("\nCost Savings:")
        print("- Only connects to expensive Realtime API during actual check-ins")
        print("- Disconnects immediately after each check-in")
        print("- Can save 95%+ on API costs compared to always-on connection")
        print("\nPress Ctrl+C to stop the test at any time.")
        sys.exit(0)
    
    print("🎯 Voice Check Agent - Smart Disconnect Test")
    print("Run with --help for more information")
    print("Press Ctrl+C to stop\n")
    
    asyncio.run(test_agent()) 