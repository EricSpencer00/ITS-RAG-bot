#!/bin/bash
# ITS Voice RAG Bot - Complete Testing Script
# This script verifies the entire system is working correctly

set -e

PROJECT_DIR="/Users/eric/GitHub/live-bot-its"
cd "$PROJECT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}ITS Voice RAG Bot - Complete System Test${NC}"
echo -e "${BLUE}================================================${NC}\n"

# Activate virtual environment
echo -e "${YELLOW}Step 1: Activating virtual environment...${NC}"
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
    echo -e "${GREEN}✓ Virtual environment activated${NC}\n"
else
    echo -e "${RED}✗ Virtual environment not found${NC}"
    exit 1
fi

# Run system verification
echo -e "${YELLOW}Step 2: Running system verification...${NC}"
if python verify_system.py; then
    echo -e "${GREEN}✓ System verification passed${NC}\n"
else
    echo -e "${RED}✗ System verification failed${NC}"
    exit 1
fi

# Check if model files exist
echo -e "${YELLOW}Step 3: Checking model files...${NC}"
HF_CACHE_DIR="$HOME/.cache/huggingface/hub/models--nvidia--personaplex-7b-v1"
if [ -d "$HF_CACHE_DIR" ]; then
    echo -e "${GREEN}✓ Model cache directory found${NC}"
    
    # Check for specific model files
    if find "$HF_CACHE_DIR" -name "model.safetensors" -o -name "tokenizer-e351c8d8-checkpoint125.safetensors" | grep -q .; then
        echo -e "${GREEN}✓ Model files detected${NC}\n"
    else
        echo -e "${YELLOW}⚠ Model files still downloading (this is normal on first run)${NC}"
        echo -e "${YELLOW}  The server will wait for downloads to complete.${NC}\n"
    fi
else
    echo -e "${YELLOW}⚠ Model cache not yet downloaded${NC}"
    echo -e "${YELLOW}  The server will download on startup.${NC}\n"
fi

# Check Python version
echo -e "${YELLOW}Step 4: Verifying Python version...${NC}"
PYTHON_VERSION=$(python --version 2>&1 | awk '{print $2}')
echo -e "  Python version: $PYTHON_VERSION"
REQUIRED_VERSION="3.14"
if [[ "$PYTHON_VERSION" == "$REQUIRED_VERSION"* ]] || [[ "$PYTHON_VERSION" == "3."[5-9]* ]] || [[ "$PYTHON_VERSION" == "3.1"[0-9]* ]]; then
    echo -e "${GREEN}✓ Python version compatible${NC}\n"
else
    echo -e "${YELLOW}⚠ Python 3.14+ recommended (you have $PYTHON_VERSION)${NC}\n"
fi

# Check key dependencies
echo -e "${YELLOW}Step 5: Checking key dependencies...${NC}"
for package in torch aiohttp fastapi sphn faiss sentence_transformers; do
    if python -c "import $package" 2>/dev/null; then
        VERSION=$(python -c "import $package; print(getattr($package, '__version__', 'installed'))")
        echo -e "  ${GREEN}✓${NC} $package ($VERSION)"
    else
        echo -e "  ${RED}✗${NC} $package (missing)"
    fi
done
echo ""

# Check environment variables
echo -e "${YELLOW}Step 6: Checking environment variables...${NC}"
if [ -z "$HF_TOKEN" ]; then
    echo -e "  ${YELLOW}⚠${NC} HF_TOKEN not set (reading from .env)"
    if grep -q "HF_TOKEN" .env 2>/dev/null; then
        echo -e "  ${GREEN}✓${NC} HF_TOKEN found in .env"
    else
        echo -e "  ${RED}✗${NC} HF_TOKEN not found in .env (required for gated model access)"
    fi
else
    echo -e "  ${GREEN}✓${NC} HF_TOKEN is set"
fi
echo ""

# Summary and next steps
echo -e "${BLUE}================================================${NC}"
echo -e "${GREEN}✓ All checks completed${NC}"
echo -e "${BLUE}================================================${NC}\n"

echo -e "${YELLOW}Next Steps:${NC}\n"
echo -e "1. Start the server:"
echo -e "   ${BLUE}python scripts/run_dev.py${NC}\n"

echo -e "2. Wait for 'Engine initialized' message${NC}\n"

echo -e "3. Open in browser:"
echo -e "   ${BLUE}https://localhost:8998${NC}\n"

echo -e "4. Test the voice agent:"
echo -e "   - Click 'Start Conversation'"
echo -e "   - Wait for 'Connected' status"
echo -e "   - Speak naturally into your microphone"
echo -e "   - Listen for agent response\n"

echo -e "${YELLOW}Troubleshooting:${NC}\n"
echo -e "- Check console output for errors"
echo -e "- Ensure microphone is enabled in browser"
echo -e "- Try different voice prompts if audio is silent"
echo -e "- Verify GPU has sufficient VRAM (10GB+ required)\n"

echo -e "${BLUE}Full documentation available in:${NC}"
echo -e "- VOICE_RAG_INTEGRATION.md"
echo -e "- README-PERSONAPLEX.md"
echo -e "- FIX_SUMMARY.md\n"
