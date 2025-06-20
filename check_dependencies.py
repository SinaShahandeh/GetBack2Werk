#!/usr/bin/env python3
"""
Dependency checker for Voice Check Agent.
This script verifies that all required dependencies are installed with correct versions.
"""

import sys
import importlib
import pkg_resources

def check_python_version():
    """Check Python version."""
    version = sys.version_info
    print(f"Python version: {version.major}.{version.minor}.{version.micro}")
    
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("❌ Python 3.8 or higher is required")
        return False
    else:
        print("✅ Python version is compatible")
        return True

def check_package(package_name, min_version=None):
    """Check if a package is installed with the correct version."""
    try:
        # Try to import the package
        module = importlib.import_module(package_name)
        
        # Get installed version
        try:
            installed_version = pkg_resources.get_distribution(package_name).version
        except pkg_resources.DistributionNotFound:
            installed_version = getattr(module, '__version__', 'unknown')
        
        print(f"✅ {package_name}: {installed_version}")
        
        # Check minimum version if specified
        if min_version and installed_version != 'unknown':
            try:
                if pkg_resources.parse_version(installed_version) < pkg_resources.parse_version(min_version):
                    print(f"⚠️  {package_name} version {installed_version} is below minimum {min_version}")
                    return False
            except:
                pass
        
        return True
        
    except ImportError:
        print(f"❌ {package_name}: Not installed")
        return False
    except Exception as e:
        print(f"❌ {package_name}: Error checking - {e}")
        return False

def check_audio_devices():
    """Check audio device availability."""
    try:
        import pyaudio
        
        audio = pyaudio.PyAudio()
        
        input_count = 0
        output_count = 0
        
        for i in range(audio.get_device_count()):
            info = audio.get_device_info_by_index(i)
            if info['maxInputChannels'] > 0:
                input_count += 1
            if info['maxOutputChannels'] > 0:
                output_count += 1
        
        print(f"✅ Audio devices: {input_count} input, {output_count} output")
        audio.terminate()
        
        if input_count == 0:
            print("⚠️  No microphone devices found")
            return False
        if output_count == 0:
            print("⚠️  No speaker devices found")
            return False
            
        return True
        
    except Exception as e:
        print(f"❌ Audio check failed: {e}")
        return False

def check_environment():
    """Check environment variables."""
    import os
    from dotenv import load_dotenv
    
    # Load .env file
    load_dotenv()
    
    api_key = os.getenv('OPENAI_API_KEY')
    if api_key:
        print(f"✅ OPENAI_API_KEY: Set (length: {len(api_key)})")
        return True
    else:
        print("❌ OPENAI_API_KEY: Not set")
        return False

def main():
    """Run all dependency checks."""
    print("🔍 Voice Check Agent - Dependency Checker")
    print("=" * 50)
    
    all_good = True
    
    # Required packages with minimum versions
    packages = [
        ('aiohttp', '3.8.0'),
        ('websockets', '11.0.0'),
        ('pyaudio', '0.2.11'),
        ('openai', '1.0.0'),
        ('dotenv', '1.0.0'),
    ]
    
    print("\n📋 Checking Python version...")
    if not check_python_version():
        all_good = False
    
    print("\n📦 Checking Python packages...")
    for package, min_version in packages:
        if not check_package(package, min_version):
            all_good = False
    
    print("\n🔊 Checking audio devices...")
    if not check_audio_devices():
        all_good = False
    
    print("\n🔑 Checking environment...")
    if not check_environment():
        all_good = False
    
    print("\n" + "=" * 50)
    if all_good:
        print("🎉 All checks passed! You should be able to run the voice agent.")
    else:
        print("⚠️  Some issues found. Please resolve them before running the agent.")
        print("\nSuggested fixes:")
        print("1. Run: pip install -r requirements.txt --upgrade")
        print("2. Create .env file with: OPENAI_API_KEY=your_key_here")
        print("3. Check audio device connections")
    
    print("=" * 50)

if __name__ == "__main__":
    main() 