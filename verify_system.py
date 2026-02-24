#!/usr/bin/env python3
"""
Verification script for ITS Voice RAG Bot - PersonaPlex Edition

Tests core functionality without requiring full model download/inference.
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

def check_imports():
    """Verify all critical imports are available."""
    print("Checking imports...")
    try:
        import torch
        print(f"  ✓ torch {torch.__version__}")
        
        import aiohttp
        print(f"  ✓ aiohttp")
        
        import fastapi
        print(f"  ✓ fastapi")
        
        import sphn
        print(f"  ✓ sphn (Opus support)")
        
        import sentence_transformers
        print(f"  ✓ sentence_transformers")
        
        import faiss
        print(f"  ✓ faiss")
        
        import sentencepiece
        print(f"  ✓ sentencepiece")
        
        print("✓ All imports successful\n")
        return True
    except ImportError as e:
        print(f"✗ Import failed: {e}\n")
        return False


def check_config():
    """Verify configuration is loaded correctly."""
    print("Checking configuration...")
    try:
        from app.config import (
            HOST, PORT, DEFAULT_VOICE_PROMPT, HF_TOKEN,
            PERSONAPLEX_DEVICE, RAG_TOP_K, OLLAMA_MODEL,
            HF_CHAT_MODEL, HF_API_URL
        )
        
        print(f"  ✓ HOST: {HOST}")
        print(f"  ✓ PORT: {PORT}")
        print(f"  ✓ Voice: {DEFAULT_VOICE_PROMPT}")
        print(f"  ✓ Device: {PERSONAPLEX_DEVICE}")
        print(f"  ✓ RAG top-k: {RAG_TOP_K}")
        print(f"  ✓ LLM: {OLLAMA_MODEL}")
        if HF_CHAT_MODEL:
            print(f"  ✓ HF chat model: {HF_CHAT_MODEL} (via {HF_API_URL})")
        
        if HF_TOKEN:
            print(f"  ✓ HF_TOKEN: {'*' * 10}...{HF_TOKEN[-4:]}")
        else:
            print(f"  ⚠ HF_TOKEN: Not set (gated model access may fail)")
        
        print("✓ Configuration loaded\n")
        return True
    except Exception as e:
        print(f"✗ Configuration error: {e}\n")
        return False


def check_rag_system():
    """Verify RAG system components are available."""
    print("Checking RAG system...")
    try:
        from app.rag.retriever import Retriever
        from app.conversation.controller import handle_user_text
        from app.conversation.state import ConversationState
        
        print(f"  ✓ Retriever")
        print(f"  ✓ Conversation controller")
        print(f"  ✓ Conversation state")
        
        # Try to instantiate retriever (won't load if no data)
        try:
            retriever = Retriever()
            print(f"  ✓ Retriever initialized ({retriever.index.ntotal} documents indexed)")
        except Exception as e:
            print(f"  ⚠ Retriever: {e} (data ingestion may be needed)")
        
        print("✓ RAG system ready\n")
        return True
    except Exception as e:
        print(f"✗ RAG system error: {e}\n")
        return False


def check_voice_system():
    """Verify voice system components are available."""
    print("Checking voice system...")
    try:
        from app.voice.personaplex import (
            PersonaPlexLoader, PersonaPlexSession, PersonaPlexEngine
        )
        
        print(f"  ✓ PersonaPlexLoader")
        print(f"  ✓ PersonaPlexSession")
        print(f"  ✓ PersonaPlexEngine")
        
        # Verify loader can find model files
        loader = PersonaPlexLoader()
        print(f"  ✓ Using repo: {loader.hf_repo}")
        print(f"  ✓ Model filenames:")
        print(f"    - Mimi: {loader.MIMI_NAME}")
        print(f"    - Moshi: {loader.MOSHI_NAME}")
        print(f"    - Tokenizer: {loader.TEXT_TOKENIZER_NAME}")
        
        print("✓ Voice system ready\n")
        return True
    except Exception as e:
        print(f"✗ Voice system error: {e}\n")
        return False


def check_web_ui():
    """Verify web UI files are present."""
    print("Checking web UI files...")
    try:
        files = [
            "app/web/static/index.html",
            "app/web/static/app.js",
            "app/web/static/styles.css",
        ]
        
        for file_path in files:
            path = Path(file_path)
            if path.exists():
                size = path.stat().st_size
                print(f"  ✓ {file_path} ({size} bytes)")
            else:
                print(f"  ✗ {file_path} (missing)")
                return False
        
        print("✓ Web UI files ready\n")
        return True
    except Exception as e:
        print(f"✗ Web UI check error: {e}\n")
        return False


def main():
    """Run all checks."""
    print("\n" + "="*70)
    print("ITS Voice RAG Bot - PersonaPlex Edition")
    print("System Verification")
    print("="*70 + "\n")
    
    checks = [
        check_imports,
        check_config,
        check_rag_system,
        check_voice_system,
        check_web_ui,
    ]
    
    results = []
    for check in checks:
        try:
            results.append(check())
        except Exception as e:
            print(f"Check failed with exception: {e}\n")
            results.append(False)
    
    # Summary
    passed = sum(results)
    total = len(results)
    
    print("="*70)
    print(f"Verification Results: {passed}/{total} checks passed")
    print("="*70)
    
    if all(results):
        print("\n✓ System is ready! Start the server with:")
        print("  python scripts/run_dev.py\n")
        return 0
    else:
        print("\n✗ Some checks failed. Review the errors above.\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
