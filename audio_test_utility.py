#!/usr/bin/env python3
"""
Audio Test Utility - Helps users configure their audio setup to prevent feedback.
"""

import sys
import time
import threading
from audio_feedback_manager import AudioFeedbackManager, AudioDeviceManager

def main():
    """Main menu for audio testing and configuration."""
    print("🎧 Voice Agent Audio Configuration Utility")
    print("=" * 50)
    
    while True:
        print("\nChoose an option:")
        print("1. List available audio devices")
        print("2. Get feedback prevention recommendations")
        print("3. Test smart muting strategy")
        print("4. Test push-to-talk strategy")
        print("5. Test echo cancellation strategy")
        print("6. Test different audio devices")
        print("7. Exit")
        
        choice = input("\nEnter your choice (1-7): ").strip()
        
        if choice == "1":
            AudioDeviceManager.list_audio_devices()
            
        elif choice == "2":
            AudioDeviceManager.get_device_recommendation()
            
        elif choice == "3":
            test_smart_muting()
            
        elif choice == "4":
            test_push_to_talk()
            
        elif choice == "5":
            test_echo_cancellation()
            
        elif choice == "6":
            test_device_separation()
            
        elif choice == "7":
            print("👋 Goodbye!")
            break
            
        else:
            print("❌ Invalid choice. Please try again.")

def test_smart_muting():
    """Test the smart muting strategy."""
    print("\n🔇 Testing Smart Muting Strategy")
    print("=" * 40)
    print("This strategy mutes the microphone when AI is speaking.")
    print("You'll see status updates showing when the mic is muted/unmuted.")
    
    manager = AudioFeedbackManager(strategy="smart_muting", ai_speech_delay=1.0)
    
    print("\nSimulating AI speaking cycle...")
    
    # Simulate AI starting to speak
    print("🤖 AI started speaking...")
    manager.mark_ai_speaking_start()
    print(f"Status: {manager.get_status()}")
    
    time.sleep(2)
    
    # Simulate AI finishing speaking
    print("🤖 AI finished speaking...")
    manager.mark_ai_speaking_end()
    print(f"Status: {manager.get_status()}")
    
    # Wait for unmute delay
    print("⏳ Waiting for unmute delay...")
    time.sleep(1.5)
    print(f"Status: {manager.get_status()}")
    
    print("✅ Smart muting test completed!")

def test_push_to_talk():
    """Test the push-to-talk strategy."""
    print("\n🎙️ Testing Push-to-Talk Strategy")
    print("=" * 40)
    print("This strategy requires you to hold a key to speak.")
    
    try:
        import keyboard
        print("✅ Keyboard library available")
        
        key = input("Enter key to use for push-to-talk (default: space): ").strip() or "space"
        
        print(f"\nPress and hold '{key}' to speak, 'q' to quit test")
        manager = AudioFeedbackManager(strategy="push_to_talk", push_to_talk_key=key)
        
        print("🎮 Push-to-talk test running...")
        print("Hold the key and watch the status change!")
        
        # Monitor for 30 seconds or until 'q' is pressed
        start_time = time.time()
        while time.time() - start_time < 30:
            status = manager.get_status()
            if status['push_to_talk_pressed']:
                print("🎙️ SPEAKING ENABLED")
            else:
                print("🔇 MUTED", end="\r")
            
            if keyboard.is_pressed('q'):
                break
                
            time.sleep(0.1)
        
        print("\n✅ Push-to-talk test completed!")
        
    except ImportError:
        print("❌ Keyboard library not installed.")
        print("Install with: pip install keyboard")

def test_echo_cancellation():
    """Test the echo cancellation strategy."""
    print("\n🔊 Testing Echo Cancellation Strategy")
    print("=" * 40)
    print("This strategy attempts to cancel echo using signal processing.")
    print("Note: This is a basic implementation for demonstration.")
    
    manager = AudioFeedbackManager(strategy="echo_cancellation")
    
    # Simulate adding reference audio and processing input
    import numpy as np
    
    print("Simulating audio processing...")
    
    # Simulate AI audio output (reference)
    reference_audio = np.random.randint(-1000, 1000, 1024, dtype=np.int16)
    manager.add_reference_audio(reference_audio.tobytes())
    
    # Simulate microphone input with echo
    input_with_echo = reference_audio * 0.5 + np.random.randint(-100, 100, 1024, dtype=np.int16)
    
    # Process the input
    processed = manager.process_microphone_audio(input_with_echo.astype(np.int16).tobytes())
    
    if processed:
        processed_array = np.frombuffer(processed, dtype=np.int16)
        original_power = np.mean(np.abs(input_with_echo))
        processed_power = np.mean(np.abs(processed_array))
        
        print(f"Original audio power: {original_power:.2f}")
        print(f"Processed audio power: {processed_power:.2f}")
        print(f"Echo reduction: {((original_power - processed_power) / original_power * 100):.1f}%")
    
    print("✅ Echo cancellation test completed!")
    print("Note: Real-world echo cancellation requires more sophisticated algorithms.")

def test_device_separation():
    """Test using different input/output devices."""
    print("\n🎧 Testing Device Separation")
    print("=" * 40)
    print("Using different devices for input and output prevents feedback.")
    
    AudioDeviceManager.list_audio_devices()
    
    print("\n💡 Recommendations:")
    print("- Use headphones (output device) to completely eliminate feedback")
    print("- Or use external microphone + built-in speakers")
    print("- Or use built-in microphone + external speakers")
    
    test_config = input("\nWould you like to test a specific device configuration? (y/n): ").lower()
    
    if test_config == 'y':
        try:
            input_device = input("Enter input device ID (or press Enter for default): ").strip()
            output_device = input("Enter output device ID (or press Enter for default): ").strip()
            
            input_device = int(input_device) if input_device else None
            output_device = int(output_device) if output_device else None
            
            print(f"✅ Configuration saved:")
            print(f"   Input device: {input_device if input_device is not None else 'Default'}")
            print(f"   Output device: {output_device if output_device is not None else 'Default'}")
            print(f"   You can use these device IDs in your voice agent configuration.")
            
        except ValueError:
            print("❌ Invalid device ID. Please use numbers only.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        sys.exit(0) 