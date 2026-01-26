#!/usr/bin/env python3
"""Test script to verify voice prompt download."""

import os
os.environ['PYO3_USE_ABI3_FORWARD_COMPATIBILITY'] = '1'

from app.voice.personaplex import PersonaPlexLoader
from app.config import HF_TOKEN, HF_REPO

print("Testing PersonaPlex voice prompt download...")
print(f"HF_TOKEN: {'set' if HF_TOKEN else 'NOT SET'}")
print(f"HF_REPO: {HF_REPO}")

loader = PersonaPlexLoader(HF_REPO, HF_TOKEN)

print("\nDownloading voices.tgz...")
try:
    voices_dir = loader.get_voice_prompts_dir(None)
    print(f"✓ Voices directory: {voices_dir}")
    
    # List voice files
    from pathlib import Path
    voice_files = list(Path(voices_dir).glob("*.pt"))
    print(f"✓ Found {len(voice_files)} voice prompts:")
    for vf in sorted(voice_files):
        print(f"  - {vf.name}")
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
