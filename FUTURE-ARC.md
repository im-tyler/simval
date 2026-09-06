# FUTURE-ARC — when simval starts running real-life simulations

Small plan. **Trigger fired 2026-09-06** — ontos (Forgejo `Tyler/ontos`,
GitHub `im-tyler/ontos`) is the real consumer: a deterministic multiscale sim
whose record streams simval already verifies (OntosEngine). Arc step 3's
"own deterministic solvers, verified by simval from day one" materialized as
a separate product rather than a simval submodule — simval stays oracle-only,
ontos stays the solver. Arc step 2 (orchestrator) now has its first
beneficiary: driving ontos verification runs.

## The arc (oracle-first, deliberately)

1. **Now: oracle.** simval verifies OTHER solvers' outputs (GROMACS, REBOUND,
   built-ins) with deterministic checks + reference anchors. This is the moat;
   every solver added makes the oracle stronger.
2. **Next: orchestrator.** Drive runs, not just judge them — parameter
   sweeps against the compare loop, agent-loop teaching (already the thesis),
   provenance-chained experiment pipelines.
3. **Later: own deterministic solvers.** Real-life simulation with
   bit-reproducible trajectories — the thing no incumbent offers
   cross-platform. Verified by simval's own oracle from day one.

## Division of labor (no coupling engineered now)

- **ontos** (Forgejo `Tyler/ontos`): the solver product this arc was waiting
  for. One-way dependency: ontos's adapters/references live in ontos, never
  here. Its Phase 3 names light-system as viewer.
- **light-system** (Forgejo `Tyler/light-system`, standalone Vulkan renderer,
  formerly "meridian"): the
  future drawing layer IF live visualization is ever needed. Renderers serve
  physics via a thin debug/particle/replay layer, not co-design — JoltViewer
  and PhysX PVD are the pattern. No work owed until a solver exists.
- **cascade solvers** (light-system, Forgejo reference): XPBD/SPH/Voronoi
  prototypes = reading material for solver design, not a base (they are
  welded to Godot's RenderingDevice).
- **omni-analyst**: the most plausible first consumer (simulation events for
  prediction/analysis). **Aethoph**: incidental dogfooding (vehicle/terrain
  dynamics), never the driver.

## Revisit trigger

Begin solver work only when a real consumer exists: omni-analyst asking for
sim events a verified oracle must produce, an external user of the oracle
demanding a missing domain, or a product need for deterministic replay
(netcode/rollback). Vision alone does not fire the trigger — that lesson
is already paid for (light-system, 2026).

Fired 2026-09-06 by ontos: a product need for deterministic replay plus a
solver that must be oracle-verified from day one. Recorded above.
