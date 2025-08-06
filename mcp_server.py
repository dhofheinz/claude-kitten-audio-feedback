#!/usr/bin/env python3
"""MCP Server for KittenTTS - Allows Claude to speak directly to users"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List
import tempfile
import subprocess
import numpy as np

# MCP protocol imports
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types

# Add project directory to path for config
sys.path.insert(0, str(Path(__file__).parent / ".claude"))
from config import load_config

# Load configuration
config = load_config()

class KittenTTSServer:
    """MCP Server for KittenTTS audio generation"""

    def __init__(self):
        self.server = Server("kitten-tts")
        self.setup_handlers()

    def setup_handlers(self):
        """Set up MCP protocol handlers"""

        @self.server.list_tools()
        async def handle_list_tools() -> List[types.Tool]:
            """Return available TTS tools"""
            return [
                types.Tool(
                    name="speak",
                    description="Convert text to speech and play it to the user",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "text": {
                                "type": "string",
                                "description": "The text to speak (max 400 characters per chunk)"
                            },
                            "voice": {
                                "type": "string",
                                "description": "Voice to use (optional, defaults to config)",
                                "enum": [
                                    "expr-voice-2-m", "expr-voice-2-f",
                                    "expr-voice-3-m", "expr-voice-3-f",
                                    "expr-voice-4-m", "expr-voice-4-f",
                                    "expr-voice-5-m", "expr-voice-5-f"
                                ]
                            },
                            "personality": {
                                "type": "string",
                                "description": "Speaking style: grizzled, friendly, professional, zen",
                                "enum": ["grizzled", "friendly", "professional", "zen"],
                                "default": "friendly"
                            }
                        },
                        "required": ["text"]
                    }
                ),
                types.Tool(
                    name="announce",
                    description="Make an announcement with a specific tone",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "message": {
                                "type": "string",
                                "description": "The announcement message"
                            },
                            "tone": {
                                "type": "string",
                                "description": "Tone of the announcement",
                                "enum": ["success", "warning", "info", "error"],
                                "default": "info"
                            }
                        },
                        "required": ["message"]
                    }
                ),
                types.Tool(
                    name="code_review",
                    description="Speak code review feedback in grizzled engineer voice",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "feedback": {
                                "type": "string",
                                "description": "The code review feedback to speak"
                            }
                        },
                        "required": ["feedback"]
                    }
                )
            ]

        @self.server.call_tool()
        async def handle_call_tool(
            name: str, arguments: Dict[str, Any]
        ) -> List[types.TextContent]:
            """Handle tool calls"""

            if name == "speak":
                result = await self.speak(
                    arguments.get("text", ""),
                    arguments.get("voice"),
                    arguments.get("personality", "friendly")
                )
            elif name == "announce":
                result = await self.announce(
                    arguments.get("message", ""),
                    arguments.get("tone", "info")
                )
            elif name == "code_review":
                result = await self.code_review(
                    arguments.get("feedback", "")
                )
            else:
                result = f"Unknown tool: {name}"

            return [types.TextContent(type="text", text=result)]

    async def speak(self, text: str, voice: str = None, personality: str = "friendly") -> str:
        """Convert text to speech and play it"""
        if not text:
            return "No text provided to speak"

        # Apply personality modifications to text
        if personality == "grizzled":
            if not text.startswith("Kid,") and not text.startswith("Listen,"):
                text = f"Listen kid, {text}"
            if not text.endswith("....."):
                text += "....."
        elif personality == "zen":
            text = f"Consider this: {text}"
        elif personality == "professional":
            text = f"Please note: {text}"

        # Use configured voice if not specified
        if not voice:
            voice = config.get('TTS_VOICE', 'expr-voice-2-m')

        # Split long text if needed
        chunks = self._split_text(text)

        # Generate and play audio for each chunk
        for chunk in chunks:
            await self._generate_and_play(chunk, voice)

        return f"Spoke: '{text[:50]}...'" if len(text) > 50 else f"Spoke: '{text}'"

    async def announce(self, message: str, tone: str = "info") -> str:
        """Make an announcement with appropriate tone"""
        # Add tone prefix
        prefixes = {
            "success": "Great news!",
            "warning": "Heads up:",
            "info": "Just so you know,",
            "error": "Oh no!"
        }

        full_message = f"{prefixes.get(tone, '')} {message}......"

        # Use appropriate voice for tone
        voices = {
            "success": "expr-voice-3-f",  # Cheerful female
            "warning": "expr-voice-4-m",  # Serious male
            "info": config.get('TTS_VOICE', 'expr-voice-2-m'),
            "error": "expr-voice-5-m"  # Concerned male
        }

        await self._generate_and_play(full_message, voices.get(tone))
        return f"Announced: {message}"

    async def code_review(self, feedback: str) -> str:
        """Speak code review in grizzled engineer voice"""
        # Always use grizzled personality for code reviews
        return await self.speak(feedback, voice="expr-voice-2-m", personality="grizzled")

    def _split_text(self, text: str, max_length: int = 380) -> List[str]:
        """Split text at natural boundaries"""
        if len(text) <= max_length:
            return [text]

        # Natural break points
        break_patterns = [
            (', ', ','), (' and ', ' and'), (' but ', ' but'),
            ('. ', '.'), (' - ', ' -'), ('; ', ';'), (' ', '')
        ]

        chunks = []
        remaining = text

        while len(remaining) > max_length:
            chunk_text = remaining[:max_length]
            best_break = -1
            best_pattern = None

            for pattern, _ in break_patterns:
                pos = chunk_text.rfind(pattern)
                if pos > best_break and pos > max_length * 0.5:
                    best_break = pos
                    best_pattern = pattern

            if best_break > 0:
                chunk = remaining[:best_break + len(best_pattern)].strip()
                chunks.append(chunk)
                remaining = remaining[best_break + len(best_pattern):].strip()
            else:
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

    async def _generate_and_play(self, text: str, voice: str) -> None:
        """Generate TTS audio and play it"""
        # Create script for TTS generation - using json for safe data passing
        import json
        
        script_content = '''
import sys
import json
from kittentts import KittenTTS
import soundfile as sf
import numpy as np

# Load parameters safely from stdin
params = json.loads(sys.stdin.read())

# Initialize model
m = KittenTTS(params['model'])

# Generate audio
audio = m.generate(params['text'], voice=params['voice'])

# Add minimal padding and fade
sample_rate = params['sample_rate']
padding = np.zeros(int(sample_rate * 0.05))
fade_length = int(sample_rate * 0.01)

if len(audio) > fade_length * 2:
    audio[:fade_length] *= np.linspace(0, 1, fade_length)
    audio[-fade_length:] *= np.linspace(1, 0, fade_length)

audio = np.concatenate([audio, padding])

# Save audio
sf.write(sys.argv[1], audio, sample_rate)
'''
        
        # Prepare parameters as JSON
        params = {
            'model': config['TTS_MODEL'],
            'text': text,
            'voice': voice,
            'sample_rate': config['TTS_SAMPLE_RATE']
        }

        # Create temp files
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as script_file:
            script_file.write(script_content)
            script_path = script_file.name

        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as audio_file:
            audio_path = audio_file.name

        try:
            # Get project directory and venv python
            project_dir = Path(__file__).parent
            venv_python = project_dir / "tts_venv" / "bin" / "python"

            # Run TTS generation with JSON parameters via stdin
            result = await asyncio.create_subprocess_exec(
                str(venv_python), script_path, audio_path,
                cwd=str(project_dir),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            # Send JSON parameters via stdin (communicate waits for completion)
            await result.communicate(input=json.dumps(params).encode())

            if result.returncode == 0:
                # Play audio
                player = config.get('AUDIO_PLAYER', 'paplay')
                play_result = await asyncio.create_subprocess_exec(
                    player, audio_path,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL
                )
                await play_result.wait()

        finally:
            # Clean up temp files
            try:
                Path(script_path).unlink()
                Path(audio_path).unlink()
            except:
                pass

    async def run(self):
        """Run the MCP server"""
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="kitten-tts",
                    server_version="1.0.0",
                    capabilities=self.server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={}
                    )
                )
            )

if __name__ == "__main__":
    server = KittenTTSServer()
    asyncio.run(server.run())