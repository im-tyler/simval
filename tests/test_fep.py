import pytest

pytest.importorskip("alchemlyb", reason="needs alchemlyb")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from simval.fep import (  # noqa: E402
    FepEngine,
    check_free_energy,
    check_hysteresis,
    check_overlap,
    synthetic_u_nk,
)
from simval.oracle import get_case, list_cases  # noqa: E402
from simval.oracle.validate import compare_metrics  # noqa: E402

EXAMPLE = (
    __import__("pathlib").Path(__file__).parent.parent / "examples" / "fep" / "synthetic"
)
LN2 = 0.6931471805599453


def _ladder_u_nk(centers, n_per, *, std=0.5, seed=0):
    rng = np.random.default_rng(seed)
    parts = []
    for i, c in enumerate(centers):
        x = rng.normal(c, std, n_per[i])
        lam = float(i)
        idx = pd.MultiIndex.from_arrays(
            [np.arange(sum(n_per[:i]), sum(n_per[:i]) + n_per[i]),
             np.full(n_per[i], lam)],
            names=["time", "fep-lambda"])
        row = {float(j): 0.5 * ((x - cj) / std) ** 2 for j, cj in enumerate(centers)}
        parts.append(pd.DataFrame(row, index=idx))
    return pd.concat(parts)


def test_synthetic_recovers_known_free_energy():
    u = synthetic_u_nk()
    res = check_free_energy(u)
    assert res.name == "free_energy"
    assert res.passed is True
    assert abs(res.detail["deltaG_kT"] - LN2) < 0.02
    assert res.detail["deltaG_kJmol"] == pytest.approx(res.detail["deltaG_kT"] * 2.479)


def test_overlap_passes_for_well_sampled_fixture():
    res = check_overlap(synthetic_u_nk())
    assert res.name == "fep_overlap"
    assert res.passed is True
    assert res.value >= 0.05


def test_overlap_fails_for_undersampled_state():
    centers = [0.0, 1.0, 2.0, 3.0, 4.0]
    n_per = [4000, 4000, 15, 4000, 4000]
    res = check_overlap(_ladder_u_nk(centers, n_per))
    assert res.passed is False
    assert res.value < 0.05


def test_hysteresis_skips_without_reverse_leg():
    res = check_hysteresis(synthetic_u_nk())
    assert res.name == "fep_hysteresis"
    assert res.passed is True
    assert res.detail["skipped"] is True


def test_hysteresis_with_consistent_reverse_leg():
    u = synthetic_u_nk()
    res = check_hysteresis(u, u_nk_reverse=u)
    assert res.passed is True
    assert res.value < 0.5


def test_fep_engine_detects_manifest_and_dhdl_files():
    eng = FepEngine()
    assert eng.name == "fep"
    assert eng.detect(EXAMPLE) is True


def test_fep_engine_load_context_reads_csv_u_nk():
    eng = FepEngine()
    ctx = eng.load_context(EXAMPLE, selection="n/a")
    assert ctx.extra["u_nk"] is not None
    assert ctx.run_params["domain"] == "fep"
    assert ctx.run_params["kind"] == "u_nk"
    res = check_free_energy(ctx.extra["u_nk"])
    assert res.passed is True
    assert np.isfinite(res.value)


def test_oracle_fep_case_exists_and_self_matches():
    assert "fep_synthetic" in list_cases()
    case = get_case("fep_synthetic")
    u = synthetic_u_nk()
    fe = check_free_energy(u)
    ov = check_overlap(u)
    candidate = {
        "deltaG_kT": fe.detail["deltaG_kT"],
        "uncertainty_kT": fe.detail["uncertainty_kT"],
        "overlap_min_eigenvalue": ov.detail["overlap_min_eigenvalue"],
    }
    compared = compare_metrics(candidate, case.reference_metrics, case.tolerances)
    assert compared.pop("__passed__") is True
    assert all(v["passed"] for v in compared.values())


def test_oracle_fep_flags_bad_candidate():
    case = get_case("fep_synthetic")
    bad = dict(case.reference_metrics)
    bad["deltaG_kT"] = -5.0
    bad["overlap_min_eigenvalue"] = 0.001
    compared = compare_metrics(bad, case.reference_metrics, case.tolerances)
    assert compared["__passed__"] is False
    assert compared["deltaG_kT"]["passed"] is False
    assert compared["overlap_min_eigenvalue"]["passed"] is False
