# KittenTTS MCP Integration

This guide explains how to set up KittenTTS as an MCP (Model Context Protocol) server, allowing Claude to speak directly to users.

## What is MCP?

MCP (Model Context Protocol) is a protocol that allows Claude to interact with external tools and services. With KittenTTS MCP, Claude can:
- Speak messages directly to users
- Make announcements with different tones
- Provide audio code reviews
- Use different voices and personalities

## Setup Instructions

### 1. Install MCP Dependencies

The MCP package should already be installed, but if not:

```bash
./tts_venv/bin/pip install mcp
```

### 2. Add to Claude Code

Run this command in your terminal to add KittenTTS as an MCP server:

```bash
claude mcp add kitten-tts --scope user -- /home/danie/projects/tools/kitten/tts_venv/bin/python /home/danie/projects/tools/kitten/mcp_server.py
```

Or run the setup script:
```bash
./setup_mcp.sh
```

This adds KittenTTS as a user-scoped server, making it available across all your projects.

### 3. Verify Installation

In Claude Code, check that the server is connected:

```
/mcp
```

You should see "kitten-tts" listed as an available server.

## Available MCP Tools

Once configured, Claude will have access to these tools:

### `speak`
Converts text to speech with customizable voice and personality.

```
Parameters:
- text: The text to speak (required)
- voice: Voice selection (optional)
- personality: Speaking style - grizzled, friendly, professional, zen
```

Example: "Please speak 'Hello, I'm Claude' in a friendly voice"

### `announce`
Makes announcements with appropriate tone.

```
Parameters:
- message: The announcement message (required)
- tone: success, warning, info, or error
```

Example: "Announce that the build completed successfully"

### `code_review`
Speaks code review feedback in the grizzled engineer voice.

```
Parameters:
- feedback: The code review feedback (required)
```

Example: "Give me audio feedback about this SQL injection vulnerability"

## Usage Examples

Once set up, you can ask Claude to:

1. **Speak directly to you:**
   "Can you speak this message: 'Your code review is complete'"

2. **Make announcements:**
   "Announce that all tests are passing with a success tone"

3. **Provide audio code reviews:**
   "Give me an audio code review about the security issues you found"

4. **Use different personalities:**
   "Speak 'Time for a code review' in your grizzled engineer voice"

## Troubleshooting

### MCP Server Not Starting

1. Check that the paths in your config are correct
2. Ensure Python virtual environment is activated
3. Verify MCP package is installed: `./tts_venv/bin/pip list | grep mcp`

### No Audio Playing

1. Test audio manually first:
   ```bash
   ./tts_venv/bin/python -c "from kittentts import KittenTTS; m = KittenTTS('KittenML/kitten-tts-nano-0.1'); import soundfile as sf; audio = m.generate('Test', voice='expr-voice-2-m'); sf.write('/tmp/test.wav', audio, 24000)"
   paplay /tmp/test.wav
   ```

2. Check your `.env` configuration for correct audio player

### Tool Not Available in Claude

1. Ensure MCP server is listed in Claude's config
2. Restart Claude Desktop completely
3. Check Claude's developer console for any MCP errors

## Advanced Configuration

### Custom Voices

Edit `.env` to set default voice:
```
TTS_VOICE=expr-voice-3-f
```

Available voices:
- expr-voice-2-m/f (Standard)
- expr-voice-3-m/f (Cheerful)
- expr-voice-4-m/f (Serious)
- expr-voice-5-m/f (Concerned)

### Custom Personalities

You can modify the personality modifications in `mcp_server.py` to add your own speaking styles.

## Security Note

The MCP server runs locally and only Claude Desktop can access it. No data is sent to external servers except for the initial model download from HuggingFace.