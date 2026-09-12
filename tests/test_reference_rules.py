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
    assert len(all_cases) >= 15
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
