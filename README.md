# simval

Deterministic verification + a reference-oracle for computational physics simulations. Local-first, LLM-free core. The moat is the unsexy layer — packaged, consistent diagnostics + provenance + a validation oracle that an AI agent (or human) loops against to know whether a simulation's output is correct.

Working name; the folder may be renamed. See `PLAN.md` for the full thesis and `AUDIT.md` for the 5-pass analysis that shaped it.

## What it does

- **Diagnose** a run-dir: deterministic Tier-1 checks (energy drift, RMSD plateau, structural equilibration, per-residue RMSF, force-field coverage, parameter/unit sanity, prep sanity: box-vs-cutoff, steric clashes, charge state + His-tautomers).
- **Provenance manifest** (`simval.provenance.v1`): params, diagnostic results, SHA256 file hashes, verdict, Tier-2 human sign-off hook, and an **auto-extracted methods paragraph**.
- **Reference-oracle**: compare a candidate run against stored canonical references (`validate`) — the agent-loop teacher. Domain-general.
- **Compare** two runs (the parameter-sweep daily loop).

## Three physics domains via one port

| Engine | Domain | Headline check |
|---|---|---|
| `gromacs` | molecular dynamics (GROMACS) | conserved-energy drift, RMSD/RMSF, charge neutralization |
| `nbody-rebound` | celestial mechanics (REBOUND) | energy + angular-momentum + COM-drift conservation |
| `wave-fdtd` | waves/PDE (built-in leapfrog FDTD) | CFL stability (`c·dt/dx ≤ 1`) + energy boundedness |

A new domain implements `EngineAdapter` (`detect` + `load_context`) and registers itself; universal checks reuse automatically, domain-specific checks fire on `ctx.extra`.

## Install

```
pip install -e .                       # core (numpy-only)
pip install -e '.[gromacs]'            # MDAnalysis adapter for GROMACS
pip install -e '.[nbody]'              # REBOUND N-body domain
pip install -e '.[web]'                # FastAPI dashboard
pip install -e '.[dev]'                # pytest + httpx
```

GROMACS itself is needed only to *produce* runs (`brew install gromacs`); simval reads its outputs.

## CLI

```
simval diagnose <run-dir>                       # run diagnostics -> provenance.json
simval validate <run-dir> --case <name>         # oracle: match/drift vs reference
simval compare  <run-a> <run-b>                  # sweep diff
simval cases                                     # list reference cases
simval engines                                   # list registered domain adapters
simval-web --port 8765                           # local dashboard (Chart.js)
```

## Examples

- `examples/nbody/two_body/system.json` — Kepler orbit; `simval validate . --case kepler_two_body`
- `examples/wave/pulse/wave.json` — stable wave pulse; `simval validate . --case wave_pulse_stable`
- `pipeline/` — a real GROMACS 1AKI lysozyme run (Dockerfile + `run.sh`).

## Architecture

```
engine adapter (per domain)  ->  RunContext  ->  pipeline.run_checks  ->  manifest
                                          \->  oracle.validate (candidate vs reference)
service.py (stable API)  ->  cli / web / (future agent, notebook)
```

The core is local + LLM-free (verification must be deterministic). The optional NL/agent layer is the only cloud-touching part and is gated (see PLAN §1.5.1).

## Extending — adding a physics domain

The port is the headroom. To add a domain:

1. **Engine adapter** — subclass `EngineAdapter` (`simval/context.py`): implement `detect(run)` (recognize your run-dir) and `load_context(run) -> RunContext` (read your solver's outputs into the context). Call `register_engine(MyEngine())` at import. **Universal checks reuse automatically** — anything you put in `ctx.energy` gets `energy_drift`.
2. **Domain checks** — add branches to `pipeline.run_checks` that fire on `ctx.extra` (your domain's observables). Return `DiagnosticResult`s.
3. **Oracle (optional)** — add a `_xx_metrics(run)` to `oracle/validate.py` + the dispatch line, compute reference metrics from a canonical case, drop a `references/xx.json`.

**Minimal reference template:** `src/simval/wave.py` (~110 lines) — a complete domain (FDTD solver, 2 checks, engine, self-registration) and `references/wave_pulse_stable.json`. `src/simval/nbody.py` is the REBOUND-wrapped variant. Copy the shape, swap the physics.

## Status

Pre-alpha, no users yet. Phase 1 = plain-MD verification + provenance + oracle, with the multi-domain port proven. FEP/ΔΔG (the core pharma deliverable) is Phase 3 — a separate, months-long investment gated on a real user + domain partner. See PLAN §7.

## License

MIT (simval core). The verification layer invokes solvers **arm's-length** (subprocess / container / MCP) and does not link them, so wrapping GPL solvers (GROMACS, OpenFOAM) does not propagate copyleft — this is what keeps a future paid layer legal (PLAN §11). Upstream solvers keep their own licenses.
