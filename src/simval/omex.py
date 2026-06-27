"""OMEX (COMBINE archive) export.

Packages a run's provenance + artifacts into a COMBINE archive (.omex) -- the
reproducibility standard used by Biosimulations / RunBioSimulations and many
journals. A first version: manifest.xml + provenance.json + the run's artifacts.
Gets simval output into the FAIR/reproducibility ecosystem."""
from __future__ import annotations

import zipfile
from pathlib import Path


def _content_manifest(artifacts: list[str]) -> str:
    entries = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<omexManifest xmlns="http://identifiers.org/combine/specifications/omex-version-1">']
    fmt = {
        "provenance.json": "application/json",
        "methods.json": "application/json",
    }
    for name in artifacts:
        format_uri = fmt.get(name, "application/octet-stream")
        if name.endswith(".json"):
            format_uri = "application/json"
        elif name.endswith((".mdp", ".xml")):
            format_uri = "text/plain"
        entries.append(f'  <content location="{name}" format="{format_uri}" />')
    entries.append("</omexManifest>")
    return "\n".join(entries) + "\n"


def export_omex(run_dir, out_path) -> dict:
    run = Path(run_dir)
    if not run.is_dir():
        raise FileNotFoundError(f"run-dir not found: {run}")

    keep = ("provenance.json", "methods.json", "mdout.mdp", "params.json",
            "thresholds.json")
    keep_suffix = (".xtc", ".dcd", ".gro", ".pdb", ".xvg", ".top", ".json", ".mdp")
    artifacts = []
    for f in sorted(run.iterdir()):
        if not f.is_file():
            continue
        if f.name in keep or f.suffix in keep_suffix:
            if f.stat().st_size < 8_000_000:  # skip very large trajectories for the archive
                artifacts.append(f.name)

    if "provenance.json" not in artifacts and (run / "provenance.json").exists():
        artifacts.insert(0, "provenance.json")

    out = Path(out_path)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.xml", _content_manifest(artifacts))
        for name in artifacts:
            z.write(run / name, name)
    return {"path": str(out), "entries": ["manifest.xml"] + artifacts,
            "bytes": out.stat().st_size}
