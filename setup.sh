#!/bin/bash
# Complete setup script for KittenTTS Audio Feedback

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo -e "${GREEN}=== KittenTTS Audio Feedback Setup ===${NC}"
echo ""

# Step 1: Check Python version
echo -e "${YELLOW}[1/5] Checking Python version...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python 3 is not installed${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
REQUIRED_VERSION="3.8"
if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo -e "${RED}Error: Python $REQUIRED_VERSION or higher is required (found $PYTHON_VERSION)${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python $PYTHON_VERSION found${NC}"

# Step 2: Create virtual environment
echo -e "${YELLOW}[2/5] Setting up Python virtual environment...${NC}"
if [ ! -d "tts_venv" ]; then
    python3 -m venv tts_venv
    echo -e "${GREEN}✓ Virtual environment created${NC}"
else
    echo -e "${GREEN}✓ Virtual environment already exists${NC}"
fi

# Activate virtual environment
source tts_venv/bin/activate

# Step 3: Install dependencies
echo -e "${YELLOW}[3/5] Installing dependencies...${NC}"
pip install --quiet --upgrade pip

# Install from requirements.txt
echo "  Installing dependencies from requirements.txt..."
pip install --quiet -r requirements.txt

echo -e "${GREEN}✓ All dependencies installed${NC}"

# Step 4: Create .env file if it doesn't exist
echo -e "${YELLOW}[4/5] Setting up configuration...${NC}"
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo -e "${GREEN}✓ Created .env configuration file${NC}"
    echo -e "  ${YELLOW}You can edit .env to customize voices and settings${NC}"
else
    echo -e "${GREEN}✓ Configuration file already exists${NC}"
fi

# Create logs directory
mkdir -p .claude/logs

# Step 5: Set up Claude Code hooks (optional)
echo -e "${YELLOW}[5/5] Setting up Claude Code integration...${NC}"

# Create local settings if not exists
if [ ! -f ".claude/settings.local.json" ]; then
    cp .claude/settings.json.example .claude/settings.local.json
    echo -e "${GREEN}✓ Created Claude Code hook settings${NC}"
else
    echo -e "${GREEN}✓ Hook settings already configured${NC}"
fi

echo ""
echo -e "${GREEN}=== Setup Complete! ===${NC}"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo ""
echo "1. For audio feedback on code changes:"
echo "   Run: ./setup_mcp.sh"
echo ""
echo "2. Test the audio system:"
echo "   Run: ./test_audio.sh"
echo ""
echo -e "${GREEN}Enjoy your grizzled code reviews! 🔊${NC}"