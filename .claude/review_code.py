#!/usr/bin/env python3
"""Unified code review handler - analyzes changes and processes audio feedback"""

import sys
import subprocess
import os
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))
from config import load_config

def main():
    """Main handler that launches both analyzer and processor"""
    project_dir = os.environ.get('CLAUDE_PROJECT_DIR', Path(__file__).parent.parent)
    config = load_config()
    
    # Launch the background audio processor only if audio feedback is enabled
    if config.get('ENABLE_AUDIO_FEEDBACK', True):
        processor_path = Path(__file__).parent / "process_tips.py"
        subprocess.Popen(
            [sys.executable, str(processor_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True  # Detach from parent process
        )
    
    # Run the analyzer and pass through its exit code
    analyzer_path = Path(__file__).parent / "analyze_changes.py"
    result = subprocess.run(
        [sys.executable, str(analyzer_path)],
        stdin=sys.stdin,  # Pass stdin from hook
        capture_output=True,
        text=True
    )
    
    # Pass through stdout and stderr
    if result.stdout:
        print(result.stdout, end='')
    if result.stderr:
        print(result.stderr, end='', file=sys.stderr)
    
    # Exit with the same code as the analyzer
    sys.exit(result.returncode)

if __name__ == "__main__":
    main()