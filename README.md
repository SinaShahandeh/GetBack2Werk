# Voice Check Agent with Smart Disconnect

A Python application that uses OpenAI's Realtime API or Google's Gemini Live API for voice-to-voice communication with periodic check-ins to help users stay productive. **Now with smart disconnect functionality to save 95%+ on API costs!**

## 🚀 Key Features

- **Multi-API Support**: Choose between OpenAI's Realtime API or Google's Gemini Live API
- **Smart Cost Management**: Only connects to the expensive APIs during actual check-ins
- **Automatic Disconnect**: Agent disconnects after successful check-ins to save costs
- **Screenshot Support (Gemini)**: Automatically captures screenshots during check-ins when using Gemini
- **Productivity Monitoring**: Regular voice check-ins to keep users on track
- **Alarm System**: Sounds alerts when users are wasting time
- **Voice Interaction**: Natural voice conversations using advanced AI models
- **Modular Architecture**: Clean separation of concerns with dedicated modules for each API
- **Advanced Audio Management**: Multiple feedback prevention strategies and noise reduction options
- **Conversation History**: Automatic tracking and saving of all conversations

## 🎯 API Comparison

| Feature | OpenAI Realtime API | Google Gemini Live API |
|---------|-------------------|----------------------|
| **Voice Quality** | Natural, multiple voices | Natural, 30+ voices |
| **Languages** | Multiple | 24+ languages |
| **Screenshot Support** | ❌ | ✅ (automatic) |
| **Audio Format** | 24kHz PCM16 | 16kHz input, 24kHz output |
| **Connection Type** | WebSocket | Google SDK |
| **Cost** | Per-minute pricing | Per-token pricing |

## 💰 Cost Savings

The smart disconnect system dramatically reduces API costs:

| Approach | Cost per Day (24h) | Cost per Month | Description |
|----------|-------------------|----------------|-------------|
| **Always Connected (Old)** | ~$86.40 | ~$2,592 | WebSocket always open |
| **Smart Disconnect (New)** | ~$0.18 | ~$5.40 | Only connect during check-ins |
| **Savings** | **99.8%** | **99.8%** | **$2,586+ saved per month!** |

## 🏗️ Architecture

The codebase is organized into modular components:

- **`voice_check_agent.py`**: Main orchestrator that coordinates all components
- **`api_manager_base.py`**: Abstract base class defining the API interface
- **`openai_manager.py`**: OpenAI Realtime API implementation
- **`gemini_manager.py`**: Google Gemini Live API implementation with screenshot support
- **`api_manager.py`**: Factory for selecting the appropriate API implementation
- **`audio_manager.py`**: Manages audio input/output streams and recording
- **`conversation_manager.py`**: Tracks and saves conversation history
- **`audio_feedback_manager.py`**: Prevents audio feedback with multiple strategies
- **`system_prompt.py`**: Configures the AI assistant's behavior

## 🛠️ Setup

### Prerequisites

- Python 3.8+
- OpenAI API key and/or Google Gemini API key
- Audio input/output device (microphone and speakers)

### Installation

1. Clone the repository:

```bash
git clone <repository-url>
cd voice-check-agent
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Set up your API keys:
   - Create a `.env` file in the project root
   - Add your API keys:

   ```
   # For OpenAI support
   OPENAI_API_KEY=your_openai_api_key_here
   
   # For Gemini support
   GEMINI_API_KEY=your_gemini_api_key_here
   ```

## 🎯 How It Works

### Smart Disconnect Cycle

1. **Timer Runs Locally**: The agent runs a timer locally (no API costs)
2. **Connect for Check-in**: When it's time, connects to the selected API
3. **Voice Conversation**: Has a brief voice conversation with the user
   - **Gemini Bonus**: Automatically captures and analyzes screenshots
4. **Agent Decides**: Based on the conversation, the agent calls one of two tools:
   - `Disconnect_Socket`: If user is productive → disconnect and save costs
   - `Sound_Alarm`: If user is wasting time → sound alarm and keep monitoring

### Agent Decision Making

**Disconnect Socket When:**

- User is working on productive tasks
- User is taking appropriate breaks
- User seems focused and on track
- Check-in concludes positively

**Sound Alarm When:**

- User is procrastinating or distracted
- User admits to wasting time
- User is engaging in unproductive activities
- User needs motivation to get back on track

## 🚀 Usage

### Basic Usage

Run the agent with default settings (OpenAI, 5-minute check-ins):

```bash
python voice_check_agent.py
```

### Using Gemini API with Screenshots

Run the agent with Gemini API (includes automatic screenshots):

```bash
python voice_check_agent.py --api gemini
```

### Advanced Options

```bash
python voice_check_agent.py [OPTIONS]
```

**Options:**

- `--api`: Choose API provider
  - `openai`: Use OpenAI Realtime API (default)
  - `gemini`: Use Google Gemini Live API with screenshot support
- `--interval`: Check-in interval in minutes (default: 5)
- `--feedback-strategy`: Audio feedback prevention strategy
  - `api_handled`: Let the API handle echo cancellation (default)
  - `smart_muting`: Mute mic when AI is speaking
  - `push_to_talk`: Manual mic control
  - `echo_cancellation`: Local echo cancellation
- `--noise-reduction`: Noise reduction type for api_handled strategy
  - `far_field`: Best for far-field mics (default)
  - `near_field`: For close-proximity mics
  - `none`: No noise reduction

### Examples

```bash
# Use Gemini with 10-minute check-ins
python voice_check_agent.py --api gemini --interval 10

