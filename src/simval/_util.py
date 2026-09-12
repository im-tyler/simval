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


# --- MD input roles (audit GROM-001) -------------------------------------
#
# A normal GROMACS run-dir carries a structure (.gro/.pdb), a run topology
# (.tpr), and possibly an Amber/CHARMM topology (.prmtop/.psf) — these are
# ROLES, not mutually-exclusive alternatives. Only multiple candidates for
# the SAME role are ambiguous. When several roles can serve as the
# trajectory topology, the precedence below is deterministic and documented.

STRUCTURE_PATTERNS = ("*.gro", "*.pdb")
RUN_TOPOLOGY_PATTERNS = ("*.tpr",)
ALTERNATE_TOPOLOGY_PATTERNS = ("*.prmtop", "*.psf")
TRAJECTORY_PATTERNS = ("*.xtc", "*.dcd", "*.trr", "*.nc")


def select_structure(run: Path):
    """Structure role (.gro/.pdb): exactly one, or None."""
    return find_unique(run, *STRUCTURE_PATTERNS, what="structure")


def select_run_topology(run: Path):
    """Run-topology role (.tpr): exactly one, or None."""
    return find_unique(run, *RUN_TOPOLOGY_PATTERNS, what="run topology (tpr)")


def select_alternate_topology(run: Path):
    """Amber/CHARMM topology role (.prmtop/.psf): exactly one, or None."""
    return find_unique(run, *ALTERNATE_TOPOLOGY_PATTERNS, what="topology (prmtop/psf)")


def select_trajectory_topology(run: Path):
    """Topology used to load the trajectory.

    Documented precedence: structure (.gro/.pdb) > run topology (.tpr) >
    Amber/CHARMM (.prmtop/.psf). Ambiguity is only an error WITHIN a role.
    """
    for select in (select_structure, select_run_topology, select_alternate_topology):
        hit = select(run)
        if hit is not None:
            return hit
    return None
