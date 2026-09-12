"""Internal helpers shared across modules."""
from __future__ import annotations

from pathlib import Path


def find_files(run: Path, *patterns: str):
    """First file in `run` matching any pattern (in order), or None.

    Only for detection heuristics - semantic input selection must use
    find_unique (audit IO-001)."""
    for pat in patterns:
        hit = next(run.glob(pat), None)
        if hit:
            return hit
    return None


def find_unique(run: Path, *patterns: str, what: str = "input"):
    """The exactly-one file in `run` matching any pattern (sorted for a
    deterministic error), or None when nothing matches.

    Ambiguity is an error, not a first-match: two candidate trajectories
    (or topologies) in one run-dir used to silently pick whichever the
    filesystem returned first (audit IO-001)."""
    hits = sorted({hit for pat in patterns for hit in run.glob(pat)}, key=str)
    if len(hits) > 1:
        raise ValueError(
            f"ambiguous {what}: expected exactly one match for {list(patterns)} in {run}, "
            f"found {[str(h) for h in hits]}"
        )
    return hits[0] if hits else None
