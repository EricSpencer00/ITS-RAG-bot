#!/usr/bin/env python3
"""
PersonaPlex Setup Script

This script helps set up the ITS Voice RAG Bot with NVIDIA PersonaPlex.

Requirements:
- Python 3.10+
- NVIDIA GPU with CUDA support (recommended)
- HuggingFace account with PersonaPlex license accepted

Usage:
    python scripts/setup_personaplex.py [--cpu-only]
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path


def run_command(cmd: list[str], description: str) -> bool:
    """Run a command and return success status."""
    print(f"\n{'='*60}")
    print(f"  {description}")
    print(f"{'='*60}")
    
    try:
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        return False
    except FileNotFoundError:
        print(f"Error: Command not found: {cmd[0]}")
        return False


def check_python_version():
    """Check Python version is 3.10+."""
    version = sys.version_info
    if version < (3, 10):
        print(f"Error: Python 3.10+ required, found {version.major}.{version.minor}")
        sys.exit(1)
    print(f"✓ Python {version.major}.{version.minor}.{version.micro}")
    
    # PyO3 (used by sphn) currently only supports up to Python 3.13
    # For Python 3.14+, we need to set forward compatibility flag
    if version >= (3, 14):
        print("⚠️  Python 3.14+ detected: Setting PyO3 forward compatibility mode")
        os.environ['PYO3_USE_ABI3_FORWARD_COMPATIBILITY'] = '1'


def check_cuda():
    """Check CUDA availability."""
    try:
        import torch
        if torch.cuda.is_available():
            device = torch.cuda.get_device_name(0)
            print(f"✓ CUDA available: {device}")
            return True
        else:
            print("⚠ CUDA not available - will use CPU (slower)")
            return False
    except ImportError:
        print("⚠ PyTorch not installed yet")
        return False


def install_opus():
    """Install Opus codec library."""
    if sys.platform == "darwin":  # macOS
        return run_command(["brew", "install", "opus"], "Installing Opus codec (macOS)")
    elif sys.platform == "linux":
        # Try apt first, then dnf
        if Path("/usr/bin/apt").exists():
            return run_command(["sudo", "apt", "install", "-y", "libopus-dev"], 
                             "Installing Opus codec (Ubuntu/Debian)")
        elif Path("/usr/bin/dnf").exists():
            return run_command(["sudo", "dnf", "install", "-y", "opus-devel"],
                             "Installing Opus codec (Fedora/RHEL)")
    else:
        print("⚠ Please install Opus codec manually for your platform")
        return False
    return True


def install_requirements():
    """Install Python requirements."""
    req_file = Path(__file__).parent.parent / "requirements-personaplex.txt"
    if not req_file.exists():
        print(f"Error: {req_file} not found")
        return False
    
    return run_command(
        [sys.executable, "-m", "pip", "install", "-r", str(req_file)],
        "Installing Python dependencies"
    )


def clone_personaplex():
    """Clone the PersonaPlex repository."""
    dest = Path(__file__).parent.parent / "personaplex"
    
    if dest.exists():
        print(f"✓ PersonaPlex already cloned at {dest}")
        return True
    
    return run_command(
        ["git", "clone", "https://github.com/NVIDIA/personaplex.git", str(dest)],
        "Cloning PersonaPlex repository"
    )


def install_moshi():
    """Install the moshi package from PersonaPlex."""
    moshi_path = Path(__file__).parent.parent / "personaplex" / "moshi"
    
    if not moshi_path.exists():
        print(f"Error: {moshi_path} not found. Run clone first.")
        return False
    
    return run_command(
        [sys.executable, "-m", "pip", "install", str(moshi_path)],
        "Installing moshi package"
    )


def setup_hf_token():
    """Guide user to set up HuggingFace token."""
    print("\n" + "="*60)
    print("  HuggingFace Token Setup")
    print("="*60)
    
    token = os.environ.get("HF_TOKEN", "")
    
    if token:
        print(f"✓ HF_TOKEN is set (starts with: {token[:10]}...)")
    else:
        print("""
To use PersonaPlex, you need a HuggingFace token:

1. Go to https://huggingface.co/settings/tokens
2. Create a new token (or use existing one)
3. Accept the PersonaPlex license at:
   https://huggingface.co/nvidia/personaplex-7b-v1
4. Set the token:
   
   export HF_TOKEN=your_token_here
   
   Or add to your .env file:
   
   echo "HF_TOKEN=your_token_here" >> .env
""")
        return False
    
    return True


def create_env_file():
    """Create a sample .env file."""
    env_file = Path(__file__).parent.parent / ".env.example"
    
    content = """# ITS Voice RAG Bot - PersonaPlex Configuration

# HuggingFace token (required)
# Get yours at: https://huggingface.co/settings/tokens
# Must accept license at: https://huggingface.co/nvidia/personaplex-7b-v1
HF_TOKEN=

# Device configuration
# Options: "cuda", "cpu", or specific device like "cuda:0"
PERSONAPLEX_DEVICE=cuda

# Enable CPU offloading for systems with limited GPU memory
# Requires 'accelerate' package
PERSONAPLEX_CPU_OFFLOAD=false

# Default voice prompt (NATF0-3, NATM0-3, VARF0-4, VARM0-4)
DEFAULT_VOICE_PROMPT=NATF2

# Default text prompt / persona
DEFAULT_TEXT_PROMPT=You are a helpful ITS support assistant. You help users with technology questions clearly and friendly.

# Server configuration
HOST=0.0.0.0
PORT=8998

# RAG configuration (optional, for document retrieval)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
"""
    
    env_file.write_text(content)
    print(f"✓ Created {env_file}")
    print("  Copy to .env and fill in your HF_TOKEN")
    
    return True


def main():
    parser = argparse.ArgumentParser(description="Set up PersonaPlex for ITS Voice RAG Bot")
    parser.add_argument("--cpu-only", action="store_true", 
                       help="Skip CUDA check (for CPU-only systems)")
    parser.add_argument("--skip-clone", action="store_true",
                       help="Skip cloning PersonaPlex repo")
    args = parser.parse_args()
    
    print("""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║     ITS Voice RAG Bot - PersonaPlex Setup                    ║
║                                                              ║
║     Full-duplex speech-to-speech powered by                  ║
║     NVIDIA PersonaPlex-7B                                    ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
""")
    
    # Check Python version
    check_python_version()
    
    # Install Opus codec
    if not install_opus():
        print("⚠ Failed to install Opus. You may need to install it manually.")
    
    # Install Python requirements
    if not install_requirements():
        print("Error: Failed to install Python requirements")
        sys.exit(1)
    
    # Check CUDA
    if not args.cpu_only:
        check_cuda()
    
    # Clone PersonaPlex
    if not args.skip_clone:
        if not clone_personaplex():
            print("Error: Failed to clone PersonaPlex")
            sys.exit(1)
    
    # Install moshi package
    if not install_moshi():
        print("Error: Failed to install moshi package")
        sys.exit(1)
    
    # Create sample .env file
    create_env_file()
    
    # Check HF token
    setup_hf_token()
    
    print("""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║     Setup Complete!                                          ║
║                                                              ║
║     Next steps:                                              ║
║     1. Copy .env.example to .env                             ║
║     2. Add your HuggingFace token to .env                    ║
║     3. Run: python -m app.main                               ║
║                                                              ║
║     The first run will download the model (~14GB)            ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    main()
