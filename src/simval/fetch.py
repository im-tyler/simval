"""Fetch structures from the free public databases (RCSB PDB, AlphaFold DB).

These are data *sources*, not a database to replicate — simval verifies
*simulations*; this just lowers the friction of getting a starting structure
by ID. Local-first is preserved: this is an explicit one-time fetch the user
requests, not background phone-home."""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path


def _classify(identifier: str) -> str:
    if len(identifier) == 4 and identifier.isalnum():
        return "pdb"
    return "alphafold"


def fetch_structure(identifier: str, out_dir, *, source: str | None = None) -> dict:
    src = source or _classify(identifier)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    if src == "pdb":
        url = f"https://files.rcsb.org/download/{identifier.upper()}.pdb"
        name = f"{identifier}.pdb"
    elif src == "alphafold":
        api = f"https://alphafold.ebi.ac.uk/api/prediction/{identifier.upper()}"
        with urllib.request.urlopen(api, timeout=30) as r:
            meta = json.load(r)[0]
        url = meta["pdbUrl"]
        name = f"AF-{identifier}.pdb"
    else:
        raise ValueError(f"unknown source: {source!r} (use 'pdb' or 'alphafold')")

    dest = out / name
    try:
        urllib.request.urlretrieve(url, dest)
    except Exception as e:
        raise FileNotFoundError(f"fetch failed for {identifier!r} ({src}): {e}") from e
    return {"source": src, "id": identifier, "path": str(dest), "url": url,
            "bytes": dest.stat().st_size}
