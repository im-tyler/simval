import json
import shutil
from pathlib import Path

import pytest

pytest.importorskip("qiskit", reason="needs qiskit")
pytest.importorskip("qiskit_aer", reason="needs qiskit-aer")

import simval.qiskit_eng  # noqa: F401  (registers QiskitEngine)
from simval.context import select_engine
from simval.qiskit_eng import (
    QiskitEngine,
    check_measurement_distribution,
    check_norm_conservation,
    run_circuit,
)

EXAMPLE = Path(__file__).parent.parent / "examples" / "qc" / "bell"


def test_qiskit_engine_detects_circuit_json():
    assert QiskitEngine().detect(EXAMPLE) is True


def test_qiskit_engine_does_not_detect_foreign_dir(tmp_path):
    (tmp_path / "other.json").write_text("{}")
    assert QiskitEngine().detect(tmp_path) is False


def test_engine_registers_and_is_selectable():
    assert select_engine(EXAMPLE).name == "qc-qiskit"


def test_bell_state_norm_conserved():
    cfg = json.loads((EXAMPLE / "circuit.json").read_text())
    data = run_circuit(cfg)
    r = check_norm_conservation(data["statevector"])
    assert r.name == "qiskit_norm"
    assert r.passed is True
    assert r.value <= 1e-9


def test_norm_check_flags_unnormalised_state():
    sv = [1.0 + 0j, 0.0 + 0j]
    r = check_norm_conservation(sv)
    assert r.passed is True
    bad = [2.0 + 0j, 0.0 + 0j]
    rb = check_norm_conservation(bad)
    assert rb.passed is False
    assert rb.value > 1.0


def test_bell_state_distribution_matches_expected():
    cfg = json.loads((EXAMPLE / "circuit.json").read_text())
    data = run_circuit(cfg)
    r = check_measurement_distribution(data["probabilities"], expected=cfg["expected"])
    assert r.passed is True
    assert r.detail["mode"] == "tv_distance"
    assert r.value <= 1e-9
    assert data["probabilities"]["00"] == pytest.approx(0.5)
    assert data["probabilities"]["11"] == pytest.approx(0.5)
    assert data["probabilities"]["01"] == pytest.approx(0.0)
    assert data["probabilities"]["10"] == pytest.approx(0.0)


def test_distribution_informational_without_expected():
    r = check_measurement_distribution({"00": 0.5, "11": 0.5})
    assert r.passed is True
    assert r.detail["mode"] == "entropy"
    assert r.value == pytest.approx(1.0)


def test_distribution_flags_mismatch():
    r = check_measurement_distribution(
        {"00": 1.0, "11": 0.0}, expected={"00": 0.5, "11": 0.5}
    )
    assert r.passed is False
    assert r.value > 0.4


def test_load_context_populates_statevector_and_probabilities():
    ctx = QiskitEngine().load_context(EXAMPLE, selection="n/a")
    assert ctx.engine == "qc-qiskit"
    sv = ctx.extra["statevector"]
    assert sv.shape == (4,)
    assert sv.dtype == complex
    assert ctx.extra["probabilities"]["00"] == pytest.approx(0.5)
    assert ctx.extra["probabilities"]["11"] == pytest.approx(0.5)
    assert check_norm_conservation(sv).passed
    assert ctx.run_params["n_qubits"] == 2
    assert ctx.run_params["domain"] == "quantum-circuit"


def test_load_context_works_after_copy_to_tmp(tmp_path):
    run = tmp_path / "qc"
    run.mkdir()
    shutil.copy(EXAMPLE / "circuit.json", run / "circuit.json")
    ctx = QiskitEngine().load_context(run, selection="n/a")
    assert check_norm_conservation(ctx.extra["statevector"]).passed
    assert ctx.extra["probabilities"]["11"] == pytest.approx(0.5)
