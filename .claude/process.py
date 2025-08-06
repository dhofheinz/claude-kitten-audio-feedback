#!/usr/bin/env python3
"""Singleton background processor for tips queue with continuous monitoring"""
import json
import os
import sys
import subprocess
import tempfile
from pathlib import Path
import time
import fcntl
import signal
from concurrent.futures import ThreadPoolExecutor, as_completed

# Load configuration
sys.path.insert(0, os.path.dirname(__file__))
from config import load_config
from audio_lock import AudioLock
config = load_config()

QUEUE_FILE = "/tmp/claude_code_tips_queue.json"
LOCK_FILE = "/tmp/claude_code_tips.lock"
PROCESS_PID_FILE = "/tmp/claude_tips_processor.pid"
BATCH_WAIT_TIME = config['BATCH_WAIT_TIME']
IDLE_TIMEOUT = 30  # Exit after 30 seconds of inactivity

# Track if we should continue running
running = True

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    global running
    running = False

# Register signal handlers
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

def acquire_lock(timeout=5):
    """Acquire a file lock to prevent race conditions"""
    lock_file = open(LOCK_FILE, 'w')
    start_time = time.time()
    while True:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return lock_file
        except IOError:
            if time.time() - start_time > timeout:
                return None
            time.sleep(0.1)

def release_lock(lock_file):
    """Release the file lock"""
    if lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_UN)
        lock_file.close()

def load_queue():
    """Load the current queue of tips"""
    if not os.path.exists(QUEUE_FILE):
        return {"tips": [], "last_update": 0}
    try:
        with open(QUEUE_FILE, 'r') as f:
            return json.load(f)
    except:
        return {"tips": [], "last_update": 0}

def save_queue(queue_data):
    """Save the queue of tips"""
    with open(QUEUE_FILE, 'w') as f:
        json.dump(queue_data, f)

def split_at_natural_boundaries(text, max_length=380):
    """Split text at natural speech boundaries for smoother audio"""
    if len(text) <= max_length:
        return [text]

    # Natural break points in order of preference
    break_patterns = [
        (', ', ','),  # Commas
        (' and ', ' and'),  # Conjunctions
        (' but ', ' but'),
        (' because ', ' because'),
        (' so ', ' so'),
        ('. ', '.'),  # Sentences
        (' - ', ' -'),  # Dashes
        ('; ', ';'),  # Semicolons
        (' ', '')  # Last resort - any space
    ]

    chunks = []
    remaining = text

    while len(remaining) > max_length:
        chunk_text = remaining[:max_length]
        best_break = -1
        best_pattern = None

        # Find the best natural break point
        for pattern, _ in break_patterns:
            pos = chunk_text.rfind(pattern)
            if pos > best_break and pos > max_length * 0.5:  # At least halfway through
                best_break = pos
                best_pattern = pattern

        if best_break > 0 and best_pattern is not None:
            # Split at the natural boundary
            chunk = remaining[:best_break + len(best_pattern)].strip()
            chunks.append(chunk)
            remaining = remaining[best_break + len(best_pattern):].strip()
        else:
            # No good break point, split at word boundary
            words = chunk_text.rsplit(' ', 1)
            if len(words) > 1:
                chunks.append(words[0])
                remaining = words[1] + remaining[max_length:]
            else:
                chunks.append(chunk_text)
                remaining = remaining[max_length:]

    if remaining:
        chunks.append(remaining)

    return chunks

