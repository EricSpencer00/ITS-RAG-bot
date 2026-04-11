#!/usr/bin/env python3
"""Isolated PersonaPlex load + warmup smoke test.

Runs the model-load + warmup path *outside* uvicorn so a crash here
gives us a real Python stack trace via faulthandler instead of taking
down the whole server. Use this whenever PP segfaults.

Usage:
    .venv311/bin/python scripts/diagnose_personaplex.py            # auto device
    .venv311/bin/python scripts/diagnose_personaplex.py --device cpu
    .venv311/bin/python scripts/diagnose_personaplex.py --device mps
    .venv311/bin/python scripts/diagnose_personaplex.py --skip-warmup
"""
from __future__ import annotations

import argparse
import faulthandler
import os
import sys
import time
import traceback

# Enable native crash → Python traceback BEFORE importing torch / moshi.
faulthandler.enable(file=sys.stderr, all_threads=True)


def banner(msg: str) -> None:
    print(f"\n{'=' * 60}\n  {msg}\n{'=' * 60}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--device",
        choices=["auto", "cpu", "mps", "cuda"],
        default="auto",
        help="torch device to load PersonaPlex on (default: auto-detect)",
    )
    parser.add_argument(
        "--skip-warmup",
        action="store_true",
        help="Load the models but don't run the torch warmup loop",
    )
    args = parser.parse_args()

    banner("Environment")
    import platform
    import torch

    print(f"Python:         {sys.version.split()[0]}")
    print(f"Platform:       {platform.platform()}")
    print(f"Torch:          {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    mps_avail = hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
    print(f"MPS available:  {mps_avail}")

    requested = "" if args.device == "auto" else args.device
    if requested:
        os.environ["PERSONAPLEX_DEVICE"] = requested
        print(f"PERSONAPLEX_DEVICE forced to: {requested}")

    banner("Importing native deps")
    try:
        import sphn  # noqa: F401
        print("sphn:           OK")
    except Exception as e:  # pragma: no cover
        print(f"sphn:           FAILED — {e}")
        return 2
    try:
        import moshi  # noqa: F401
        print(f"moshi:          OK ({getattr(moshi, '__version__', 'unknown')})")
    except Exception as e:  # pragma: no cover
        print(f"moshi:          FAILED — {e}")
        return 2

    banner("Constructing PersonaPlexEngine")
    from app.voice.personaplex import PersonaPlexEngine, torch_auto_device
    from app.config import HF_REPO, HF_TOKEN, PERSONAPLEX_CPU_OFFLOAD, VOICE_PROMPT_DIR

    device = torch_auto_device(requested or None)
    print(f"Resolved device: {device}")

    engine = PersonaPlexEngine(
        device=requested or None,
        hf_repo=HF_REPO,
        hf_token=HF_TOKEN,
        cpu_offload=PERSONAPLEX_CPU_OFFLOAD,
        voice_prompt_dir=VOICE_PROMPT_DIR,
    )

    if args.skip_warmup:
        # Manually exercise the load steps without warmup, so we can see
        # exactly which load step crashes.
        banner("Load: mimi codec")
        t0 = time.time()
        mimi_w = engine.loader.download_file(engine.loader.MIMI_NAME)
        engine._mimi = engine.loader.get_mimi(mimi_w, engine.device)
        engine._other_mimi = engine.loader.get_mimi(mimi_w, engine.device)
        print(f"  ok ({time.time() - t0:.1f}s)")

        banner("Load: text tokenizer")
        t0 = time.time()
        engine._text_tokenizer = engine.loader.get_text_tokenizer()
        print(f"  ok ({time.time() - t0:.1f}s)")

        banner("Load: voice prompts directory")
        t0 = time.time()
        engine.voice_prompt_dir = engine.loader.get_voice_prompts_dir(engine.voice_prompt_dir)
        print(f"  ok ({time.time() - t0:.1f}s) — {engine.voice_prompt_dir}")

        banner("Load: PersonaPlex LM")
        t0 = time.time()
        moshi_w = engine.loader.download_file(engine.loader.MOSHI_NAME)
        engine._lm = engine.loader.get_moshi_lm(moshi_w, engine.device, engine.cpu_offload)
        engine._lm.eval()
        print(f"  ok ({time.time() - t0:.1f}s)")

        print("\nLoad complete (warmup skipped). Engine is ready in-process.")
        return 0

    banner("Running PersonaPlexEngine.initialize() (load + warmup)")
    import asyncio
    t0 = time.time()
    try:
        asyncio.run(engine.initialize())
    except Exception:
        print("\nERROR during initialize():")
        traceback.print_exc()
        return 1
    print(f"\nFull init succeeded in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
