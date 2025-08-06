# KittenTTS Audio Feedback for Claude Code

An intelligent audio feedback system that enhances Claude Code with real-time voice notifications for code quality issues and task completions.

## Features

- **Real-time Code Analysis**: Automatically reviews code changes and provides contextual suggestions
- **Audio Notifications**: Hear feedback through text-to-speech using the lightweight KittenTTS model
- **Smart Batching**: Prevents audio spam by intelligently grouping multiple rapid edits
- **Long Message Support**: Automatically splits lengthy feedback into manageable chunks
- **Configurable**: Customize voices, models, and behavior through environment variables
- **Dual Feedback**: Provides both audio playback for developers and text feedback to Claude Code
- **MCP Integration**: Claude can speak directly to users via Model Context Protocol

## How It Works

1. **File Edit Detection**: Hooks monitor code changes in real-time
2. **AI Analysis**: Claude analyzes diffs using non-interactive mode
3. **Smart Queuing**: Tips are batched to avoid overwhelming audio
4. **TTS Generation**: KittenTTS converts feedback to natural speech
5. **Seamless Playback**: Audio plays while you continue coding

## Quick Start

See [GETTING_STARTED.md](GETTING_STARTED.md) for installation and setup instructions.

For MCP integration (allowing Claude to speak directly), see [MCP_SETUP.md](MCP_SETUP.md).

## Requirements

- Python 3.8+
- Claude Code CLI
- PulseAudio (for WSL2/Linux audio playback)
- ~500MB disk space for TTS model

## Configuration

Edit `.env` to customize:
- TTS model and voice selection
- Batch timing for grouped feedback
- Logging preferences
- Audio player backend

## Project Structure

```
.claude/
├── analyze_changes.py       # Code analysis hook
├── announce_task.py         # Task completion announcer
├── process_tips.py          # Background audio processor
├── review_code.py           # Unified review handler
├── config.py                # Configuration loader
├── settings.json.example    # Example hook configuration
└── settings.local.json      # Your hook configuration

.env.example                 # Configuration template
mcp_server.py                # MCP server for Claude integration
claude_desktop_config.json   # Example config for Claude Desktop
```

## License

MIT

## Dependencies & Acknowledgments

This project uses the following open source libraries:

- **[KittenTTS](https://github.com/KittenML/kitten-tts)** - Ultra-lightweight 15M parameter TTS model for fast, high-quality speech synthesis
- **[MCP (Model Context Protocol)](https://github.com/modelcontextprotocol/python-sdk)** - Protocol for Claude integrations and tool interactions
- **[Claude Code CLI](https://github.com/anthropics/claude-code)** - Official CLI for Claude by Anthropic

### Python Libraries
- `soundfile` - Audio file I/O
- `numpy` - Numerical operations for audio processing
- `python-dotenv` - Environment variable management
- Standard library: `logging`, `asyncio`, `subprocess`, `json`