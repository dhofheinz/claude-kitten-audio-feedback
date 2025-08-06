#!/usr/bin/env python3
import json
import sys
import os
import subprocess
from pathlib import Path
from datetime import datetime
import time
import fcntl
import logging
from logging.handlers import RotatingFileHandler

# Load configuration
sys.path.insert(0, os.path.dirname(__file__))
from config import load_config
config = load_config()

# Configuration from env
BATCH_WAIT_TIME = config['BATCH_WAIT_TIME']
QUEUE_FILE = "/tmp/claude_code_tips_queue.json"
LOCK_FILE = "/tmp/claude_code_tips.lock"
ENABLE_LOGGING = config['ENABLE_LOGGING']
MAX_LOG_SIZE = config.get('MAX_LOG_SIZE', 5 * 1024 * 1024)  # Default 5MB
BACKUP_COUNT = config.get('LOG_BACKUP_COUNT', 3)  # Keep 3 old logs

def setup_logger(name, log_file):
    """Setup a rotating logger with size limits"""
    logger = logging.getLogger(name)
    
    # Only add handler if logger doesn't have any handlers yet
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        
        # Create rotating file handler
        handler = RotatingFileHandler(
            log_file,
            maxBytes=MAX_LOG_SIZE,
            backupCount=BACKUP_COUNT
        )
        handler.setLevel(logging.DEBUG)
        
        # Create formatter
        formatter = logging.Formatter('%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        handler.setFormatter(formatter)
        
        # Add handler to logger
        logger.addHandler(handler)
    
    return logger

def log_message(message, logger=None):
    """Log message if logging is enabled"""
    if not ENABLE_LOGGING or not logger:
        return
    try:
        logger.info(message)
    except:
        pass

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

# Main script starts here
try:
    input_data = json.load(sys.stdin)
except:
    sys.exit(0)

# Check if this is a Write, Edit, or MultiEdit tool
tool_name = input_data.get("tool_name", "")
if tool_name not in ["Write", "Edit", "MultiEdit"]:
    sys.exit(0)

# Get the file path and content
tool_input = input_data.get("tool_input", {})
file_path = tool_input.get("file_path", "")

if not file_path:
    sys.exit(0)

# Get the changes based on tool type
change_description = ""
if tool_name == "Write":
    change_description = f"Created new file: {file_path}"
elif tool_name == "Edit":
    change_description = f"Edited {file_path}"
elif tool_name == "MultiEdit":
    num_edits = len(tool_input.get("edits", []))
    change_description = f"Made {num_edits} edits to {file_path}"

# Get full context for better code reviews
diff_context = ""
try:
    if tool_name == "Write":
        # For Write, include the full new file content
        content = tool_input.get("content", "")
        diff_context = f"New file content:\n```\n{content}\n```"
    elif tool_name == "Edit":
        # For Edit, include full old and new strings
        old_str = tool_input.get("old_string", "")
        new_str = tool_input.get("new_string", "")
        diff_context = f"Changed from:\n```\n{old_str}\n```\n\nTo:\n```\n{new_str}\n```"
    elif tool_name == "MultiEdit":
        # For MultiEdit, show all edits with full strings
        edits = tool_input.get("edits", [])
        if edits:
            diff_context = f"Made {len(edits)} changes:\n"
            for i, edit in enumerate(edits, 1):
                old = edit.get("old_string", "")
                new = edit.get("new_string", "")
                diff_context += f"\nEdit {i}:\nFrom:\n```\n{old}\n```\nTo:\n```\n{new}\n```\n"
except:
    pass

# Use Claude to analyze the change
try:
    # Load the prompt template from config
    prompt_template = config.get('REVIEW_PROMPT', 'Review this code change and respond with "GOOD" or a short tip.')
    
    # Format the prompt with the actual values
    prompt = prompt_template.format(
        file_path=file_path,
        change_description=change_description,
        diff_context=f"Change details:\n{diff_context}" if diff_context else ""
    )

    # Setup logging if enabled
    logger = None
    if ENABLE_LOGGING:
        project_dir = os.environ.get('CLAUDE_PROJECT_DIR', Path(__file__).parent.parent)
        log_dir = Path(project_dir) / config['LOG_DIR']
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "analyze_changes.log"
        logger = setup_logger('analyze_changes', str(log_file))

        log_message("=== ANALYZE CHANGES LOG ===", logger)
        log_message(f"File: {file_path}", logger)
        log_message(f"Tool: {tool_name}", logger)
        log_message("=== PROMPT SENT TO CLAUDE ===", logger)
        log_message(prompt, logger)

    # Call Claude
    claude_result = subprocess.run(
        [
            "claude", "-p", prompt,
            "--model", config['CLAUDE_MODEL'],
            "--allowedTools", "Read", "Grep", "Glob",
            "--max-turns", str(config['CLAUDE_MAX_TURNS'])
        ],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=os.path.dirname(file_path) if file_path else None
    )

    # Log response if enabled
    if ENABLE_LOGGING and logger:
        log_message("=== CLAUDE'S RAW RESPONSE ===", logger)
        log_message(f"Return code: {claude_result.returncode}", logger)
        log_message(f"Stdout: {claude_result.stdout if claude_result.stdout else '(empty)'}", logger)
        log_message(f"Stderr: {claude_result.stderr if claude_result.stderr else '(empty)'}", logger)

    if claude_result.returncode == 0 and claude_result.stdout:
        response = claude_result.stdout.strip().strip('"\'')

        if ENABLE_LOGGING and logger:
            log_message("=== PROCESSED RESPONSE ===", logger)
            log_message(f"Cleaned response: {response}", logger)
            log_message(f"Is GOOD?: {response.upper() == 'GOOD'}", logger)

        # Filter out error messages from Claude
        if "Error: Reached max turns" in response:
            if ENABLE_LOGGING and logger:
                log_message("Decision: Ignoring max turns error", logger)
            sys.exit(0)
        
        # If it's not GOOD, add to the queue and notify Claude
        if response.upper() != "GOOD":
            # Only add to audio queue if audio feedback is enabled
            if config.get('ENABLE_AUDIO_FEEDBACK', True):
                # Acquire lock
                lock = acquire_lock()
                if lock:
                    try:
                        # Load current queue
                        queue_data = load_queue()
                        current_time = time.time()

                        # Add the new tip
                        queue_data["tips"].append(response)
                        queue_data["last_update"] = current_time

                        if ENABLE_LOGGING and logger:
                            if len(queue_data["tips"]) == 1:
                                log_message(f"Decision: Added first tip to queue, waiting {BATCH_WAIT_TIME}s for more", logger)
                            else:
                                log_message(f"Decision: Added tip to queue ({len(queue_data['tips'])} total)", logger)

                        # Save updated queue
                        save_queue(queue_data)

                    finally:
                        release_lock(lock)
            elif ENABLE_LOGGING and logger:
                log_message("Decision: Audio feedback disabled, not adding to queue", logger)

            # Return the tip to Claude as text feedback if enabled (exit code 2 shows stderr to Claude)
            if config.get('ENABLE_TEXT_FEEDBACK', True):
                print(f"💡 Code review tip: {response}", file=sys.stderr)
                sys.exit(2)
            elif ENABLE_LOGGING and logger:
                log_message("Decision: Text feedback disabled, not returning to Claude", logger)
        else:
            if ENABLE_LOGGING and logger:
                log_message("Decision: GOOD code, no tip needed", logger)
    else:
        if ENABLE_LOGGING and logger:
            log_message("Decision: Claude failed, assuming good code", logger)

except Exception as e:
    # Log error if enabled
    if ENABLE_LOGGING and 'logger' in locals():
        log_message(f"ERROR: {str(e)}", logger)
    sys.exit(0)

sys.exit(0)