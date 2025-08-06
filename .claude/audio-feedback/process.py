#!/usr/bin/env python3
"""Singleton background processor for tips queue with continuous monitoring."""

from __future__ import annotations

import json
import os
import sys
import time
import fcntl
import signal
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

# -----------------------------------
# Config
# -----------------------------------

# Load configuration
sys.path.insert(0, os.path.dirname(__file__))
from config import load_config  # type: ignore[import-not-found]
from audio_lock import AudioLock  # type: ignore[import-not-found]

config = load_config()

QUEUE_FILE = Path("/tmp/claude_code_tips_queue.json")
LOCK_FILE = Path("/tmp/claude_code_tips.lock")
PROCESS_PID_FILE = Path("/tmp/claude_tips_processor.pid")
HEALTH_CHECK_FILE = Path("/tmp/claude_tips_processor.health")

BATCH_WAIT_TIME: float = float(config.get("BATCH_WAIT_TIME", 0.0))
IDLE_TIMEOUT: int = config.get('PROCESSOR_IDLE_TIMEOUT', 30)  # Configurable idle timeout

# Track if we should continue running
running: bool = True


# -----------------------------------
# Signals
# -----------------------------------

def signal_handler(signum, frame) -> None:  # noqa: ANN001
    """Handle shutdown signals gracefully."""
    global running
    running = False


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


# -----------------------------------
# Locking & IO helpers
# -----------------------------------

def acquire_lock(timeout: float = 5.0):
    """Acquire a file lock to prevent race conditions. Returns an open file or None on timeout."""
    lock_file = open(LOCK_FILE, "a+")  # avoid truncation
    start_time = time.time()
    while True:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return lock_file
        except OSError:
            if time.time() - start_time > timeout:
                try:
                    lock_file.close()
                except Exception:
                    pass
                return None
            time.sleep(0.1)


def release_lock(lock_file) -> None:
    """Release the file lock."""
    if lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_UN)
        finally:
            try:
                lock_file.close()
            except Exception:
                pass


def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data))
    os.replace(tmp, path)


def load_queue() -> Dict[str, Any]:
    """Load the current queue of tips."""
    if not QUEUE_FILE.exists():
        return {"tips": [], "last_update": 0}
    try:
        return json.loads(QUEUE_FILE.read_text())
    except Exception:
        return {"tips": [], "last_update": 0}


def save_queue(queue_data: Dict[str, Any]) -> None:
    """Save the queue of tips atomically."""
    _atomic_write_json(QUEUE_FILE, queue_data)


# -----------------------------------
# Text utils
# -----------------------------------

def split_at_natural_boundaries(text: str, max_length: int = 380) -> List[str]:
    """Split text at natural speech boundaries for smoother audio."""
    if len(text) <= max_length:
        return [text]

    # Natural break points in order of preference
    break_patterns = [
        ", ",
        " and ",
        " but ",
        " because ",
        " so ",
        ". ",
        " - ",
        "; ",
        " ",
    ]

    chunks: List[str] = []
    remaining = text

    while len(remaining) > max_length:
        window = remaining[:max_length]
        best_break = -1
        for pattern in break_patterns:
            pos = window.rfind(pattern)
            if pos > best_break and pos > max_length * 0.5:  # at least halfway
                best_break = pos
                best_pat_len = len(pattern)

        if best_break > 0:
            split_at = best_break + best_pat_len
            chunk = remaining[:split_at].strip()
            chunks.append(chunk)
            remaining = remaining[split_at:].strip()
        else:
            # Fallback: split at last space
            space_pos = window.rfind(" ")
            if space_pos > 0:
                chunks.append(remaining[:space_pos].strip())
                remaining = remaining[space_pos + 1 :].strip()
            else:
                chunks.append(window.strip())
                remaining = remaining[max_length:].strip()

    if remaining:
        chunks.append(remaining)

    return chunks


# -----------------------------------
# Audio generation
# -----------------------------------

def _python_exe_for_tts(project_dir: Path) -> str:
    """Pick venv python if present, else current interpreter."""
    venv_python = project_dir / "tts_venv" / "bin" / "python"
    if venv_python.exists() and venv_python.is_file():
        return str(venv_python)
    return sys.executable


