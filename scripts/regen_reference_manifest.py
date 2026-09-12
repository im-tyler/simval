#!/usr/bin/env python3
"""Regenerate src/simval/oracle/references/MANIFEST.json (audit GOLD-002).

The manifest pins every shipped golden's canonical-content sha256 so a
reference edited in place fails closed at load time instead of flowing
silently into verdicts. The manifest is the pinned artifact itself; it
is regenerated only deliberately, by running this script after an
intentional golden change, and the diff is reviewed with that change.

Usage (repo root):
    python3 scripts/regen_reference_manifest.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from simval.oracle import cases


def main() -> int:
    references = cases._REFERENCES_DIR
    manifest_path = references / cases._MANIFEST_NAME
    entries: dict[str, str] = {}
    for path in sorted(references.glob("*.json")):
        if path.name == cases._MANIFEST_NAME:
            continue
        d = json.loads(path.read_text())
        name = d["name"]
        if name != path.stem:
            raise ValueError(f"{path.name}: golden 'name' {name!r} != file stem — refusing to pin")
        if name in entries:
            raise ValueError(f"duplicate golden name {name!r}")
        entries[name] = cases.reference_digest(d)
    if not entries:
        raise ValueError(f"no reference goldens found under {references}")
    manifest_path.write_text(json.dumps(entries, indent=2, sort_keys=True) + "\n")
    print(f"{manifest_path.relative_to(REPO_ROOT)}: pinned {len(entries)} references")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
