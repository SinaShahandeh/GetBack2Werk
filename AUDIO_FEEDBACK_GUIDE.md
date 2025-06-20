# Audio Feedback Prevention Guide

This guide explains how to prevent your microphone from picking up the AI's voice output, eliminating feedback loops in your voice application.

## Quick Solutions

### 🎧 1. Use Headphones (Recommended)

**The simplest and most effective solution:**

- Plug in any headphones or earbuds
- AI's voice goes directly to your ears instead of speakers
- Completely eliminates feedback

### 🔧 2. Use Software Solutions

The application now includes several built-in strategies to prevent feedback.

## Available Strategies

### Smart Muting (Default)

Automatically mutes the microphone when the AI is speaking.

```bash
# Use smart muting (default)
python voice_check_agent.py --feedback-strategy smart_muting
```

**How it works:**

- Microphone is muted when AI starts speaking
- Waits 0.5 seconds after AI finishes before unmuting
- Prevents AI voice from being picked up by microphone

### Push-to-Talk

Requires you to hold a key to speak.

```bash
# Use push-to-talk mode
python voice_check_agent.py --feedback-strategy push_to_talk
```

**How it works:**

- Hold spacebar (or configured key) to speak
- Microphone is muted when key is not pressed
- Completely prevents accidental audio pickup

### Echo Cancellation

Uses signal processing to remove echo from microphone input.

```bash
# Use echo cancellation
python voice_check_agent.py --feedback-strategy echo_cancellation
```

**How it works:**

- Monitors AI's audio output as reference
- Subtracts similar audio from microphone input
- More advanced but may not be 100% effective

## Testing Your Setup

Use the audio test utility to find the best configuration:

```bash
python audio_test_utility.py
```

This utility will:

1. List your available audio devices
2. Test different feedback prevention strategies
3. Help you configure device separation
4. Provide personalized recommendations

## Advanced Configuration

### Using Different Audio Devices

List available devices:

```bash
python audio_test_utility.py
# Choose option 1 to list devices
```

Then modify your code to use specific devices:

```python
# In setup_audio_streams method
self.input_stream = self.audio.open(
    format=self.audio_format,
    channels=self.channels,
    rate=self.rate,
    input=True,
    input_device_index=1,  # Use specific microphone
    frames_per_buffer=self.chunk
)

self.output_stream = self.audio.open(
    format=self.audio_format,
    channels=self.channels,
    rate=self.rate,
    output=True,
    output_device_index=0,  # Use specific speakers
    frames_per_buffer=self.chunk
)
```

### Manual Microphone Control

You can manually mute/unmute the microphone:

```python
# In your agent code
agent.feedback_manager.set_manual_mute(True)   # Mute
agent.feedback_manager.set_manual_mute(False)  # Unmute
```

## Installation Requirements

Make sure you have all required packages:

```bash
pip install -r requirements.txt
```

For push-to-talk functionality, ensure the `keyboard` library is installed:

```bash
pip install keyboard
```

## Troubleshooting

### Common Issues

1. **Still getting feedback with smart muting:**
   - Try increasing the delay: modify `ai_speech_delay` in `AudioFeedbackManager`
   - Consider using push-to-talk instead

2. **Push-to-talk not working:**
   - Make sure `keyboard` library is installed
   - Check if you have permission to capture keyboard events
   - Try running with administrator privileges on Windows

3. **Echo cancellation not effective:**
   - This is a basic implementation for demonstration
   - Consider using headphones or smart muting instead
   - Professional echo cancellation requires more sophisticated algorithms

4. **Audio devices not listed correctly:**
   - Restart the application
   - Check if audio devices are properly connected
   - Update audio drivers

### Performance Tips

1. **Smart Muting** - Best balance of effectiveness and naturalness
2. **Push-to-Talk** - Most reliable but requires manual interaction
3. **Echo Cancellation** - Experimental, may affect audio quality

## Hardware Recommendations

### Best (No Feedback)

- Any wired or wireless headphones
- Gaming headsets with boom microphones
- Earbuds with built-in microphones

### Good (Minimal Setup)

- External USB microphone + built-in speakers
- Built-in microphone + external speakers
- Webcam microphone + headphones

### Okay (Requires Software Solutions)

- Built-in laptop microphone + built-in speakers
- External microphone + external speakers near microphone

## Example Usage

```bash
# Start with smart muting (recommended for most users)
python voice_check_agent.py --feedback-strategy smart_muting

# Use push-to-talk for guaranteed no feedback
python voice_check_agent.py --feedback-strategy push_to_talk

# Test your audio setup first
python audio_test_utility.py

# Run with custom check interval and feedback strategy
python voice_check_agent.py --interval 10 --feedback-strategy smart_muting
```

## Need Help?

1. Run the audio test utility: `python audio_test_utility.py`
2. Try different strategies to see what works best
3. Check that your microphone and speakers are working properly
4. Consider using headphones for the best experience
