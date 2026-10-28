"""Checks both Groq models (primary + fallback).   python scripts/test_llm.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.llm import get_llm

for tier in ("primary", "fallback"):
    try:
        print(f"[{tier}] ->", get_llm(tier).call("Reply with one short Bangla sentence: API কী?"))
    except Exception as exc:
        print(f"[{tier}] FAILED: {exc}")
