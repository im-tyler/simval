"""FreeSolv experimental hydration free-energy database (642 compounds, CC-BY).

The reference-library moat: 642 citable, open, experimental ΔG values with
uncertainties. A candidate FEP/computed ΔG is validated against the experimental
ground truth for the compound -- the most credible reference anchor available.

Source: MobleyLab/FreeSolv (doi:10.5281/zenodo.1161245), CC-BY-4.0.
"""
from __future__ import annotations

import json
from pathlib import Path

from simval.result import DiagnosticResult

_DB: dict | None = None


def _load() -> dict:
    global _DB
    if _DB is None:
        _DB = json.loads((Path(__file__).parent / "data" / "freesolv.json").read_text())
    return _DB


def list_compounds() -> list[str]:
    return sorted(_load().keys())


def lookup(compound_id: str) -> dict:
    db = _load()
    if compound_id not in db:
        raise KeyError(f"unknown FreeSolv compound: {compound_id!r}")
    e = db[compound_id]
    return {
        "compound_id": compound_id,
        "iupac": e.get("iupac", "").strip(),
        "smiles": e.get("smiles", ""),
        "expt_dG_kcal_mol": float(e["expt"]),
        "expt_uncertainty": float(e.get("d_expt", 0.5) or 0.5),
    }


def search(name: str, *, limit: int = 10) -> list[dict]:
    needle = name.lower()
    hits = []
    for cid, e in _load().items():
        if needle in (e.get("iupac", "") + e.get("nickname", "") + cid).lower():
            hits.append(lookup(cid))
            if len(hits) >= limit:
                break
    return hits


def check_against_experiment(
    computed_dG: float, compound_id: str, *, extra_tolerance: float = 0.0,
) -> DiagnosticResult:
    """Compare a computed hydration ΔG to the FreeSolv experimental value."""
    info = lookup(compound_id)
    expt = info["expt_dG_kcal_mol"]
    unc = info["expt_uncertainty"] + extra_tolerance
    deviation = computed_dG - expt
    passed = abs(deviation) <= unc
    return DiagnosticResult(
        name="freesolv_experimental",
        passed=passed,
        threshold=float(unc),
        value=float(abs(deviation)),
        detail={
            "compound_id": compound_id,
            "iupac": info["iupac"],
            "computed_dG_kcal_mol": float(computed_dG),
            "experimental_dG_kcal_mol": expt,
            "experimental_uncertainty": info["expt_uncertainty"],
            "deviation_kcal_mol": float(deviation),
            "tolerance_kcal_mol": unc,
            "note": "within experimental uncertainty" if passed else "outside experimental uncertainty",
        },
    )
