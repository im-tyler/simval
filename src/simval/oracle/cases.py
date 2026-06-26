from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_REFERENCES_DIR = Path(__file__).parent / "references"


@dataclass
class ReferenceCase:
    name: str
    description: str
    engine: str
    force_field: str
    selection: str
    reference_metrics: dict
    tolerances: dict
    source: str
    source_hash: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "engine": self.engine,
            "force_field": self.force_field,
            "selection": self.selection,
            "reference_metrics": self.reference_metrics,
            "tolerances": self.tolerances,
            "source": self.source,
            "source_hash": self.source_hash,
        }


def _load(path: Path) -> ReferenceCase:
    d = json.loads(path.read_text())
    return ReferenceCase(
        name=d["name"],
        description=d.get("description", ""),
        engine=d.get("engine", "gromacs"),
        force_field=d.get("force_field", ""),
        selection=d.get("selection", "protein and name CA"),
        reference_metrics=d["reference_metrics"],
        tolerances=d.get("tolerances", {}),
        source=d.get("source", ""),
        source_hash=d.get("source_hash", ""),
    )


def list_cases() -> list[str]:
    if not _REFERENCES_DIR.exists():
        return []
    return sorted(p.stem for p in _REFERENCES_DIR.glob("*.json"))


def get_case(name: str) -> ReferenceCase:
    path = _REFERENCES_DIR / f"{name}.json"
    if not path.exists():
        raise KeyError(f"unknown reference case: {name!r}; available: {list_cases()}")
    return _load(path)


def load_all() -> dict[str, ReferenceCase]:
    if not _REFERENCES_DIR.exists():
        return {}
    return {p.stem: _load(p) for p in _REFERENCES_DIR.glob("*.json")}
