from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

_REFERENCES_DIR = Path(__file__).parent / "references"

# Supported reference-format versions: the current 0.1.x series. Anything
# else (or a missing version) fails closed — a golden of unknown vintage
# must not silently flow into verdicts.
SUPPORTED_REFERENCE_SERIES = (0, 1)

_SHA256_RE = __import__("re").compile(r"^[0-9a-f]{64}$")


def _check_identity(name: str, identity) -> dict[str, str]:
    """Scenario identity (audit ORA-003): a required, non-empty map of
    run-relative input path -> sha256(hex). A golden without identity is
    malformed and fails closed at load time."""
    if not isinstance(identity, dict) or not identity:
        raise ValueError(
            f"reference case {name!r}: golden carries no scenario 'identity' "
            "(required: {input path: sha256} for every scenario-defining input)"
        )
    bad_types = sorted(k for k, v in identity.items() if not isinstance(k, str) or not isinstance(v, str))
    if bad_types:
        raise ValueError(f"reference case {name!r}: identity keys/values must be strings: {bad_types}")
    bad_hashes = sorted(k for k, v in identity.items() if not _SHA256_RE.match(v))
    if bad_hashes:
        raise ValueError(
            f"reference case {name!r}: identity entries must be lowercase sha256 hex: {bad_hashes}"
        )
    return dict(identity)


def _check_reference_version(name: str, version) -> str:
    if not isinstance(version, str) or not version:
        raise ValueError(f"reference case {name!r}: missing reference_version")
    try:
        parts = tuple(int(p) for p in version.split("."))
    except ValueError:
        raise ValueError(f"reference case {name!r}: malformed reference_version {version!r}") from None
    if len(parts) != 3 or parts[:2] != SUPPORTED_REFERENCE_SERIES:
        raise ValueError(
            f"reference case {name!r}: unsupported reference_version {version!r} "
            f"(supported series: {'.'.join(str(p) for p in SUPPORTED_REFERENCE_SERIES)}.x)"
        )
    return version


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
    reference_version: str = ""
    ignore: list[str] = field(default_factory=list)
    identity: dict[str, str] = field(default_factory=dict)

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
            "reference_version": self.reference_version,
            "ignore": list(self.ignore),
            "identity": dict(self.identity),
        }


def _load(path: Path) -> ReferenceCase:
    d = json.loads(path.read_text())
    name = d["name"]
    ignore = d.get("ignore", [])
    if not isinstance(ignore, list) or not all(isinstance(m, str) for m in ignore):
        raise ValueError(f"reference case {name!r}: 'ignore' must be a list of metric names")
    unknown_ignores = sorted(set(ignore) - set(d["reference_metrics"]))
    if unknown_ignores:
        raise ValueError(
            f"reference case {name!r}: ignore lists unknown metrics {unknown_ignores}"
        )
    return ReferenceCase(
        name=name,
        description=d.get("description", ""),
        engine=d.get("engine", "gromacs"),
        force_field=d.get("force_field", ""),
        selection=d.get("selection", "protein and name CA"),
        reference_metrics=d["reference_metrics"],
        tolerances=d.get("tolerances", {}),
        source=d.get("source", ""),
        source_hash=d.get("source_hash", ""),
        reference_version=_check_reference_version(name, d.get("reference_version")),
        ignore=ignore,
        identity=_check_identity(name, d.get("identity")),
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
