#!/usr/bin/env python3
"""Shared audio playback locking mechanism to prevent overlapping audio"""

import fcntl
import time
import os
from pathlib import Path

AUDIO_LOCK_FILE = "/tmp/claude_kitten_audio.lock"
AUDIO_LOCK_TIMEOUT = 30  # Maximum time to wait for lock (seconds)

class AudioLock:
    """Context manager for audio playback locking"""
    
    def __init__(self, timeout=AUDIO_LOCK_TIMEOUT, wait=True):
        """
        Initialize audio lock.
        
        Args:
            timeout: Maximum time to wait for lock in seconds
            wait: If True, wait for lock. If False, fail immediately if locked.
        """
        self.timeout = timeout
        self.wait = wait
        self.lock_file = None
        self.locked = False
    
    def __enter__(self):
        """Acquire the audio lock"""
        self.lock_file = open(AUDIO_LOCK_FILE, 'w')
        
        if self.wait:
            # Wait for lock with timeout
            start_time = time.time()
            while True:
                try:
                    fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self.locked = True
                    # Write PID for debugging
                    self.lock_file.write(f"{os.getpid()}\n")
                    self.lock_file.flush()
                    return self
                except IOError:
                    if time.time() - start_time > self.timeout:
                        self.lock_file.close()
                        raise TimeoutError(f"Could not acquire audio lock after {self.timeout} seconds")
                    time.sleep(0.1)
        else:
            # Try once, fail if locked
            try:
                fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.locked = True
                self.lock_file.write(f"{os.getpid()}\n")
                self.lock_file.flush()
                return self
            except IOError:
                self.lock_file.close()
                raise RuntimeError("Audio is already playing")
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Release the audio lock"""
        if self.lock_file and self.locked:
            try:
                fcntl.flock(self.lock_file, fcntl.LOCK_UN)
            except (IOError, OSError):
                # Lock release failed, but we're exiting anyway
                pass
            finally:
                self.lock_file.close()

def is_audio_playing():
    """Check if audio is currently playing (lock is held)"""
    try:
        with open(AUDIO_LOCK_FILE, 'w') as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(f, fcntl.LOCK_UN)
            return False
    except IOError:
        return True

def wait_for_audio():
    """Wait for any current audio to finish"""
    with AudioLock(wait=True):
        pass  # Just acquire and release the lock