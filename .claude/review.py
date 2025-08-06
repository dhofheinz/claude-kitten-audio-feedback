#!/usr/bin/env python3
"""Unified code review with integrated audio and text feedback"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import fcntl
import logging
import subprocess
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, Optional, Tuple

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))
from config import load_config  # type: ignore[import-not-found]

# ----------------------------
# Configuration & Constants
# ----------------------------

config = load_config()

QUEUE_FILE = Path("/tmp/claude_code_tips_queue.json")
LOCK_FILE = Path("/tmp/claude_code_tips.lock")
PROCESS_PID_FILE = Path("/tmp/claude_tips_processor.pid")
PROCESS_LOCK_FILE = Path("/tmp/claude_tips_processor.lock")

ENABLE_LOGGING: bool = bool(config.get("ENABLE_LOGGING", False))
MAX_LOG_SIZE: int = int(config.get("MAX_LOG_SIZE", 5 * 1024 * 1024))
BACKUP_COUNT: int = int(config.get("LOG_BACKUP_COUNT", 3))
BATCH_WAIT_TIME: float = float(config.get("BATCH_WAIT_TIME", 0.0))  # reserved

CLAUDE_MODEL: str = str(config.get("CLAUDE_MODEL", "claude-sonnet-4-20250514"))
CLAUDE_MAX_TURNS: int = int(config.get("CLAUDE_MAX_TURNS", 3))
CLAUDE_TIMEOUT: int = int(config.get("CLAUDE_TIMEOUT", 60))
REVIEW_PROMPT: str = str(
    config.get("REVIEW_PROMPT", 'Review this code change and respond with "GOOD" or a short tip.')
)

ENABLE_AUDIO_FEEDBACK: bool = bool(config.get("ENABLE_AUDIO_FEEDBACK", True))
ENABLE_TEXT_FEEDBACK: bool = bool(config.get("ENABLE_TEXT_FEEDBACK", True))

GOOD_RE = re.compile(r"^\s*GOOD\s*[!.,:\-]?(?:\s|$)", re.IGNORECASE)


# ----------------------------
# Logging
# ----------------------------

def setup_logger(name: str, log_file: Path) -> logging.Logger:
    """Setup a rotating logger with size limits."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    handler = RotatingFileHandler(str(log_file), maxBytes=MAX_LOG_SIZE, backupCount=BACKUP_COUNT)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def log_message(message: str, logger: Optional[logging.Logger] = None) -> None:
    """Log message if logging is enabled."""
    if ENABLE_LOGGING and logger:
        try:
            logger.info(message)
        except Exception:
            pass


# ----------------------------
# File locking helpers
# ----------------------------

def acquire_lock(lock_file_path: Path, timeout: float = 5.0):
    """Acquire a file lock to prevent race conditions. Returns an open file or None on timeout."""
    lock_file = open(lock_file_path, "a+")  # avoid truncation
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


# ----------------------------
# Process helpers
# ----------------------------

