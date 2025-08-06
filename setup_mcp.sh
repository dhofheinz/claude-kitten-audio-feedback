#!/bin/bash
# Setup KittenTTS as an MCP server in Claude Code

PROJECT_DIR="/home/danie/projects/tools/kitten"
VENV_PYTHON="$PROJECT_DIR/tts_venv/bin/python"

echo "Setting up KittenTTS MCP server for Claude Code..."
echo ""
echo "Run this command to add KittenTTS to Claude Code:"
echo ""
echo "claude mcp add kitten-tts --scope user -- $VENV_PYTHON $PROJECT_DIR/mcp_server.py"
echo ""
echo "This will make the following tools available:"
echo "  - speak: Convert text to speech with personality options"
echo "  - announce: Make announcements with different tones"
echo "  - code_review: Speak code review feedback in grizzled engineer voice"
echo ""
echo "After adding, use /mcp in Claude Code to check the status."