from __future__ import annotations

import re
from pathlib import Path

_WATER_ITP = {
    "tip3p.itp": "TIP3P",
    "tip4p.itp": "TIP4P",
    "tip5p.itp": "TIP5P",
    "spc.itp": "SPC",
    "spce.itp": "SPC/E",
}


def parse_mdp(path) -> dict[str, str]:
    out: dict[str, str] = {}
    for ln in Path(path).read_text().splitlines():
        s = ln.split(";", 1)[0].strip()
        if not s or "=" not in s:
            continue
        k, _, v = s.partition("=")
        out[k.strip()] = v.strip()
    return out


def extract_force_field(top_path) -> str | None:
    if not top_path or not Path(top_path).exists():
        return None
    txt = Path(top_path).read_text(errors="ignore")
    m = re.search(r'#include\s+"([^"/]+\.ff)/forcefield\.itp"', txt)
    return m.group(1) if m else None


def extract_water_model(top_path) -> str | None:
    if not top_path or not Path(top_path).exists():
        return None
    txt = Path(top_path).read_text(errors="ignore")
    for itp, name in _WATER_ITP.items():
        if itp in txt:
            return name
    return None


def build_metadata(mdp_path=None, top_path=None, gmx_version: str | None = None) -> dict:
    meta: dict = {
        "force_field": None,
        "water_model": None,
        "gmx_version": gmx_version,
        "mdp": {},
    }
    if mdp_path and Path(mdp_path).exists():
        meta["mdp"] = parse_mdp(mdp_path)
    if top_path:
        meta["force_field"] = extract_force_field(top_path)
        meta["water_model"] = extract_water_model(top_path)
    return meta


def production_duration_ps(mdp: dict) -> str:
    dt = mdp.get("dt")
    nsteps = mdp.get("nsteps")
    try:
        ps = float(dt) * float(nsteps)
        if ps >= 1000:
            return f"{ps / 1000:.2f} ns"
        return f"{ps:.1f} ps"
    except (TypeError, ValueError):
        return f"{nsteps} steps"


def render_methods(meta: dict) -> str:
    m = meta.get("mdp", {})
    ff = meta.get("force_field") or "the selected force field"
    water = meta.get("water_model") or "the selected water model"
    gmx = f"GROMACS {meta['gmx_version']}" if meta.get("gmx_version") else "GROMACS"
    integrator = m.get("integrator", "md")
    dt = m.get("dt", "?")
    constraints = m.get("constraints", "none")
    coulomb = m.get("coulombtype", "?")
    rcoul = m.get("rcoulomb", "?")
    tcoupl = m.get("tcoupl", "no")
    ref_t = m.get("ref_t", "?")
    pcoupl = m.get("pcoupl", "no")
    seed = m.get("gen_seed", "n/a")

    ensemble = []
    ensemble.append("NVE" if tcoupl == "no" else f"NVT ({tcoupl} thermostat, {ref_t} K)")
    if pcoupl != "no":
        ensemble.append(f"NPT ({pcoupl} barostat)")

    return (
        f"MD was performed with {gmx} using the {ff} force field and {water} water. "
        f"Integration: {integrator}, dt = {dt} ps, constraints = {constraints}. "
        f"Electrostatics: {coulomb} (rcoulomb = {rcoul} nm). "
        f"Ensemble: {', '.join(ensemble)}. "
        f"Production length: {production_duration_ps(m)} (gen_seed {seed})."
    )
