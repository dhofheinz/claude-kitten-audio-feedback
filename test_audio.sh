#!/bin/bash
# Test audio output for KittenTTS

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

if [ ! -d "tts_venv" ]; then
    echo "Error: Virtual environment not found. Please run ./setup.sh first"
    exit 1
fi

echo "Testing KittenTTS audio output..."
echo ""

"$SCRIPT_DIR/tts_venv/bin/python" << 'EOF'
from kittentts import KittenTTS
import soundfile as sf
import subprocess
import tempfile
import os

try:
    # Load the model
    print("Loading KittenTTS model...")
    m = KittenTTS('KittenML/kitten-tts-nano-0.1')
    
    # Test message
    text = "Kid, your audio system is working. Now go write some code that doesn't suck."
    
    print(f"Generating audio: '{text}'")
    audio = m.generate(text, voice='expr-voice-2-m')
    
    # Save to temp file
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
        temp_path = f.name
        sf.write(temp_path, audio, 24000)
    
    # Play audio
    print("Playing audio...")
    result = subprocess.run(['paplay', temp_path], capture_output=True)
    
    # Clean up
    os.unlink(temp_path)
    
    if result.returncode == 0:
        print("\n✓ Audio test successful!")
    else:
        print("\n✗ Audio playback failed. Check your audio setup.")
        if result.stderr:
            print(f"Error: {result.stderr.decode()}")

except Exception as e:
    print(f"\n✗ Test failed: {e}")
    print("\nTroubleshooting:")
    print("1. Make sure PulseAudio is running (for Linux/WSL2)")
    print("2. Check that paplay is installed: which paplay")
    print("3. Try running: paplay /usr/share/sounds/alsa/Front_Center.wav")
EOF