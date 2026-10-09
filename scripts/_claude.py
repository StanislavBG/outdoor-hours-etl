"""Single pinned entry point for shelling out to `claude -p`."""
from __future__ import annotations

import os
import subprocess

CLAUDE_MODEL = os.environ.get("OUTDOOR_HOURS_CLAUDE_MODEL", "claude-haiku-4-5-20251001")


def run_claude(prompt: str, *, timeout: int = 120) -> str:
    r = subprocess.run(
        ["claude", "-p", "--model", CLAUDE_MODEL],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if r.returncode != 0:
        raise RuntimeError(f"claude -p failed rc={r.returncode}: {r.stderr[:200]}")
    return r.stdout.strip()
