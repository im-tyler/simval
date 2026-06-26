"""Internal helpers shared across modules."""
from __future__ import annotations

from pathlib import Path


def find_files(run: Path, *patterns: str):
    """First file in `run` matching any pattern (in order), or None."""
    for pat in patterns:
        hit = next(run.glob(pat), None)
        if hit:
            return hit
    return None
