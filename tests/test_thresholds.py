import json

from simval.fixtures import make_run_dir
from simval.pipeline import diagnose


def test_threshold_override_takes_effect(tmp_path):
    run = make_run_dir(tmp_path / "good", good=True)
    default = diagnose(run, selection="protein")
    default_ed = [d for d in default["diagnostics"] if d["name"] == "energy_drift"][0]
    assert default_ed["passed"] is True

    tight = diagnose(run, selection="protein", thresholds={"energy_drift": 1e-6})
    tight_ed = [d for d in tight["diagnostics"] if d["name"] == "energy_drift"][0]
    assert tight_ed["threshold"] == 1e-6
    assert tight_ed["passed"] is False  # the good run's rel-range now exceeds 1e-6


def test_thresholds_json_in_run_dir(tmp_path):
    run = make_run_dir(tmp_path / "bad", good=False)
    (run / "thresholds.json").write_text(json.dumps({"energy_drift": 10.0}))
    m = diagnose(run, selection="protein")
    by_name = {d["name"]: d for d in m["diagnostics"]}
    assert by_name["energy_drift"]["threshold"] == 10.0
