from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class DiagnosticResult:
    name: str
    passed: bool
    threshold: float
    value: float
    detail: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
