from __future__ import annotations

from simval.oracle.validate import compute_metrics


def compare_runs(run_a, run_b, *, selection: str = "protein and name CA") -> dict:
    """Diff two runs on scalar metrics. This is the daily loop: parameter
    sweep -> compare runs on RMSD / Rg / energy / drift."""
    a = compute_metrics(run_a, selection=selection)
    b = compute_metrics(run_b, selection=selection)

    deltas: dict[str, dict] = {}
    only_a: dict = {}
    only_b: dict = {}
    for k in sorted(set(a) | set(b)):
        if k in a and k in b:
            av, bv = a[k], b[k]
            denom = abs(av) + 1e-12
            deltas[k] = {"a": av, "b": bv, "delta_abs": bv - av, "delta_rel": abs(bv - av) / denom}
        elif k in a:
            only_a[k] = a[k]
        else:
            only_b[k] = b[k]

    if not deltas:
        raise ValueError(
            f"no overlapping metrics between {run_a} and {run_b} -- different domains/engines"
        )

    return {
        "selection": selection,
        "run_a": str(run_a),
        "run_b": str(run_b),
        "metrics_a": a,
        "metrics_b": b,
        "deltas": deltas,
        "only_a": only_a,
        "only_b": only_b,
    }


def largest_deltas(comparison: dict, *, n: int = 5) -> list[tuple[str, float]]:
    ranked = sorted(comparison["deltas"].items(), key=lambda kv: kv[1]["delta_rel"], reverse=True)
    return [(name, v["delta_rel"]) for name, v in ranked[:n]]
