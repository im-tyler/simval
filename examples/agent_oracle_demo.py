"""Agent-oracle wedge demo.

Demonstrates the defensible positioning: an (LLM-free simulation of an) AI agent
that produces a candidate simulation, and simval's oracle catching that it's
wrong against a canonical reference. Run:

    python examples/agent_oracle_demo.py

This is the 'ground-truth verification for AI-generated simulations' loop,
without needing a real LLM -- the agent's broken output is synthesized, then
the oracle flags it deterministically.
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

WAVE = ROOT / "examples" / "wave" / "pulse" / "wave.json"


def agent_produces_candidate(broken: bool) -> Path:
    """Pretend an AI agent generated this wave-PDE config. broken=True means it
    picked a timestep that violates the CFL condition (a plausible agent mistake)."""
    cfg = json.loads(WAVE.read_text())
    if broken:
        cfg["dt"] = 0.2          # c*dt/dx = 2.0 > 1 -> numerically unstable
    run = Path(tempfile.mkdtemp())
    (run / "wave.json").write_text(json.dumps(cfg))
    return run


def main() -> int:
    from simval.oracle import validate

    print("== simval: ground-truth oracle for AI-generated simulations ==\n")

    good = agent_produces_candidate(broken=False)
    bad = agent_produces_candidate(broken=True)

    r_good = validate(good, "wave_pulse_stable")
    r_bad = validate(bad, "wave_pulse_stable")

    print(f"agent candidate A (stable dt):  oracle = {'MATCH' if r_good.passed else 'DRIFT'}")
    print(f"agent candidate B (CFL>1):      oracle = {'MATCH' if r_bad.passed else 'DRIFT'}")
    if not r_bad.passed:
        print("\nOracle caught the AI's unstable scheme. Drifted metrics:")
        for name, m in r_bad.detail["metrics"].items():
            if not m["passed"]:
                print(f"  - {name}: ref={m['reference']:.3g}  candidate={m['candidate']:.3g}  ({m['tol_kind']})")
    print("\n=> deterministic ground-truth flags AI mistakes without a human in the loop.")
    return 0 if (r_good.passed and not r_bad.passed) else 1


if __name__ == "__main__":
    raise SystemExit(main())