def generate_audio_chunk(chunk_text: str, chunk_index: int, project_dir: Path) -> Tuple[int, Optional[str]]:
    """Generate audio for a single text chunk - can be run in parallel."""
    # Use json.dumps to embed safe Python string literals
    py_text = json.dumps(chunk_text)
    py_voice = json.dumps(config.get("TTS_VOICE", "default"))
    py_model = json.dumps(config.get("TTS_MODEL", "kitten-small"))
    sample_rate = int(config.get("TTS_SAMPLE_RATE", 22050))

    script_content = f"""# auto-generated
from kittentts import KittenTTS
import soundfile as sf
import numpy as np
import sys

m = KittenTTS({py_model})
text = {py_text}
audio = m.generate(text, voice={py_voice})

sample_rate = {sample_rate}
padding = np.zeros(int(sample_rate * 0.05))

fade_length = int(sample_rate * 0.01)
if len(audio) > fade_length * 2:
    audio[:fade_length] *= np.linspace(0, 1, fade_length)
    audio[-fade_length:] *= np.linspace(1, 0, fade_length)

audio = np.concatenate([audio, padding])
sf.write(sys.argv[1], audio, sample_rate)
"""

    script_path = None
    audio_path = None

    try:
        python_exe = _python_exe_for_tts(project_dir)

        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as script_file:
            script_file.write(script_content)
            script_path = script_file.name

        with tempfile.NamedTemporaryFile(suffix=f"_{chunk_index}.wav", delete=False) as audio_file:
            audio_path = audio_file.name

        result = subprocess.run(  # noqa: S603
            [python_exe, script_path, audio_path],
            cwd=str(project_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )

        if result.returncode == 0:
            return (chunk_index, audio_path)

        # Failure path cleanup
        try:
            if audio_path and Path(audio_path).exists():
                os.unlink(audio_path)
        except Exception:
            pass
        return (chunk_index, None)

    except Exception:
        # Cleanup on exception
        try:
            if audio_path and Path(audio_path).exists():
                os.unlink(audio_path)
        except Exception:
            pass
        return (chunk_index, None)
    finally:
        try:
            if script_path and Path(script_path).exists():
                os.unlink(script_path)
        except Exception:
            pass


# -----------------------------------
# Batch processing & playback
# -----------------------------------

def _build_batch_message(tips: List[str]) -> str:
    """Combine tips into a single message (keep original semantics)."""
    if not tips:
        return ""

    if len(tips) == 1:
        message = tips[0]
    elif len(tips) == 2:
        message = f"{tips[0]} Also, {tips[1].lower()}"
    else:
        # For 3+ tips, create a numbered/ordered-like list (max 3)
        message = "Multiple suggestions: "
        for i, tip in enumerate(tips[:3], 1):
            if i == 1:
                message += f"First, {tip.lower()}"
            elif i == 2:
                message += f" Second, {tip.lower()}"
            else:
                message += f" Finally, {tip.lower()}"

    # Ensure it ends with double ellipsis
    if not message.endswith("....."):
        message = message + (".." if message.endswith("...") else ".....")

    return message


def process_and_speak_tips(tips: List[str]) -> bool:
    """Process and speak batched tips with parallel audio generation.
    
    Returns:
        True if tips were successfully played, False otherwise.
    """
    if not tips:
        return True

    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", Path(__file__).parent.parent))
    message = _build_batch_message(tips)

    # Split message into chunks at natural boundaries
    text_chunks = split_at_natural_boundaries(message)

    # Generate audio for all chunks in parallel
    audio_files: Dict[int, str] = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(generate_audio_chunk, chunk, i, project_dir): i
            for i, chunk in enumerate(text_chunks)
        }
        for future in as_completed(futures):
            idx, path = future.result()
            if path:
                audio_files[idx] = path

    # Play audio files in order with lock to prevent overlapping
    success = False
    try:
        with AudioLock(timeout=60, wait=True):  # Wait up to 60s for current audio to finish
            played_count = 0
            for i in range(len(text_chunks)):
                path = audio_files.get(i)
                if not path:
                    continue
                try:
                    result = subprocess.run(  # noqa: S603
                        ["paplay", path],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    if result.returncode == 0:
                        played_count += 1
                except Exception:
                    pass
                finally:
                    try:
                        os.unlink(path)
                    except Exception:
                        pass
            # Consider success if we played at least one chunk
            success = played_count > 0
    except TimeoutError:
        # Could not acquire lock after timeout, clean up audio files
        for p in audio_files.values():
            try:
                os.unlink(p)
            except Exception:
                pass
        success = False
    
    return success


def update_health_check() -> None:
    """Touch the health check file to indicate the processor is alive."""
    try:
        HEALTH_CHECK_FILE.touch()
    except Exception:
        pass


def cleanup_and_exit(code: int = 0) -> None:
    """Clean up PID file and health check file, then exit."""
    try:
        if PROCESS_PID_FILE.exists():
            os.unlink(PROCESS_PID_FILE)
    except Exception:
        pass
    try:
        if HEALTH_CHECK_FILE.exists():
            os.unlink(HEALTH_CHECK_FILE)
    except Exception:
        pass
    sys.exit(code)


# -----------------------------------
# Main loop
# -----------------------------------

if __name__ == "__main__":
    # Exit early if audio feedback is disabled
    if not config.get("ENABLE_AUDIO_FEEDBACK", True):
        cleanup_and_exit(0)

    last_activity_time = time.time()
    last_health_update = time.time()
    tips_batch: List[str] = []
    batch_start_time: Optional[float] = None
    
    # Initial health check
    update_health_check()

    while running:
        current_time = time.time()
        
        # Update health check every 5 seconds
        if current_time - last_health_update >= 5:
            update_health_check()
            last_health_update = current_time

        # Check for timeout (exit if idle too long)
        if current_time - last_activity_time > IDLE_TIMEOUT and not tips_batch:
            cleanup_and_exit(0)

        # Check the queue for new tips (only if we're not already processing)
        if not tips_batch:  # Only read queue if we don't have tips pending
            lock = acquire_lock()
            if lock:
                try:
                    queue_data = load_queue()
                    tips = queue_data.get("tips", [])
                    if tips:
                        last_activity_time = current_time
                        batch_start_time = current_time
                        tips_batch = tips.copy()  # Take a snapshot of current tips
                        # Clear the queue atomically to prevent other processes from reading same tips
                        save_queue({"tips": [], "last_update": time.time()})
                finally:
                    release_lock(lock)

        # Process batch if ready
        if tips_batch and batch_start_time is not None:
            if current_time - batch_start_time >= BATCH_WAIT_TIME:
                # Try to process and speak tips
                if process_and_speak_tips(tips_batch):
                    # Success! Clear the batch
                    tips_batch = []
                    batch_start_time = None
                else:
                    # Failed to play - keep tips in batch for retry
                    # Reset timer to try again after another batch wait
                    batch_start_time = current_time
                last_activity_time = current_time

        # Sleep briefly to avoid busy waiting
        time.sleep(0.1)

    # Clean shutdown
    cleanup_and_exit(0)
