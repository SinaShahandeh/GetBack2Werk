#!/usr/bin/env python3
"""
Setup script for Voice Check Agent.
This script helps with initial setup and dependency installation.
"""

import os
import sys
import subprocess
import platform

def print_header():
    """Print setup header."""
    print("=" * 60)
    print("🤖 Voice Check Agent Setup")
    print("=" * 60)

def check_python_version():
    """Check if Python version is compatible."""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("❌ Python 3.8 or higher is required")
        print(f"   Current version: {version.major}.{version.minor}.{version.micro}")
        return False
    
    print(f"✅ Python version: {version.major}.{version.minor}.{version.micro}")
    return True

def install_system_dependencies():
    """Install system dependencies for audio processing."""
    system = platform.system()
    
    print("\n📦 Installing system dependencies...")
    
    if system == "Darwin":  # macOS
        print("Detected macOS")
        try:
            subprocess.run(["brew", "--version"], check=True, capture_output=True)
            print("Installing PortAudio via Homebrew...")
            subprocess.run(["brew", "install", "portaudio"], check=True)
            print("✅ PortAudio installed successfully")
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("⚠️  Homebrew not found. Please install PortAudio manually:")
            print("   brew install portaudio")
            return False
    
    elif system == "Linux":
        print("Detected Linux")
        # Try different package managers
        if os.path.exists("/usr/bin/apt-get"):
            print("Installing PortAudio via apt...")
            try:
                subprocess.run(["sudo", "apt-get", "update"], check=True)
                subprocess.run(["sudo", "apt-get", "install", "-y", "portaudio19-dev"], check=True)
                print("✅ PortAudio installed successfully")
            except subprocess.CalledProcessError:
                print("⚠️  Failed to install PortAudio. Please install manually:")
                print("   sudo apt-get install portaudio19-dev")
                return False
        else:
            print("⚠️  Unknown Linux distribution. Please install PortAudio manually:")
            print("   On Ubuntu/Debian: sudo apt-get install portaudio19-dev")
            print("   On CentOS/RHEL: sudo yum install portaudio-devel")
            return False
    
    elif system == "Windows":
        print("Detected Windows")
        print("ℹ️  PyAudio wheels should work on Windows")
        print("   If you encounter issues, try: conda install pyaudio")
    
    else:
        print(f"⚠️  Unknown system: {system}")
        print("   Please install PortAudio manually for your system")
        return False
    
    return True

def install_python_dependencies():
    """Install Python dependencies."""
    print("\n🐍 Installing Python dependencies...")
    
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], check=True)
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)
        print("✅ Python dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install Python dependencies: {e}")
        return False

def setup_environment():
    """Help user set up environment variables."""
    print("\n🔑 Setting up environment...")
    
    # Load .env file if it exists
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    
    api_key = os.getenv('OPENAI_API_KEY')
    if api_key:
        print(f"✅ OPENAI_API_KEY is already set")
        return True
    
    print("❌ OPENAI_API_KEY not found")
    print("\nPlease set your OpenAI API key:")
    print("1. Get your API key from: https://platform.openai.com/api-keys")
    print("2. Choose one of these methods:")
    print("\n   Option A: Create a .env file (RECOMMENDED):")
    print("   Create a file named '.env' in this directory with:")
    print("   OPENAI_API_KEY=your_api_key_here")
    print("\n   Option B: Set as environment variable:")
    
    if platform.system() == "Windows":
        print("   Windows (Command Prompt):")
        print("   set OPENAI_API_KEY=your_api_key_here")
        print("   ")
        print("   Windows (PowerShell):")
        print("   $env:OPENAI_API_KEY='your_api_key_here'")
    else:
        print("   macOS/Linux:")
        print("   export OPENAI_API_KEY='your_api_key_here'")
        print("   ")
        print("   To make it permanent, add to ~/.bashrc or ~/.zshrc:")
        print("   echo 'export OPENAI_API_KEY=\"your_api_key_here\"' >> ~/.bashrc")
    
    return False

def test_audio_devices():
    """Test audio device availability."""
    print("\n🔊 Testing audio devices...")
    
    try:
        import pyaudio
        
        audio = pyaudio.PyAudio()
        
        # Check input devices
        input_devices = []
        output_devices = []
        
        for i in range(audio.get_device_count()):
            info = audio.get_device_info_by_index(i)
            if info['maxInputChannels'] > 0:
                input_devices.append(f"  {i}: {info['name']}")
            if info['maxOutputChannels'] > 0:
                output_devices.append(f"  {i}: {info['name']}")
        
        print(f"✅ Found {len(input_devices)} input device(s):")
        for device in input_devices[:3]:  # Show first 3
            print(device)
        
        print(f"✅ Found {len(output_devices)} output device(s):")
        for device in output_devices[:3]:  # Show first 3
            print(device)
        
        audio.terminate()
        
        if not input_devices:
            print("⚠️  No microphone devices found")
            return False
        
        if not output_devices:
            print("⚠️  No speaker devices found")
            return False
        
        return True
        
    except ImportError:
        print("❌ PyAudio not installed - cannot test audio devices")
        return False
    except Exception as e:
        print(f"❌ Error testing audio devices: {e}")
        return False

def run_setup():
    """Run the complete setup process."""
    print_header()
    
    success = True
    
    # Check Python version
    if not check_python_version():
        success = False
    
    # Install system dependencies
    if success and not install_system_dependencies():
        success = False
    
    # Install Python dependencies
    if success and not install_python_dependencies():
        success = False
    
    # Test audio devices
    if success and not test_audio_devices():
        print("⚠️  Audio device issues detected - the agent may not work properly")
    
    # Setup environment
    if success and not setup_environment():
        success = False
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 Setup completed successfully!")
        print("\nNext steps:")
        print("1. Set your OPENAI_API_KEY environment variable (if not done)")
        print("2. Run the agent: python run_agent.py")
        print("   Or directly: python voice_check_agent.py")
    else:
        print("⚠️  Setup completed with issues")
        print("Please resolve the issues above before running the agent")
    
    print("=" * 60)

if __name__ == "__main__":
    run_setup() 