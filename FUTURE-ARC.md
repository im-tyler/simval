# FUTURE-ARC — when simval starts running real-life simulations

Small plan, parked. Do not start solver work before the revisit trigger fires.

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
