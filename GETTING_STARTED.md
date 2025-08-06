# Getting Started

This guide will help you set up the KittenTTS audio feedback system for Claude Code.

## Prerequisites

1. **Claude Code CLI** installed and configured
2. **Python 3.8+** with pip
3. **Audio support**:
   - WSL2: Ensure WSLg is configured for audio
   - Linux: PulseAudio or ALSA installed
   - macOS: Core Audio (built-in)

## Installation

### Automatic Setup (Recommended)

```bash
git clone https://github.com/dhofheinz/claude-kitten-audio-feedback.git
cd claude-kitten-audio-feedback
./setup.sh  # Does everything for you
```

This script will:
- Check Python version (3.8+ required)
- Create virtual environment
- Install all dependencies (KittenTTS, MCP, etc.)
- Set up configuration files
- Create necessary directories

### Manual Setup

If you prefer to set things up manually:

#### 1. Clone the Repository

```bash
git clone https://github.com/dhofheinz/claude-kitten-audio-feedback.git
cd claude-kitten-audio-feedback
```

#### 2. Create Virtual Environment

```bash
python3 -m venv tts_venv
source tts_venv/bin/activate  # On Windows: tts_venv\Scripts\activate
```

#### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

Or install manually:
```bash
pip install kittentts soundfile numpy mcp python-dotenv
```

The first run will automatically download the TTS model (~500MB).

#### 4. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` to customize settings:

```bash
# Core settings
TTS_MODEL=KittenML/kitten-tts-nano-0.1
TTS_VOICE=expr-voice-2-m
TTS_SAMPLE_RATE=24000

# Batching (seconds to wait before speaking grouped tips)
BATCH_WAIT_TIME=3

# Claude analysis settings
CLAUDE_MODEL=sonnet
CLAUDE_MAX_TURNS=3

# Debug logging
ENABLE_LOGGING=false
```

### 5. Configure Claude Settings

Copy the example settings to your project:

```bash
cp .claude/settings.json.example .claude/settings.local.json
```

Or if you have existing settings, add the hooks manually:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "$CLAUDE_PROJECT_DIR/.claude/review.py",
            "timeout": 15
          }
        ]
      }
    ]
  }
}
```

## Testing the Setup

### 1. Test TTS Audio

```bash
./test_audio.sh  # Automated test script
```

Or manually:
```bash
python3 -c "from kittentts import KittenTTS; m = KittenTTS('KittenML/kitten-tts-nano-0.1'); import soundfile as sf; audio = m.generate('Hello, audio feedback is working!', voice='expr-voice-2-m'); sf.write('/tmp/test.wav', audio, 24000)"
paplay /tmp/test.wav
```

### 2. Test with Claude Code

Start Claude Code in your project:

```bash
claude
```

Create a test file with an issue:

```python
# Create test.py
def bad_function(x):
    query = f"SELECT * FROM users WHERE id = {x}"  # SQL injection
    return query
```

You should hear audio feedback about the security issue!

## Troubleshooting

### No Audio on WSL2

1. Check WSLg audio support:
```bash
pactl info
```

2. Test audio directly:
```bash
speaker-test -t wav -c 2
```

3. Ensure PulseAudio is running:
```bash
pulseaudio --start
```

### Tips Not Playing

1. Enable logging in `.env`:
```bash
ENABLE_LOGGING=true
```

2. Check logs:
```bash
tail -f .claude/logs/review.log
```

3. Verify queue processing:
```bash
cat /tmp/claude_code_tips_queue.json
```

### Model Download Issues

If the model fails to download, manually cache it:

```python
from kittentts import KittenTTS
m = KittenTTS("KittenML/kitten-tts-nano-0.1")
```

## Customization

### Different Voices

Available voices in kitten-tts-nano-0.1:
- `expr-voice-1-f` - Female voice 1
- `expr-voice-2-m` - Male voice 2 (default)
- `expr-voice-3-f` - Female voice 3

### Disable Specific Hooks

Comment out or remove unwanted hooks in `.claude/settings.local.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      // Commented out to disable
      // {
      //   "matcher": "Write|Edit|MultiEdit",
      //   "hooks": [...]
      // }
    ]
  }
}
```

### Adjust Batching Time

In `.env`, change `BATCH_WAIT_TIME` (in seconds):
- Lower values: Faster feedback, more interruptions
- Higher values: Grouped feedback, fewer interruptions

## Next Steps

- Adjust code review prompts in `.env` file's `REVIEW_PROMPT`
- Customize the review logic in `.claude/review.py`
- Add new hooks for other Claude Code events
- Experiment with different TTS models from KittenML

## Support

For issues or questions, please open an issue on GitHub.