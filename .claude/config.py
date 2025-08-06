#!/usr/bin/env python3
"""Configuration loader for Claude Code hooks"""
import os
from pathlib import Path

def load_config():
    """Load configuration from .env file or use defaults"""
    config = {}
    
    # Get project directory
    project_dir = os.environ.get('CLAUDE_PROJECT_DIR', Path(__file__).parent.parent)
    env_file = Path(project_dir) / '.env'
    
    # Default values
    defaults = {
        'ENABLE_LOGGING': 'false',
        'LOG_DIR': '.claude/logs',
        'MAX_LOG_SIZE': '5242880',  # 5MB in bytes
        'LOG_BACKUP_COUNT': '3',     # Keep 3 old log files
        'ENABLE_AUDIO_FEEDBACK': 'true',
        'ENABLE_TEXT_FEEDBACK': 'true',
        'TTS_MODEL': 'KittenML/kitten-tts-nano-0.1',
        'TTS_VOICE': 'expr-voice-2-m',
        'TTS_SAMPLE_RATE': '24000',
        'BATCH_WAIT_TIME': '3',
        'CLAUDE_MODEL': 'sonnet',
        'CLAUDE_MAX_TURNS': '3',
        'CLAUDE_TIMEOUT': '60',
        'AUDIO_PLAYER': 'paplay'
    }
    
    # Load from .env if exists
    if env_file.exists():
        with open(env_file, 'r') as f:
            content = f.read()
            
        # Parse the .env file handling multi-line values
        lines = content.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                
                # Check if this is a multi-line value (starts with quote)
                if value.startswith('"'):
                    # Collect all lines until we find the closing quote
                    full_value = value[1:]  # Remove opening quote
                    i += 1
                    while i < len(lines) and not full_value.endswith('"'):
                        full_value += '\n' + lines[i]
                        i += 1
                    # Remove closing quote
                    if full_value.endswith('"'):
                        full_value = full_value[:-1]
                    config[key] = full_value
                else:
                    config[key] = value
            i += 1
    
    # Apply defaults for missing values
    for key, default_value in defaults.items():
        if key not in config:
            config[key] = default_value
    
    # Convert types with safe fallbacks
    config['ENABLE_LOGGING'] = config['ENABLE_LOGGING'].lower() == 'true'
    config['ENABLE_AUDIO_FEEDBACK'] = config['ENABLE_AUDIO_FEEDBACK'].lower() == 'true'
    config['ENABLE_TEXT_FEEDBACK'] = config['ENABLE_TEXT_FEEDBACK'].lower() == 'true'
    
    # Safe integer conversions with fallbacks to defaults
    try:
        config['MAX_LOG_SIZE'] = int(config['MAX_LOG_SIZE'])
    except (ValueError, TypeError):
        config['MAX_LOG_SIZE'] = 5242880  # 5MB default
    
    try:
        config['LOG_BACKUP_COUNT'] = int(config['LOG_BACKUP_COUNT'])
    except (ValueError, TypeError):
        config['LOG_BACKUP_COUNT'] = 3
    
    try:
        config['TTS_SAMPLE_RATE'] = int(config['TTS_SAMPLE_RATE'])
    except (ValueError, TypeError):
        config['TTS_SAMPLE_RATE'] = 24000
    
    try:
        config['BATCH_WAIT_TIME'] = int(config['BATCH_WAIT_TIME'])
    except (ValueError, TypeError):
        config['BATCH_WAIT_TIME'] = 3
    
    try:
        config['CLAUDE_MAX_TURNS'] = int(config['CLAUDE_MAX_TURNS'])
    except (ValueError, TypeError):
        config['CLAUDE_MAX_TURNS'] = 3
    
    try:
        config['CLAUDE_TIMEOUT'] = int(config['CLAUDE_TIMEOUT'])
    except (ValueError, TypeError):
        config['CLAUDE_TIMEOUT'] = 60
    
    return config