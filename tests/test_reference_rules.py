"""Reference-case registry tests: version gate + every shipped metric resolves
to exactly one comparison rule (audit ORA-001/GOLD-001 corpus property)."""
from __future__ import annotations

import json

import pytest

from simval.oracle import cases as cases_mod
from simval.oracle import load_all
from simval.oracle.cases import ReferenceCase
from simval.oracle.validate import _DEFAULT_TOLERANCES, compare_metrics


def test_every_reference_metric_resolves_to_exactly_one_rule():
    problems = []
    for name, case in load_all().items():
        for metric in case.reference_metrics:
            if metric in case.ignore:
                continue
            if metric not in case.tolerances and metric not in _DEFAULT_TOLERANCES:
                problems.append(f"{name}: {metric} has no rule")
        for metric in case.tolerances:
            if metric not in case.reference_metrics:
                problems.append(f"{name}: tolerance for unknown metric {metric}")
    assert not problems, problems


def test_no_undeclared_ignores_in_shipped_references():
    for name, case in load_all().items():
        assert case.ignore == [], f"{name}: unexpected ignore list {case.ignore}"


def test_reference_version_gate_rejects_unsupported(tmp_path):
    src = cases_mod._REFERENCES_DIR / "adk_morph.json"
    d = json.loads(src.read_text())
    d["reference_version"] = "99.0.0"
    path = tmp_path / "future.json"
    path.write_text(json.dumps(d))
    with pytest.raises(ValueError, match="unsupported reference_version"):
        cases_mod._load(path)


def test_reference_version_gate_rejects_missing(tmp_path):
    src = cases_mod._REFERENCES_DIR / "adk_morph.json"
    d = json.loads(src.read_text())
    del d["reference_version"]
    path = tmp_path / "noversion.json"
    path.write_text(json.dumps(d))
    with pytest.raises(ValueError, match="missing reference_version"):
        cases_mod._load(path)


def test_all_shipped_references_parse_under_version_gate():
    all_cases = load_all()
    # 14 after benzene_hydration_fep was retired (FEP-001, AUDIT.md §G).
    assert len(all_cases) >= 14
    assert all(c.reference_version.startswith("0.1.") for c in all_cases.values())


def test_case_roundtrip_carries_new_fields():
    case = load_all()["adk_morph"]
    d = case.to_dict()
    assert d["reference_version"] == "0.1.0"
    assert d["ignore"] == []
    restored = ReferenceCase(**{k: v for k, v in d.items()})
    assert restored.reference_version == case.reference_version


def test_compare_metrics_missing_candidate_metric_fails():
    ref = {"n_frames": 10, "mean_rg_nm": 2.2}
    cand = {"mean_rg_nm": 2.2}
    out = compare_metrics(cand, ref)
    assert out["__passed__"] is False
    assert out["n_frames"]["passed"] is False
    assert "missing from candidate" in out["n_frames"]["error"]


def test_compare_metrics_missing_policy_is_config_error():
    with pytest.raises(ValueError, match="'weird_metric'.*no comparison policy"):
        compare_metrics({"weird_metric": 1.0}, {"weird_metric": 1.0})


def test_compare_metrics_ignore_exempts_metric():
    ref = {"n_frames": 10}
    out = compare_metrics({}, ref, ignore=["n_frames"])
    assert out["__passed__"] is True
    assert out["n_frames"]["tol_kind"] == "ignore"


# --- ORA-002: bounds are bounds, not distances from the golden ---


def _case_tols(name):
    return load_all()[name].tolerances


def test_wave_cfl_ceiling_rejects_supercritical():
    # The old abs-1.0 rule let CFL 1.4 pass against a 0.5 golden.
    ref = {"cfl": 0.5, "energy_growth": 1.007, "n_steps": 2000}
    tols = _case_tols("wave_pulse_stable")
    bad = compare_metrics({"cfl": 1.4, "energy_growth": 1.007, "n_steps": 2000}, ref, tols)
    assert bad["cfl"]["passed"] is False
    ok = compare_metrics({"cfl": 0.99, "energy_growth": 1.007, "n_steps": 2000}, ref, tols)
    assert ok["cfl"]["passed"] is True
    assert ok["__passed__"] is True


def test_em_courant_ceiling_rejects_supercritical():
    ref = {"courant": 0.7071, "em_energy_growth": 1.014, "n_steps": 800}
    tols = _case_tols("em_pulse_stable")
    bad = compare_metrics({"courant": 1.2, "em_energy_growth": 1.0, "n_steps": 800}, ref, tols)
    assert bad["courant"]["passed"] is False
    assert bad["em_energy_growth"]["passed"] is True  # 1.0 is bounded energy, not drift


def test_bound_kinds_require_finite_candidates():
    ref = {"cfl": 0.5}
    out = compare_metrics(
        {"cfl": float("nan")}, ref, {"cfl": ["max", 1.0]}
    )
    assert out["cfl"]["passed"] is False
    out = compare_metrics({"cfl": float("inf")}, ref, {"cfl": ["max", 1.0]})
    assert out["cfl"]["passed"] is False
    out = compare_metrics({"p": float("nan")}, {"p": 0.99}, {"p": ["min", 0.9]})
    assert out["p"]["passed"] is False


def test_interval_and_min_bounds():
    assert compare_metrics({"tau": 0.8}, {"tau": 0.8}, {"tau": ["interval", 0.5, 2.0]})["tau"]["passed"]
    assert not compare_metrics({"tau": 2.8}, {"tau": 0.8}, {"tau": ["interval", 0.5, 2.0]})["tau"]["passed"]
    assert not compare_metrics({"tau": 0.3}, {"tau": 0.8}, {"tau": ["interval", 0.5, 2.0]})["tau"]["passed"]
    assert compare_metrics({"p": 0.9999}, {"p": 0.9999}, {"p": ["min", 0.9]})["p"]["passed"]
    assert not compare_metrics({"p": 0.5}, {"p": 0.9999}, {"p": ["min", 0.9]})["p"]["passed"]


# --- ORA-004: tolerance rules are externally supplied too ---


@pytest.mark.parametrize(
    "spec",
    [
        ["abs", float("inf")],
        ["abs", float("nan")],
        ["abs", 0.0],
        ["abs", -1.0],
        ["rel", float("inf")],
        ["max", float("inf")],
        ["min", float("nan")],
        ["interval", 0.5, float("inf")],
        ["interval", 2.0, 0.5],
        ["exact", 1.0],
        ["vacuous", 1.0],
        ["abs"],
        ["abs", 1.0, 2.0],
    ],
)
def test_malformed_tolerance_rules_rejected(spec):
    with pytest.raises(ValueError, match="tolerance rule"):
        compare_metrics({"m": 1.0}, {"m": 1.0}, {"m": spec})


def test_wellformed_tolerance_rules_accepted():
    assert compare_metrics({"m": 1.0}, {"m": 1.0}, {"m": ["abs", 0.5]})["__passed__"]
    assert compare_metrics({"m": 1.0}, {"m": 1.0}, {"m": ["interval", 0.0, 2.0]})["__passed__"]
