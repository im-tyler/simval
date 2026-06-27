"""Quantum-circuits domain (Qiskit Aer statevector simulation).

Loads a circuit.json (n_qubits + a gate list), builds a qiskit
QuantumCircuit, runs it through qiskit_aer.AerSimulator(method='statevector'),
and captures the final statevector amplitudes and measurement probabilities.
Invariants: norm conservation sum|amp|^2 = 1 (unitarity of the evolution), and
optional agreement of the measurement distribution with an expected reference."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from simval.context import EngineAdapter, RunContext, register_engine
from simval.result import DiagnosticResult

_SINGLE_Q = {"h", "x", "y", "z", "s", "t", "sdg", "tdg"}
_TWO_Q = {"cx", "cz", "swap"}


def run_circuit(cfg: dict) -> dict:
    """Build a qiskit QuantumCircuit from cfg and run it via AerSimulator
    (statevector method). Returns the final statevector (complex ndarray) and
    the measurement-probability dict keyed by bitstring."""
    from qiskit import QuantumCircuit
    from qiskit_aer import AerSimulator

    n = int(cfg["n_qubits"])
    gates = cfg.get("gates", [])
    circ = QuantumCircuit(n)
    for g in gates:
        name = g["name"]
        q = g["q"]
        if name in _SINGLE_Q:
            getattr(circ, name)(int(q[0]))
        elif name in _TWO_Q:
            getattr(circ, name)(int(q[0]), int(q[1]))
        else:
            raise ValueError(f"unsupported gate: {name!r}")
    circ.save_statevector()
    sim = AerSimulator(method="statevector")
    sv = sim.run(circ).result().get_statevector()
    amps = np.asarray(sv.data, dtype=complex)
    probs = np.abs(amps) ** 2
    prob_dict = {format(i, f"0{n}b"): float(probs[i]) for i in range(2 ** n)}
    return {
        "statevector": amps,
        "probabilities": prob_dict,
        "n_qubits": n,
        "n_gates": len(gates),
    }


def check_norm_conservation(statevector, *, threshold: float = 1e-9) -> DiagnosticResult:
    """sum |amp|^2 must equal 1 (unitary evolution preserves the L2 norm)."""
    sv = np.asarray(statevector, dtype=complex)
    norm = float((np.abs(sv) ** 2).sum())
    drift = float(abs(norm - 1.0))
    return DiagnosticResult(
        name="qiskit_norm",
        passed=drift <= threshold,
        threshold=float(threshold),
        value=drift,
        detail={"norm": norm, "n_amplitudes": int(sv.size)},
    )


def check_measurement_distribution(
    probabilities, expected=None, *, threshold: float = 1e-9
) -> DiagnosticResult:
    """If `expected` is given, compare via total-variation distance
    (0 = identical, 1 = disjoint); pass when TV <= threshold. Otherwise
    informational: report the Shannon entropy (bits) of the distribution."""
    p = dict(probabilities)
    keys = sorted(p)
    pvec = np.array([p[k] for k in keys], dtype=float)
    if expected is None:
        nz = pvec[pvec > 0]
        entropy = float(-(nz * np.log2(nz)).sum()) if nz.size else 0.0
        return DiagnosticResult(
            name="qiskit_distribution",
            passed=True,
            threshold=float(threshold),
            value=entropy,
            detail={
                "mode": "entropy",
                "entropy_bits": entropy,
                "outcomes": {k: float(p[k]) for k in keys},
            },
        )
    e = dict(expected)
    qvec = np.array([float(e.get(k, 0.0)) for k in keys], dtype=float)
    tv = float(0.5 * np.abs(pvec - qvec).sum())
    return DiagnosticResult(
        name="qiskit_distribution",
        passed=tv <= threshold,
        threshold=float(threshold),
        value=tv,
        detail={
            "mode": "tv_distance",
            "tv_distance": tv,
            "outcomes": {k: float(p[k]) for k in keys},
            "expected": {k: float(e.get(k, 0.0)) for k in keys},
        },
    )


class QiskitEngine(EngineAdapter):
    name = "qc-qiskit"

    def detect(self, run: Path) -> bool:
        return (run / "circuit.json").exists()

    def load_context(self, run: Path, selection: str) -> RunContext:
        cfg = json.loads((run / "circuit.json").read_text())
        data = run_circuit(cfg)
        ctx = RunContext(run_dir=run, engine=self.name, selection=selection)
        ctx.extra = {
            "statevector": data["statevector"],
            "probabilities": data["probabilities"],
            "expected_probabilities": cfg.get("expected"),
            "n_qubits": data["n_qubits"],
        }
        ctx.run_params = {
            "engine": self.name,
            "domain": "quantum-circuit",
            "n_qubits": data["n_qubits"],
            "n_gates": data["n_gates"],
        }
        return ctx


register_engine(QiskitEngine())
