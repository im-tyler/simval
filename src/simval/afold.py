"""AlphaFold confidence (pLDDT) as a verification prior.

Fetches AlphaFold's per-residue predicted confidence for a UniProt id and surfaces
expected-flexibility regions before you simulate -- low pLDDT regions are where
AlphaFold itself is unsure, i.e. where a simulation is most likely to show
mobility or artefacts. This turns a public database into a verification prior
(on-wedge), not a structure lookup."""
from __future__ import annotations

from pathlib import Path

from simval.result import DiagnosticResult


def fetch_plddt(uniprot_id: str, cache_dir=".") -> tuple[list[float], Path]:
    """Fetch the AlphaFold model for `uniprot_id`; return (per-residue pLDDT, pdb_path).
    pLDDT is stored in the B-factor (tempfactor) column of the CA atoms."""
    import MDAnalysis as mda

    from simval.fetch import fetch_structure

    info = fetch_structure(uniprot_id, cache_dir, source="alphafold")
    u = mda.Universe(info["path"])
    ca = u.select_atoms("name CA")
    return list(float(x) for x in ca.tempfactors), Path(info["path"])


def check_plddt_profile(plddt, *, low_threshold: float = 70.0, warn_mean: float = 70.0) -> DiagnosticResult:
    """Summarise structural confidence. Flags an overall-low-confidence structure
    (mean pLDDT < warn_mean) as a warning -- a sim of a structure AlphaFold is
    unsure about will likely show artefacts in the flagged regions."""
    p = list(plddt)
    n = len(p)
    mean = sum(p) / n if n else 0.0
    below = [i for i, v in enumerate(p) if v < low_threshold]
    very_low = [i for i, v in enumerate(p) if v < 50.0]
    return DiagnosticResult(
        name="plddt_confidence",
        passed=mean >= warn_mean,
        threshold=float(warn_mean),
        value=float(mean),
        detail={
            "mean_plddt": float(mean),
            "min_plddt": float(min(p)) if p else 0.0,
            "n_residues": int(n),
            "fraction_below_70": float(sum(1 for v in p if v < 70.0) / n) if n else 0.0,
            "fraction_below_50": float(sum(1 for v in p if v < 50.0) / n) if n else 0.0,
            "fraction_above_90": float(sum(1 for v in p if v >= 90.0) / n) if n else 0.0,
            "low_confidence_residue_indices": below[:50],
            "very_low_confidence_indices": very_low[:20],
            "note": "low-pLDDT regions are expected-flexible; watch their RMSF",
        },
    )
