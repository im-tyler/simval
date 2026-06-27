import json
import shutil
from pathlib import Path


from simval.em import EMEngine, check_courant, check_em_energy, integrate_em
from simval.oracle import validate
from simval.pipeline import diagnose
from simval.quantum import QuantumEngine, check_norm_conservation, evolve_spin

EM = Path(__file__).parent.parent / "examples" / "em" / "wave"
QM = Path(__file__).parent.parent / "examples" / "quantum" / "spin"


# --- EM ---
def test_em_courant():
    assert check_courant(0.7).passed is True
    assert check_courant(1.4).passed is False


def test_em_engine_detects():
    assert EMEngine().detect(EM) is True


def test_em_stable_run():
    data = integrate_em(json.loads((EM / "em.json").read_text()))
    assert check_courant(data["courant"]).passed
    assert check_em_energy(data["energy"], src_on_index=data["src_on"] // 10).passed


def test_diagnose_em(tmp_path):
    run = tmp_path / "em"
    run.mkdir()
    shutil.copy(EM / "em.json", run / "em.json")
    m = diagnose(run, selection="n/a")
    names = [d["name"] for d in m["diagnostics"]]
    assert "em_courant" in names and "em_energy_bounded" in names
    assert m["verdict"] == "pass"


# --- Quantum ---
def test_quantum_engine_detects():
    assert QuantumEngine().detect(QM) is True


def test_quantum_norm_conserved():
    data = evolve_spin(json.loads((QM / "quantum.json").read_text()))
    nc = check_norm_conservation(data["norm"])
    assert nc.passed, f"norm drifted: {nc.value}"
    assert nc.value < 1e-9


def test_quantum_rabi_swings():
    data = evolve_spin(json.loads((QM / "quantum.json").read_text())
                       | {"omega1": 0.0})  # no drive -> no swing -> should fail
    from simval.quantum import check_rabi_oscillates
    assert check_rabi_oscillates(data["p_up"]).passed is False


def test_diagnose_quantum(tmp_path):
    run = tmp_path / "qm"
    run.mkdir()
    shutil.copy(QM / "quantum.json", run / "quantum.json")
    m = diagnose(run, selection="n/a")
    names = [d["name"] for d in m["diagnostics"]]
    assert "norm_conservation" in names and "rabi_population_swing" in names
    assert m["verdict"] == "pass"


def test_oracle_em_and_quantum_match():
    assert validate(EM, "em_pulse_stable").passed is True
    assert validate(QM, "quantum_spin").passed is True