def is_process_running(pid: int) -> bool:
    """Check if a process with given PID is running."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _read_pid_file(pid_file: Path) -> Optional[int]:
    if not pid_file.exists():
        return None
    try:
        pid = int(pid_file.read_text().strip())
        return pid if is_process_running(pid) else None
    except Exception:
        return None


def _atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def ensure_audio_processor_running(logger: Optional[logging.Logger] = None) -> Optional[int]:
    """Ensure the background audio processor is running; return PID if running/launched."""
    if not ENABLE_AUDIO_FEEDBACK:
        return None

    # If already running, return PID
    pid = _read_pid_file(PROCESS_PID_FILE)
    if pid:
        return pid

    # Launch guarded by a lock to avoid thundering herd
    lock = acquire_lock(PROCESS_LOCK_FILE, timeout=1.0)
    if not lock:
        # Another process is launching it; best-effort no-op
        return _read_pid_file(PROCESS_PID_FILE)

    try:
        # Double-check after acquiring lock
        pid = _read_pid_file(PROCESS_PID_FILE)
        if pid:
            return pid

        processor_script = Path(__file__).parent / "process.py"
        project_dir = Path(__file__).parent.parent
        venv_python = project_dir / "tts_venv" / "bin" / "python3"

        # Choose Python executable
        python_exe = sys.executable
        if venv_python.exists() and venv_python.is_file():
            try:
                test = subprocess.run(
                    [str(venv_python), "-c", "import sys; sys.exit(0)"],
                    capture_output=True,
                    timeout=2,
                )
                if test.returncode == 0:
                    python_exe = str(venv_python)
            except Exception:
                pass

        env = os.environ.copy()
        env["CLAUDE_PROJECT_DIR"] = str(project_dir)

        proc = subprocess.Popen(  # noqa: S603
            [python_exe, str(processor_script)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=env,
        )

        _atomic_write_text(PROCESS_PID_FILE, str(proc.pid))
        log_message(f"Audio processor started with PID {proc.pid}", logger)
        return proc.pid
    finally:
        release_lock(lock)


# ----------------------------
# Queue helpers
# ----------------------------

def _load_queue() -> Dict[str, Any]:
    if not QUEUE_FILE.exists():
        return {"tips": [], "last_update": 0}
    try:
        return json.loads(QUEUE_FILE.read_text())
    except Exception:
        return {"tips": [], "last_update": 0}


def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data))
    os.replace(tmp, path)


def add_tip_to_queue(tip: str) -> bool:
    """Add a tip to the audio queue atomically."""
    lock = acquire_lock(LOCK_FILE)
    if not lock:
        return False
    try:
        queue_data = _load_queue()
        queue_data.setdefault("tips", []).append(tip)
        queue_data["last_update"] = time.time()
        _atomic_write_json(QUEUE_FILE, queue_data)
        return True
    finally:
        release_lock(lock)


# ----------------------------
# Code change analysis
# ----------------------------

def _build_diff_context(tool_name: str, tool_input: Dict[str, Any]) -> str:
    if tool_name == "Write":
        content = tool_input.get("content", "")
        return f"New file content:\n```\n{content}\n```"
    if tool_name == "Edit":
        old_str = tool_input.get("old_string", "")
        new_str = tool_input.get("new_string", "")
        return f"Changed from:\n```\n{old_str}\n```\n\nTo:\n```\n{new_str}\n```"
    if tool_name == "MultiEdit":
        edits = tool_input.get("edits", [])
        if not edits:
            return ""
        parts = [f"Made {len(edits)} changes:"]
        for i, edit in enumerate(edits, 1):
            old = edit.get("old_string", "")
            new = edit.get("new_string", "")
            parts.append(f"\nEdit {i}:\nFrom:\n```\n{old}\n```\nTo:\n```\n{new}\n```")
        return "\n".join(parts)
    return ""


def _change_description(tool_name: str, file_path: str, tool_input: Dict[str, Any]) -> str:
    if tool_name == "Write":
        return f"Created new file: {file_path}"
    if tool_name == "Edit":
        return f"Edited {file_path}"
    if tool_name == "MultiEdit":
        num_edits = len(tool_input.get("edits", []))
        return f"Made {num_edits} edits to {file_path}"
    return ""


def _format_prompt(file_path: str, change_description: str, diff_context: str) -> str:
    # Be resilient to missing placeholders in custom templates.
    safe_map = {
        "file_path": file_path,
        "change_description": change_description,
        "diff_context": f"Change details:\n{diff_context}" if diff_context else "",
    }
    try:
        return REVIEW_PROMPT.format(**safe_map)
    except Exception:
        # Fallback to default if custom template is incompatible
        return (
            f"{REVIEW_PROMPT}\n\n"
            f"File: {file_path}\n{change_description}\n\n"
            f"{safe_map['diff_context']}"
        )


def _call_claude(prompt: str, cwd: Optional[str], logger: Optional[logging.Logger]) -> Tuple[int, str, str]:
    args = [
        "claude",
        "-p",
        prompt,
        "--model",
        CLAUDE_MODEL,
        "--allowedTools",
        "Read",
        "Grep",
        "Glob",
        "--max-turns",
        str(CLAUDE_MAX_TURNS),
    ]
    
    # Optionally add verbose flag for debugging
    if config.get("CLAUDE_VERBOSE", False):
        args.append("--verbose")
    try:
        result = subprocess.run(  # noqa: S603
            args,
            stdout=subprocess.PIPE,
            stderr=None,  # Inherit stderr directly from parent process
            text=True,
            timeout=CLAUDE_TIMEOUT,
            cwd=cwd,
        )
    except FileNotFoundError as e:
        # Explicit error to help debugging if CLI not available
        log_message(f"ERROR: claude CLI not found: {e}", logger)
        return 127, "", str(e)
    except subprocess.TimeoutExpired as e:
        log_message(f"ERROR: claude timed out after {CLAUDE_TIMEOUT}s", logger)
        return 124, "", str(e)
    except Exception as e:
        log_message(f"ERROR invoking claude: {e}", logger)
        return 1, "", str(e)

    if ENABLE_LOGGING and logger:
        log_message("=== CLAUDE'S RAW RESPONSE ===", logger)
        log_message(f"Return code: {result.returncode}", logger)
        log_message(f"Stdout: {result.stdout if result.stdout else '(empty)'}", logger)
        # Note: stderr now goes directly to parent process stderr

    return result.returncode, result.stdout or "", ""  # Empty string for stderr since we don't capture it


def analyze_code_change(input_data: Dict[str, Any], logger: Optional[logging.Logger] = None) -> Tuple[Optional[str], Optional[bool]]:
    """Analyze the code change and return (tip, has_tip)."""

    tool_name = str(input_data.get("tool_name", ""))
    if tool_name not in {"Write", "Edit", "MultiEdit"}:
        return None, None

    tool_input = input_data.get("tool_input") or {}
    file_path = str(tool_input.get("file_path", "")).strip()
    if not file_path:
        return None, None

    change_description = _change_description(tool_name, file_path, tool_input)
    diff_context = _build_diff_context(tool_name, tool_input)

    prompt = _format_prompt(file_path, change_description, diff_context)

    if ENABLE_LOGGING and logger:
        log_message("=== ANALYZE CHANGES ===", logger)
        log_message(f"File: {file_path}", logger)
        log_message(f"Tool: {tool_name}", logger)
        log_message("=== PROMPT SENT TO CLAUDE ===", logger)
        log_message(prompt, logger)

    rc, stdout, _stderr = _call_claude(prompt, cwd=os.path.dirname(file_path) if file_path else None, logger=logger)
    if rc != 0 or not stdout:
        return None, None

    response = stdout.strip().strip("\"'")
    if ENABLE_LOGGING and logger:
        log_message("=== PROCESSED RESPONSE ===", logger)
        log_message(f"Cleaned response: {response}", logger)

    # Filter out control errors
    if "Error: Reached max turns" in response:
        log_message("Decision: Ignoring max turns error", logger)
        return None, None

    is_good = bool(GOOD_RE.match(response))
    if ENABLE_LOGGING and logger:
        preview = response[:80].replace("\n", "\\n")
        log_message(f"Response pattern check: '{preview}...' is_good={is_good}", logger)

    if is_good:
        log_message("Decision: GOOD code, no tip needed", logger)
        return None, None

    return response, True


# ----------------------------
# Main
# ----------------------------

def main() -> None:
    """Main entry point for unified review."""
    # Safety check: Verify CLAUDE_PROJECT_DIR is set
    project_dir_env = os.environ.get("CLAUDE_PROJECT_DIR")
    if not project_dir_env:
        # No project directory set - exit silently
        sys.exit(0)
    
    # Use the actual script location instead of assuming path
    # This makes it resilient to script being moved or symlinked
    current_script = Path(__file__).resolve()
    if not current_script.exists():
        # Something very wrong if we can't find ourselves
        sys.exit(0)
    
    logger: Optional[logging.Logger] = None

    if ENABLE_LOGGING:
        project_dir = Path(project_dir_env)
        log_dir = Path(project_dir) / str(config.get("LOG_DIR", "logs"))
        log_dir.mkdir(parents=True, exist_ok=True)
        logger = setup_logger("review", log_dir / "review.log")

    try:
        try:
            input_data = json.load(sys.stdin)
        except Exception:
            # No/invalid input -> no-op success
            sys.exit(0)

        tip, has_tip = analyze_code_change(input_data, logger)

        if has_tip and tip:
            if ENABLE_AUDIO_FEEDBACK:
                try:
                    ensure_audio_processor_running(logger)
                    if add_tip_to_queue(tip):
                        log_message("Decision: Added tip to audio queue", logger)
                except Exception as e:
                    log_message(f"Audio processor error: {e}", logger)

            if ENABLE_TEXT_FEEDBACK:
                feedback_msg = f"💡 Code review tip: {tip}"
                log_message(f"Decision: Sending text feedback to Claude: {feedback_msg}", logger)
                log_message("About to exit with code 2", logger)
                print(feedback_msg, file=sys.stderr)
                sys.stderr.flush()
                sys.exit(2)  # Exit code 2 sends stderr to Claude

    except Exception as e:
        log_message(f"ERROR: {e}", logger)

    sys.exit(0)


if __name__ == "__main__":
    main()
