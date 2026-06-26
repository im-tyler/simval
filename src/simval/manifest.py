from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from simval import __version__
from simval.result import DiagnosticResult

SCHEMA = "simval.provenance.v1"


def compute_hashes(paths: Iterable, *, chunk: int = 1 << 16) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in paths:
        path = Path(p)
        h = hashlib.sha256()
        with path.open("rb") as f:
            for block in iter(lambda: f.read(chunk), b""):
                h.update(block)
        out[str(path)] = h.hexdigest()
    return out


def build_manifest(
    params,
    results,
    *,
    files=None,
    image_digest=None,
    notes="",
    tier2_signed_off: bool = False,
) -> dict:
    verdict = all(r.passed for r in results) if results else False
    diagnostics = [r.to_dict() if isinstance(r, DiagnosticResult) else r for r in results]
    return {
        "schema": SCHEMA,
        "simval_version": __version__,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "verdict": "pass" if verdict else "fail",
        "params": params,
        "diagnostics": diagnostics,
        "files": compute_hashes(files) if files else {},
        "image_digest": image_digest,
        "tier2_signed_off": bool(tier2_signed_off),
        "notes": notes,
    }


def write_manifest(manifest: dict, path) -> None:
    Path(path).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def load_manifest(path) -> dict:
    return json.loads(Path(path).read_text())
