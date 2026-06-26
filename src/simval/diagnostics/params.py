from __future__ import annotations

from simval.result import DiagnosticResult
from simval.units import Dimension, Quantity

EXPECTED_DIM: dict[str, Dimension] = {
    "dt": Dimension(time=1),
    "nsteps": Dimension(),
    "ref_t": Dimension(temperature=1),
    "tau_t": Dimension(time=1),
    "ref_p": Dimension(mass=1, length=-1, time=-2),
    "tau_p": Dimension(time=1),
}

MUST_BE_POSITIVE = {"dt", "nsteps", "ref_t", "ref_p"}


def check_params(
    params: dict[str, Quantity],
    *,
    expected: dict[str, Dimension] | None = None,
) -> DiagnosticResult:
    spec = expected if expected is not None else EXPECTED_DIM
    violations: list[str] = []
    checked = 0
    for name, q in params.items():
        if name not in spec:
            continue
        checked += 1
        if q.dimension != spec[name]:
            violations.append(
                f"{name}: unit {q.unit!r} has dimension incompatible with expected"
            )
        if name in MUST_BE_POSITIVE and q.value <= 0:
            violations.append(f"{name}: value {q.value} must be positive")
    n_violations = len(violations)
    return DiagnosticResult(
        name="params",
        passed=n_violations == 0,
        threshold=0.0,
        value=float(n_violations),
        detail={
            "checked": checked,
            "n_violations": n_violations,
            "violations": violations,
        },
    )