# Use OpenAI with smart muting
python voice_check_agent.py --api openai --feedback-strategy smart_muting

# Use Gemini with near-field mic
python voice_check_agent.py --api gemini --noise-reduction near_field

# Test mode with 1-minute intervals
python test_voice_agent.py --api gemini
```

### Help

Get help information:

```bash
python voice_check_agent.py --help
```

## 🖼️ Screenshot Feature (Gemini Only)

When using the Gemini API, the agent automatically captures screenshots during check-ins. This provides visual context about what you're working on:

- Screenshots are captured when the agent says "check on me"
- Images are automatically resized to fit API limits
- The agent can see your screen and provide more contextual feedback
- Privacy: Screenshots are only taken during check-ins, not continuously

## 💬 Example Conversations

### Productive Scenario (with Gemini)

```
User: "check on me"
[Screenshot captured showing code editor]
Agent: "I can see you're working on the Python project in VS Code. You've made good progress on the API integration. How's the debugging going?"
User: "Pretty well, just fixed the authentication issue"
Agent: "Excellent work! I can see the clean code structure. Keep it up, I'll check on you again in 5 minutes."
[Agent calls Disconnect_Socket tool and disconnects to save costs]
```

### Unproductive Scenario (with OpenAI)

```
User: "check on me"
Agent: "Hi! How are you doing? What have you been up to?"
User: "Just scrolling through TikTok for the past hour"
Agent: "It sounds like you might be getting distracted. What important task could you focus on instead?"
User: "I guess I should work on my presentation..."
Agent: "That's a great idea! Let's get you focused on that presentation."
[Agent calls Sound_Alarm tool to help motivate the user]
```

## 🔧 Configuration

### Environment Variables

Create a `.env` file with:

```
# Choose one or both APIs
OPENAI_API_KEY=your_openai_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
```

### Audio Settings

Both APIs use these audio settings by default:

- **Format**: 16-bit PCM
- **Channels**: 1 (mono)
- **Sample Rate**:
  - OpenAI: 24,000 Hz (input/output)
  - Gemini: 16,000 Hz (input), 24,000 Hz (output)
- **Chunk Size**: 512 samples (optimized for echo cancellation)

### Conversation History

- Conversations are automatically saved to `conversation_histories/` directory
- Each session creates a timestamped JSON file
- History includes user messages, assistant responses, and function calls
- Recent history is included in the system prompt for context

### Audio Recordings

- User microphone input is recorded to `recordings/` directory
- Recordings are saved as WAV files with timestamps
- Useful for debugging audio issues

## 📊 System Architecture

```
┌─────────────────┐
│  Local Timer    │ ← No API costs
│  (5 min cycle)  │
└─────┬───────────┘
      │
      ▼
┌─────────────────┐         ┌─────────────────┐
│  Choose API     │────────▶│ Gemini API      │
│  Provider       │         │ + Screenshots   │
└─────┬───────────┘         └─────────────────┘
      │                     
      │                     ┌─────────────────┐
      └────────────────────▶│ OpenAI API      │
                            │ (Voice only)    │
                            └─────────────────┘
      ▼
┌─────────────────┐
│  Voice Check-in │ ← Brief conversation
│  Conversation   │   
└─────┬───────────┘
      │
      ▼
┌─────────────────┐
│  Agent Decides  │ ← ToolHandler processes
│  Tool to Call   │   function calls
└─────┬───────────┘
      │
      ▼
┌─────────────────┬─────────────────┐
│ Disconnect_     │ Sound_Alarm     │
│ Socket          │                 │
│ (Save costs)    │ (Keep monitoring)│
└─────────────────┴─────────────────┘
```

## 🛡️ Error Handling

- **Connection Failures**: Automatically retries on next cycle
- **Audio Issues**: Graceful fallback and error logging
- **API Switching**: Can use different APIs for different check-ins
- **Timeout Protection**: 2-minute maximum per check-in
- **Conversation History**: Automatically saved on exit
- **WebSocket/Session Errors**: Proper cleanup and reconnection

## 📝 Logs

The agent provides detailed logging:

- API selection and connection events
- Check-in cycle start/end
- Screenshot capture (Gemini only)
- Tool calls and decisions with enhanced visibility
- Audio feedback prevention status
- Error messages and warnings
- Cost-saving notifications
- Conversation history tracking

## 🔍 Troubleshooting

### Common Issues

1. **No audio input/output**: Check microphone and speaker permissions
2. **API key errors**: Verify your API keys in `.env` file
3. **Connection failures**: Check internet connection and API status
4. **Screenshot issues (Gemini)**: Ensure screen recording permissions are granted
5. **High costs**: Ensure you're using the smart disconnect version
6. **Audio feedback**: Try different feedback strategies based on your setup

### Debug Mode

Add more verbose logging by modifying the logging level in `voice_check_agent.py`:

```python
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
```

## 📈 Cost Monitoring

Monitor your usage in the respective dashboards:

- **OpenAI**: Check the OpenAI dashboard for Realtime API usage
- **Gemini**: Monitor token usage in Google Cloud Console
- Verify that connections only occur during check-ins
- Confirm 95%+ cost reduction compared to always-on connection

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test with both APIs
5. Submit a pull request

## 📄 License

MIT License - see LICENSE file for details

## 🆘 Support

If you encounter issues:

1. Check the troubleshooting section
2. Review the logs for error messages
3. Ensure your environment meets all prerequisites
4. Verify API keys are correctly set
5. Open an issue with detailed information

---

**Happy productivity monitoring with massive cost savings and multi-API support! 🎉**
