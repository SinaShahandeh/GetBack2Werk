"""
API Manager adapter - selects the appropriate API implementation.
Also contains shared tool handling logic.
"""

import asyncio
import json
import logging
from typing import Dict, Any

from openai_manager import OpenAIRealtimeManager
from gemini_manager import GeminiLiveManager

logger = logging.getLogger(__name__)


def get_api_manager(api_provider: str, api_key: str):
    """Factory function to get the appropriate API manager.
    
    Args:
        api_provider: Either 'openai' or 'gemini'
        api_key: The API key for the provider
        
    Returns:
        Instance of the appropriate API manager
    """
    if api_provider.lower() == 'openai':
        return OpenAIRealtimeManager(api_key)
    elif api_provider.lower() == 'gemini':
        return GeminiLiveManager(api_key)
    else:
        raise ValueError(f"Unknown API provider: {api_provider}")


class ToolHandler:
    """Handles function/tool calls from the AI models."""

    def __init__(self):
        pass

    async def handle_function_call(self, tool_calls: list, voice_agent):
        """Handle function calls from the assistant.
        
        Args:
            tool_calls: List of tool call dictionaries with 'name', 'arguments', and 'call_id'
            voice_agent: The VoiceCheckAgent instance
        """
        results = []
        
        for tool_call in tool_calls:
            function_name = tool_call['name']
            arguments = tool_call['arguments']
            call_id = tool_call.get('call_id', function_name)
            
            print(f"\n{'='*60}")
            print(f"🔧 TOOL CALL DETECTED")
            print(f"Function: {function_name}")
            print(f"Call ID: {call_id}")
            print(f"Arguments: {arguments}")
            print(f"{'='*60}")

            try:
                logger.info(f"🔧 Executing tool: {function_name} with args: {arguments}")

                if function_name == 'Disconnect_Socket':
                    await self._handle_disconnect_tool(arguments, call_id, voice_agent)
                    # For disconnect, we don't add to results since we're disconnecting
                    return  

                elif function_name == 'Sound_Alarm':
                    result = await self._handle_alarm_tool(arguments, call_id, voice_agent)
                    results.append({
                        'name': function_name,
                        'call_id': call_id,
                        'result': result
                    })

                else:
                    print(f"❌ UNKNOWN TOOL CALLED: {function_name}")
                    logger.warning(f"❌ Unknown tool called: {function_name}")
                    results.append({
                        'name': function_name,
                        'call_id': call_id,
                        'result': {"error": f"Unknown function: {function_name}"}
                    })

            except Exception as e:
                print(f"❌ ERROR IN TOOL EXECUTION")
                print(f"Function: {function_name}")
                print(f"Error: {str(e)}")
                logger.error(f"❌ Error handling function call {function_name}: {e}")
                
                results.append({
                    'name': function_name,
                    'call_id': call_id,
                    'result': {"error": str(e)}
                })

            print(f"{'='*60}\n")
        
        # Send all results back to the API
        if results:
            await voice_agent.api_manager.send_tool_response(results)

    async def _handle_disconnect_tool(self, args: dict, call_id: str, voice_agent):
        """Handle disconnect socket tool call."""
        reason = args.get('reason', 'Check-in completed successfully')
        print(f"✅ DISCONNECT TOOL CALLED")
        print(f"Reason: {reason}")
        logger.info(f"✅ Disconnect requested by tool: {reason}")

        voice_agent.should_disconnect = True
        voice_agent.disconnect_reason = f"tool_disconnect: {reason}"

        # Send function result before disconnecting
        await voice_agent.api_manager.send_tool_response([{
            'name': 'Disconnect_Socket',
            'call_id': call_id,
            'result': {
                "status": "success",
                "message": "Socket will be disconnected"
            }
        }])

        # Wait for confirmation before disconnecting
        print(f"🔌 WAITING 10 SECONDS FOR CONFIRMATION BEFORE DISCONNECTING")
        logger.info(f"🔌 Waiting 10 seconds for final message before disconnect")
        await asyncio.sleep(10)
        await voice_agent.disconnect()

    async def _handle_alarm_tool(self, args: dict, call_id: str, voice_agent):
        """Handle sound alarm tool call."""
        reason = args.get('reason', 'User needs attention')
        urgency = args.get('urgency', 'medium')
        print(f"🚨 ALARM TOOL CALLED")
        print(f"Reason: {reason}")
        print(f"Urgency: {urgency}")
        logger.warning(f"🚨 ALARM TRIGGERED: {reason} (Urgency: {urgency})")

        voice_agent.alarm_triggered = True
        self._sound_alarm(reason, urgency)

        return {
            "status": "success",
            "message": f"Alarm sounded: {reason}"
        }

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