def generate_audio_chunk(chunk_text, chunk_index, project_dir):
    """Generate audio for a single text chunk - can be run in parallel"""
    script_content = f'''
from kittentts import KittenTTS
import soundfile as sf
import numpy as np
import sys

# Initialize the model
m = KittenTTS("{config['TTS_MODEL']}")

# The text chunk
text = """{chunk_text}"""

# Generate audio with the configured voice
audio = m.generate(text, voice='{config['TTS_VOICE']}')

# Add minimal padding (50ms) and fade to prevent pops
sample_rate = {config['TTS_SAMPLE_RATE']}
padding = np.zeros(int(sample_rate * 0.05))

# Add small fade in/out (10ms) to prevent audio pops
fade_length = int(sample_rate * 0.01)
if len(audio) > fade_length * 2:
    audio[:fade_length] *= np.linspace(0, 1, fade_length)
    audio[-fade_length:] *= np.linspace(1, 0, fade_length)

audio = np.concatenate([audio, padding])

# Save to the output file passed as argument
sf.write(sys.argv[1], audio, sample_rate)
'''

    try:
        venv_python = Path(project_dir) / "tts_venv" / "bin" / "python"

        # Create temp files for script and audio
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as script_file:
            script_file.write(script_content)
            script_path = script_file.name

        with tempfile.NamedTemporaryFile(suffix=f'_{chunk_index}.wav', delete=False) as audio_file:
            audio_path = audio_file.name

        # Run the script in the virtual environment
        result = subprocess.run(
            [str(venv_python), script_path, audio_path],
            cwd=str(project_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10
        )

        # Clean up script
        os.unlink(script_path)

        if result.returncode == 0:
            return (chunk_index, audio_path)
        else:
            os.unlink(audio_path)
            return (chunk_index, None)

    except Exception as e:
        return (chunk_index, None)

def process_and_speak_tips(tips):
    """Process and speak batched tips with parallel audio generation"""
    if not tips:
        return

    # Combine tips into a single message
    if len(tips) == 1:
        message = tips[0]
    elif len(tips) == 2:
        message = f"{tips[0]} Also, {tips[1].lower()}"
    else:
        # For 3+ tips, create a numbered list
        message = "Multiple suggestions: "
        for i, tip in enumerate(tips[:3], 1):  # Limit to 3 tips max
            if i == 1:
                message += f"First, {tip.lower()}"
            elif i == 2:
                message += f" Second, {tip.lower()}"
            else:
                message += f" Finally, {tip.lower()}"

    # Ensure it ends with double ellipsis
    if not message.endswith('.....'):
        if message.endswith('...'):
            message += '..'
        else:
            message += '.....'

    # Get project directory
    project_dir = os.environ.get('CLAUDE_PROJECT_DIR', Path(__file__).parent.parent)

    # Split message into chunks at natural boundaries
    text_chunks = split_at_natural_boundaries(message)

    # Generate audio for all chunks in parallel
    audio_files = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(generate_audio_chunk, chunk, i, project_dir): i
            for i, chunk in enumerate(text_chunks)
        }

        for future in as_completed(futures):
            chunk_index, audio_path = future.result()
            if audio_path:
                audio_files[chunk_index] = audio_path

    # Play audio files in order with lock to prevent overlapping
    try:
        with AudioLock(timeout=60, wait=True):  # Wait up to 60s for current audio to finish
            for i in range(len(text_chunks)):
                if i in audio_files:
                    try:
                        # Play the audio (no timeout - let it play fully)
                        subprocess.run(
                            ["paplay", audio_files[i]],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL
                        )
                        # Clean up
                        os.unlink(audio_files[i])
                    except Exception:
                        pass
    except TimeoutError:
        # Could not acquire lock after timeout, clean up audio files
        for i in audio_files.values():
            try:
                os.unlink(i)
            except:
                pass

def cleanup_and_exit():
    """Clean up PID file and exit"""
    try:
        os.unlink(PROCESS_PID_FILE)
    except:
        pass
    sys.exit(0)

# Main: Continuously monitor queue for new tips
if __name__ == "__main__":
    # Exit early if audio feedback is disabled
    if not config.get('ENABLE_AUDIO_FEEDBACK', True):
        cleanup_and_exit()
    
    last_activity_time = time.time()
    tips_batch = []
    batch_start_time = None
    
    # Continuously monitor the queue
    while running:
        current_time = time.time()
        
        # Check for timeout (exit if idle too long)
        if current_time - last_activity_time > IDLE_TIMEOUT:
            if not tips_batch:  # No pending tips
                cleanup_and_exit()
        
        # Check the queue for new tips
        lock = acquire_lock()
        if lock:
            try:
                queue_data = load_queue()
                
                # Check if new tips arrived
                if queue_data["tips"]:
                    last_activity_time = current_time
                    
                    if not tips_batch:
                        # First tip in new batch
                        batch_start_time = current_time
                    
                    # Add new tips to batch
                    tips_batch.extend(queue_data["tips"])
                    
                    # Clear the queue
                    queue_data = {"tips": [], "last_update": 0}
                    save_queue(queue_data)
            finally:
                release_lock(lock)
        
        # Process batch if ready
        if tips_batch and batch_start_time:
            if current_time - batch_start_time >= BATCH_WAIT_TIME:
                # Process the batch
                process_and_speak_tips(tips_batch)
                
                # Reset for next batch
                tips_batch = []
                batch_start_time = None
                last_activity_time = current_time
        
        # Sleep briefly to avoid busy waiting
        time.sleep(0.1)
    
    # Clean shutdown
    cleanup_and_exit()