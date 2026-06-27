# Omnilator — Plan (working draft)

> Living document. Status: **DRAFT v0.3** — post-audit. Scope narrowed to simulation-only; verification promoted to the headline.
> Product/working package name is **`simval`** pending the D6 naming decision. The folder is still `omnilator/`.
> Authority: AUDIT.md (5-pass synthesis). §C edits applied here; convergent findings (§A in AUDIT) drive every change.

---

## 1. What this is (and isn't)

**One-line vision.** A reproducible simulation workbench with NL assist, provenance, and shared viz — built around a **deterministic verification layer** that the free agent+MCP+Docker composite cannot ship.

**In scope (Phase 1)**
- One vertical: **GROMACS molecular dynamics**.
- One user (see §1.5).
- NL-accepting notebook UI + always-on provenance panel + comparison view (not chat+canvas).
- One ReAct agent (cloud LLM via LiteLLM) → one MCP server (we write) → `docker run` + mounted workspace.
- **Deterministic diagnostics + human sign-off** (see §1.7) — promoted from Phase 3 to the headline.
- MDAnalysis + NGLView (live) / Molecular Nodes (render). **No USD for MD.**
- Honest reproducibility (captured artifacts are re-runnable; the NL→artifact step is not bit-reproducible — see §9).

**Explicitly NOT**
- A new simulation engine (uses existing solvers verbatim).
- A fork of upstream tools (wrappers + containers only — and this is precisely what keeps a paid layer legal; see §11).
- A generic chatbot (purpose-built for tool orchestration with verification).
- **A creative/generative tool.** Blender is a render target for sim output *only*. Generative-creative is Out-of-Scope (AUDIT A1).
- **A "glue every solver together" platform.** One vertical, one engine, until Phase 1's exit criterion is met.
- A cloud-only product. Local-first where it matters (data, control, compute); cloud-assisted where it must (LLM).

---

## 1.5 Primary user + Job-to-be-Done

**Primary user:** biotech/pharma R&D scientist running MD as part of lead optimization / binding-affinity workflows. **Secondary:** rusty PI who needs to redo an MD calculation they haven't touched since postdoc.

**Current alternative:** Schrödinger ($$$), CHARMM-GUI + GROMACS + VMD hand-stitched, or raw GROMACS CLI.

**Job-to-be-done (the daily loop):** run a parameter sweep, **compare runs on RMSD / Rg / energy**, and **export a reproducible bundle** a colleague or reviewer can rerun. The expert's actual complaint about GROMACS is "setup is boilerplate and sweeps are hard to manage" — a tooling problem, not a conversation problem (AUDIT A2).

**Willingness to pay:** real, sub-$1k/mo indie/academic band that Rescale/Schrödinger ignore. See §4.6.

**What NL is for:** a novice onboarding feature and a sweep-setup accelerator — **not** the expert's primary control surface. Experts want determinism; NL+LLM breaks it (AUDIT A2, A3).

### 1.5.1 User-interview proxy (scientist persona, 2026-06-26) — drives §7 reorder

A pharma comp-chemist persona review (14 questions) produced one load-bearing finding and the build queue. Recorded here so the roadmap is traceable to the user, not to preference.

- **FEP is the actual pharma deliverable; plain-MD verification is the foundation it rests on.** Binding ΔΔG (FEP/TI, BAR/MBAR convergence) is what lead-opt pays for; simval has 0% of that today. Honest fork: chase FEP (months, scope explosion, needs domain depth Tyler lacks — A12) OR own the plain-MD foundation. **Scoping choice: Phase 1 = the plain-MD verification + provenance/methods utility a pharma modeler runs *alongside* their FEP stack.** FEP/ΔΔG → Phase 3+, a separate investment gated on a real user + domain partner.
- **Methods-section auto-extract is the #1 wedge and is near-free.** Every parameter for a methods paragraph lives in `.mdp`/`.top`. Emitted as structured provenance + a rendered paragraph. Modelers hand-type this 50×/yr.
- **Prep-sanity (box/cutoff, clashes) is buildable now; protonation/net-charge needs FF-charge parsing (deferred).** These catch the expensive mistakes (wrong box → PME image artifacts; clashes → unphysical).
- **Claim scoping:** "structural equilibration" ≠ "thermodynamic/free-energy convergence." RMSD plateau certifies the former, never imply the latter.
- **Cloud-LLM is a hard gate for regulated pharma.** Reframe: the *verification core is local + LLM-free* (selling point). The optional NL/agent layer is the only cloud-touching part, and it must be air-gap-able.
- Adopt verdict: "I'd pilot it in shadow mode today for the provenance/methods extract; I would not yet trust a PASS; I'd ignore NL." That sets the honest bar.

---

## 1.6 Existence proof (lead the pitch with the gap)

The composite substitute — an AI coding agent + community MCP servers + Docker — gets ~60–70% of the way for throwaway single-tool work. **Omnilator's 30–40% gap is entirely the unsexy layer:** converters, provenance, verification, job survival. **That gap is the product.**

References that prove the easy half is already free: `blender-mcp` (23k★, MIT, opencode/Cursor/Claude-native), Jupyter-AI, the agent+MCP+Docker composite.

---

## 1.7 Verification — the actual product shape (re-derived, post-audit)

This is the load-bearing section. "Validator agent" is deleted. Verification is split into two tiers (AUDIT A4, sharpened):

**Tier 1 — deterministic / mechanical. Fully buildable. This is the headline.**
- Energy drift > threshold → fail (conservation-law residual).
- RMSD / radius-of-gyration plateau; equilibration tests (block averaging, autocorrelation time, effective sample size).
- Force-field parameter coverage (all atom types parameterized? cofactor covered?).
- Unit / dimensional consistency.
- Mass / momentum / energy conservation residuals.
- File / image / param integrity (digests, checksums).

This is ~80% of the value of "verification," it's all diagnostics, and the free composite solves ~5% of it (AUDIT A4). **Tier 1 is the one defensible thing to build.**

**Tier 2 — model-class vs scientific intent. NOT computable. Human sign-off.**
- "Is a fixed-charge force field even capable of the charge-transfer physics I care about?" (wrong by construction, not by number)
- "Is my coarse-graining throwing away the detail my question needs?"
- "Is this discrepancy a bug or a discovery?"

These are category judgments, not computations. Force fields are empirical fits to data, not theorems — you cannot Lean-prove "this FF matches reality." Tier 2 is where the human (or a domain expert) signs off on export.

**Where formal methods (Lean) actually fit:** prove the *diagnostics themselves* are correct — integrator symplecticity, dimensional/unit correctness, statistical validity of the convergence tests, conservation-law implementation. Lean at the Tier-1 implementation layer, not the physics-validity layer.

**Why this is the moat as AI scales:** trust scales *inversely* with AI-generated volume. The more compute is thrown at simulation generation, the more valuable the deterministic verification layer becomes. It is the only thing in this landscape that gets more valuable, not less, as AI scales.

---

## 1.8 The durable build — reference-oracle (decided 2026-06-26)

Strategic anchor: build for the future by accumulating assets that **don't depreciate** as AI improves — not by scaffolding the largest version now (which depreciates).

- **Durable (compound as AI improves):** canonical reference datasets (known-good outputs per benchmark case); a validation oracle future agents call to verify their sim code; users/distribution/trust.
- **Depreciating (rebuilt by future AI):** hand-written scaffolding, glue, orchestration, any "largest-scale" structure committed to under today's capabilities.

**The build:** a **reference-oracle for MD.** Canonical benchmark cases carry stored reference *metrics* (computed once from known-good trajectories, versioned as JSON — not the huge raw trajectories). An API — `validate(run, case) -> pass/fail + per-metric deltas` — lets an agent (or human) building/improving an MD integrator check whether their output reproduces the known-good result within tolerance. Reuses simval's diagnostics to compute candidate metrics. This is the agent-loop teacher: an LLM with no oracle hallucinates plausible-wrong physics; an LLM with a reference oracle gets told "your RMSD drifts 8% from the known-good — fix it."

Extends domain-by-domain as bandwidth + real users justify (CFD, EM later; frontier excluded — no reference data without the supercomputer). **Alanine-dipeptide canonical benchmark** is the first proper reference case to add (rich published data).

Units shipped this iteration: `oracle/cases.py` (ReferenceCase registry), `oracle/validate.py` (`compute_metrics` + pure `compare_metrics` + `validate`), `references/*.json` (AdK + lysozyme snapshots), `simval validate <run-dir> --case <name>`.

### 1.8.1 Extension architecture — the "ultimate-ready" seams (2026-06-26)

The base is built to absorb expansion without rewriting the core. Two stable ports:

- **`EngineAdapter` (`simval/context.py`)** — a new physics domain implements `detect(run)` + `load_context(run) -> RunContext`. `GromacsEngine` and `SyntheticEngine` ship now; a future `FluidEngine` / `NBodyEngine` / `OpenMMEngine` registers via `register_engine()` and is immediately discoverable (`simval engines`, `service.list_engines()`). *The port is what's built; the future domains are not pre-instantiated* — that would be the omni-fantasy in code form.
- **`service.py`** — the stable API (`inspect`, `diagnose_run`, `validate_run`, `cases`, `list_engines`). Any future UI (full SPA, notebook, agent) sits on this and never touches pipeline internals.
- **`web.py`** — a thin local-first FastAPI dashboard (`pip install simval[web]`; `simval-web`). Proves the service API is UI-agnostic; replaceable by a real frontend without core changes.

Layering: `engines → pipeline.run_checks(ctx) → manifest` / `oracle.validate`. Checks read from a `RunContext`; adding a check is one branch in `run_checks`; adding a domain is an `EngineAdapter` + that domain's checks reading `ctx.extra`. A plugin test (`test_new_domain_plugs_in_via_adapter`) proves the seam. **Discipline holds:** this is interfaces, not implementations of unbuilt domains.

---

## 2. Why now — honest enablers and honest blockers

**Enablers (real, as of mid-2026)**
- MCP is a shipping Anthropic open standard; `langchain_mcp_adapters` makes LangGraph ↔ MCP integration straightforward.
- GROMACS container images exist (incl. NVIDIA GPU); OpenFOAM, headless Blender, FreeCAD, Godot images exist.
- LangGraph gives stateful, checkpointable, branching agent graphs (ReAct via `create_react_agent` is enough for Phase 1 — no 5-agent graph).
- Anthropic + GitHub now run MCP registries — **we consume, we do not build one** (AUDIT A6).

**Blockers / unknowns (also real)**
- "Did the simulation produce correct physics?" is partly solvable (Tier 1) and partly a human judgment (Tier 2). Scope the product to the solvable part; surface the human part as a sign-off gate.
- Long-running sim control (checkpoint, resume, verify) is genuinely hard and under-solved — **deferred to Phase 3**, not Phase 1.
- Cross-tool data conversion is the real time sink when the second vertical arrives. Not a Phase-1 problem (one tool).

---

## 2.5 Competitive landscape (AUDIT A13)

- **Surrogate vendors** (PhysicsX, BeyondMath, Navista SimAI) build ML models that *skip the solvers we wrap* — a strictly better tech vector. Thesis for why we win: **trustworthy ground-truth while surrogates mature.** Verification is what surrogates can't self-certify.
- **Incumbents** (Schrödinger, Rescale, SimScale, Cadence) own the buyer and the natural paid layer (managed reproducible compute). Rescale's model = our paid layer; our wedge is the sub-$1k/mo indie/academic price point they ignore + local-first.
- **Jupyter ecosystem** is where the scientist user already lives and already does CAD+MD+CFD+provenance. "New workbench" is the wrong framing for that user; we are a **Jupyter-shaped notebook + the verification layer they don't have**.
- **The composite substitute** (agent + community MCP + Docker) ≈ 60–70% for throwaway single-tool work. Our gap is the unsexy layer (§1.6). Lead with it.

---

## 3. Architecture (minimal Phase-1 stack)

```
notebook UI (NL-accepting cells + provenance panel + comparison view; defer canvas/timeline)
  -> one ReAct agent (LangGraph create_react_agent, cloud model via LiteLLM)
  -> MCP client (langchain_mcp_adapters, stdio)           [no gateway; consume registries]
  -> tools.yaml registry (name / transport / command)
  -> docker run + mounted ./workspace volume               [rootless/gVisor; --network=none --read-only]
  -> GROMACS MCP server (we write it)
  -> MDAnalysis -> HDF5/numpy                              [no USD for MD]
  -> NGLView (live) | Molecular Nodes (render)
  -> DETERMINISTIC DIAGNOSTICS (gmx energy + RMSD + thresholds -> pass/fail)   <-- the moat (§1.7 Tier 1)
  -> JSON provenance manifest (params, image digest, hashes, diagnostics, verdict)
  -> HUMAN SIGN-OFF on export (§1.7 Tier 2)
```

**Deleted from v0.2:** MCP Gateway/Registry box, the 5-agent graph (Planner/Router/Executor/Validator/Visualizer), K8s, USD/glTF for MD, Rerun (Phase 3), Blender-as-universal-viz axiom. Blender = viz implementation detail for the MD vertical only, and NGLView/ChimeraX/OVITO are purpose-built alternatives to revisit at Phase-2 review.

---

## 4. Decisions (status post-audit)

| # | Decision | Status |
|---|---|---|
| D1 | Scope & user — **one vertical (GROMACS MD), one user (biotech R&D)**; cut creative | **DECIDED v0.3** |
| D2 | Runtime — **greenfield Python**; Hive = reference only | **DECIDED v0.3** (AUDIT A11) |
| D3 | LLM sourcing — **cloud LLM for Phase 1** (Claude/GPT via LiteLLM); local execution/data | **DECIDED v0.3** (AUDIT A10) |
| D4 | Verification model — **deterministic diagnostics (Tier 1) + human sign-off (Tier 2)**; no Validator agent | **DECIDED v0.3** (§1.7) |
| D5 | Process — **collapse Phase 0 into Phase 1**; 2–3 wk timebox; kill-by date (§10) | **DECIDED v0.3** |
| D6 | Name — **REOPENED.** "Omnilator/omni" contradicts a sim+verification thesis. Working package name `simval` until decided. **No naming session** (that's the A12 trap); pick when it surfaces naturally. | OPEN |
| D-new | First executable unit — **diagnostics library standalone**, before agent/MCP/Docker | **DECIDED v0.3** |

**§4.6 Paid layer + buyer + price band (added).** Candidate paid layer: managed reproducible compute (the Rescale model) at sub-$1k/mo indie/academic. **Hypothetical** until a first paying conversation. If hypothetical, GPL risk drops a tier; if real/near-term, R9 (license audit) is the most urgent task in the doc.

---

## 5. Research tasks (verify before locking design)

R1–R4, R7 stand. **Rewritten / added:**

- **R6 (rewritten) — MD visualization + interchange stack.** Size integration of **MDAnalysis + NGLView + Molecular Nodes**. HDF5/numpy as interchange. **USD research dropped for MD** (AUDIT A5).
- **R8 — Name / trademark collision.** Pre-publication gate. Run against `simval` (and whatever final name D6 lands) on PyPI/Docker Hub/GitHub.
- **R9 (added) — License audit per tool.** Pre-paid-layer gate. GROMACS (LGPL/GPL), Blender (GPLv3), OpenFOAM (GPLv3). Confirm arm's-length invocation (subprocess/container/MCP socket) keeps the proprietary tier non-derivative. See §11.

**R1/R2/R5/R6 are best answered by building the Phase-1 slice, not by more research** (AUDIT A12). Do not front-load them.

---

## 6. Risk register

| Risk | Severity | Mitigation |
|---|---|---|
| **Security / RCE surface (bpy = RCE as a feature; shared-kernel containers; MCP prompt-injection CVEs)** | **Critical** | rootless/gVisor/Kata; `--network=none --read-only`; digest-pinned images; **human approval before generated code runs**; treat MCP tool results as untrusted input (AUDIT A7) |
| Sim-correctness — split into: | | |
| (a) deterministic diagnostics wrong | High | Tier-1 checks unit-tested against known-good + deliberately-broken fixtures; Lean-able where feasible |
| (b) Tier-2 intent judgment missed | High | Human sign-off on export; never auto-approve Tier 2 |
| (c) silent-wrong-physics (right output, wrong model) | High | Out of scope for automation; surface as a check-list for the human |
| (d) "Validator agent" (LLM checking LLM) = correlated failure | — | **Deleted.** Replaced by Tier 1 + human (AUDIT A4) |
| **GPL vs paid layer** | High (if paid) / Low (if not) | §11; arm's-length invocation only; R9 gate |
| **Meta-risk: over-planning & solo bandwidth** | **High (up-rated)** | §10 kill criterion; 2–3 wk timebox; this is one of ~10 projects |
| Cost / context-window (cloud LLM per run) | Med-High | LiteLLM abstraction; cache prompts; budget per sweep |
| Hardware gap vs "local-first" promise | Med | Cloud-assisted LLM is required (A10); state it honestly |
| Scope creep across project portfolio | Med | One-vertical-at-a-time; this doc as gate |
| Upstream churn (MCP / LangGraph) | Med | Thin adapter seams; isolate external APIs |

---

## 7. Phased roadmap (collapsed, timeboxed)

Phase 0 is **folded into Phase 1** (AUDIT A12). No separate research phase.

- **Phase 1 — Thin slice, GROMACS MD.** Build order (diagnostics-first — proves the moat before any agent/UI work):
  1. ~~Diagnostics library (§1.7 Tier 1): energy drift, RMSD plateau + equilibration, FF parameter coverage, param/unit sanity~~ — **DONE 2026-06-26** (34 tests, numpy-only).
  2. ~~Provenance manifest (params, diagnostics, hashes, verdict) + Tier-2 sign-off hook~~ — **DONE 2026-06-26** (`simval.provenance.v1`).
  3. ~~CLI harness: `simval diagnose <run-dir>` → report + manifest~~ — **DONE 2026-06-26**.
   4. **Real-data + execution DONE 2026-06-26.** MDAnalysis adapter (`simval/io.py`); real GROMACS pipeline (`pipeline/`: 1AKI/amber99sb-ildn, 38,392 atoms, em+30ps NVT, native `gmx` 2026.3 + `Dockerfile` A7 boundary). Validated on real dynamics — correctly refuses to false-pass an un-equilibrated run.
      - *Findings:* (i) NVT total energy ≠ drift observable → use conserved-energy/NVE; (ii) tpx v138 `.tpr` skew → `.gro`-first topology.

   **Build queue (reordered 2026-06-26 by §1.5.1 user-proxy — commoditized layer deprioritized):**
   5. **Methods/provenance auto-extract** — `.mdp`/`.top` → structured provenance + rendered methods paragraph. The #1 wedge, near-free. *(next)*
   6. **Prep-sanity checks** — box-vs-cutoff (PME minimum-image), steric clashes, **charge-state/neutralization (gmx-dump net charge + His-tautomer inventory)** — **DONE 2026-06-26**. Caught a real bug in our own pipeline (missing `genion` → +8 unneutralized system → PME artifact risk); pipeline fixed. Protonation-state *correctness* remains Tier-2 (human reviews the surfaced His tautomers).
   7. **Honest claim-scoping + configurable thresholds** — "structural equilibration" (never imply ΔG convergence); system-aware threshold defaults.
   8. *Gate:* a real user conversation (§1.5.1 / AUDIT E.2) before the commoditized layer.
   9. **Commoditized layer (only past the gate):** MCP server → ReAct agent → notebook UI. This is the 60–70% the free composite already ships — do not over-invest (A13, A12).

   **Phase-1 exit criterion:** a target user completes a real weekly task unaided; **the diagnostics flag a deliberately-broken run as failed while passing a sane one**; the user exports a reproducible bundle incl. auto-extracted methods (Tier-2 sign-off included).

- **Phase 2 — Second vertical + data layer + sweep registry/compare.**
- **Phase 3 — Depth + FEP/ΔΔG.** Binding free-energy convergence (BAR/MBAR, FEP overlap, cycle closure), PLUMED/OpenMM interop. **A separate, months-long investment gated on a real user + a domain partner.** This is what makes it a *pharma* tool; Phase 1 is the foundation.
- **Phase 4 — Ecosystem.** Community tool templates, public registry.
- **Phase 5 — Intelligence.** Hypothesis generation, auto-optimization.

---

## 8. Out of scope (prevents creep)

- Writing our own solvers or physics engines
- Forking upstream tools
- **Generative / creative Blender work** (AUDIT A1) — Blender = render target only
- **Glueing multiple solvers behind one frontend** (the "unified sim platform" trap)
- **A physics foundation model** (the DeepMind/PhysicsX game — different weight class; AUDIT A13)
- Mobile-first UI; real-time multi-user collaboration; physical-lab hardware hooks; a custom LLM
- USD/glTF interchange for MD (revisit only if a non-MD vertical needs scene interchange)

---

## 9. Build philosophy & honest reproducibility

- Thin verifiable slice before broad structure. Earn every directory.
- Wrappers over forks. Containers over installs. Arm's-length invocation over deep linking (see §11).
- **Honest two-tier reproducibility (AUDIT A9):** captured artifacts (params, scripts, image digest, seed, hardware/CUDA record) **are re-runnable**; the NL→artifact step is **not** bit-reproducible (LLM is non-deterministic; GPU/CUDA results differ across hardware). **Drop "bit-for-bit" from any external-facing language.**
- **Local-first, honestly:** local-first where it matters (data, control, compute); cloud-assisted where it must (LLM). State this out loud in the positioning (AUDIT A10).

---

## 10. Shelve criteria (no calendar date — Tyler's call, 2026-06-26)

No kill-by date. The project is worked when bandwidth allows. Shelve if **any** of these becomes true:

- The diagnostics layer cannot reliably distinguish a deliberately-broken GROMACS run from a sane one.
- Tyler cannot name (i) the one user, (ii) his own day-2 loop, or (iii) why this beats Tebian/Neutron/Teploy for bandwidth.
- Scope re-expands to "all domains" / "all engines" / "unified sim platform" — that is A12 winning and the project should be parked until there's a real first user.

Status (2026-06-26): criterion 1 is provisionally met — energy-drift diagnostic is green and separates broken from sane runs.

---

## 11. Licensing & open-core boundary (added — AUDIT A8)

GROMACS (LGPL/GPL), Blender (GPLv3), OpenFOAM (GPLv3) are copyleft. **The plan's own "no forks, wrappers-only" rule is what makes a paid layer legal** — arm's-length invocation (subprocess/container/MCP socket) does not propagate copyleft. State this explicitly.

"Deep integration" must mean **deep-at-the-boundary**, never **by-linking**. Linking against GPL headers, statically compiling GPL code, or shipping a derivative work propagates the GPL and poisons the proprietary tier. R9 (license audit per tool) is the pre-paid-layer gate.

---

## 12. Path to a leading product (2026-06-26)

**Realistic target:** the leading OSS *verification + reference-oracle* layer for computational physics — not a leading commercial product (solo; no domain depth, distribution, or capital; AUDIT E3 unchanged).

**The defensible wedge:** ground-truth verification for AI-generated simulations. Surrogate labs (PhysicsX, DeepMind) and the free agent+MCP+Docker composite cannot self-certify their output; deterministic verification against canonical references is the one thing they lack, and its value scales *inversely* with AI volume.

**The compounding moat:** the curated reference-library (canonical benchmark cases per domain) + the deterministic oracle + provenance. Each added reference case is durable and hard to replicate.

**Phases:**
- **P0 — Publishable.** PyPI package, docs, CITATION, agent-oracle demo. *(this turn)*
- **P1 — Reference-library moat.** Expand canonical cases across all domains; version + sign them.
- **P2 — AI-sim verification wedge.** Public oracle API spec + a worked agent-loop demo; "ground-truth for AI sims" positioning.
- **P3 — Community + publication.** Release on r/compchem, GROMACS forum, MDAnalysis Discord; a JOSS paper (the citation path that makes OSS tools "leading").
- **P4 — Sustainability.** NIH/NSF OSS grant tracks or sponsored development. Leading OSS is institutionally funded; solo is not durable long-term.

**What code cannot fix (honest):** leading requires users + community + years + likely institutional funding. The multi-domain port is architecture, not a market. This plan raises the ceiling; the floor remains "find one user." Shelve criteria (§10) still apply.

---

## Changelog

- **v0.3** — post-audit. Applied all 14 §C edits from AUDIT.md. Scope narrowed to GROMACS MD for one user (D1); creative cut (A1). Greenfield Python (D2). Cloud LLM Phase 1 (D3). Verification split into Tier 1 (deterministic, buildable — the headline) + Tier 2 (human sign-off) (D4, §1.7). Phase 0 folded into Phase 1 with 2–3 wk timebox + kill criterion (D5, §10). Name reopened (D6); working package name `simval`. Deleted: MCP Gateway/Registry, 5-agent graph, K8s, USD-for-MD, Validator agent. Added: §1.5 user, §1.6 existence proof, §1.7 verification tiers, §2.5 competitive landscape, §10 shelve criteria, §11 licensing. R6 rewritten (drop USD for MD); R9 added (license audit). Diagnostics-first build order inside Phase 1.
- **v0.3a (2026-06-26)** — kill date removed per Tyler (§10 → shelve criteria only). Phase-1 diagnostics slice **shipped**: 5 Tier-1 checks (energy drift, RMSD plateau, equilibration/ESS, FF coverage, param/unit sanity) + provenance manifest (`simval.provenance.v1`) + `simval diagnose` CLI. 34 tests passing. Criterion 1 of §10 met.
- **v0.3b (2026-06-26)** — **real-data bridge**: MDAnalysis adapter (`simval/io.py`) reads real GROMACS `.xtc`/`.tpr`/`.gro`/`.xvg`. Verified on a real adenylate kinase trajectory — tool returns the scientifically correct verdict (rejects a 10-frame conformational morph as non-equilibrated). Selection+alignment (the PBC/water gotcha) encoded in the adapter. 43 tests. `[gromacs]` optional dep added.
- **v0.3c (2026-06-26)** — **real GROMACS execution**: native `gmx` 2026.3 + 1AKI/amber99sb-ildn pipeline (`pipeline/`) producing real dynamics (38,392 atoms, 30ps NVT). `Dockerfile` + `run.sh` define the containerized recipe (A7 boundary). Tool runs end-to-end on real `.xtc`/`.gro`/`.xvg` and correctly flags the un-equilibrated run. Two refinements filed: NVT→conserved-energy for drift; `.gro`-first topology (tpx v138 skew).
- **v0.3d (2026-06-26)** — **user-proxy roadmap reorder**: §1.5.1 added (scientist-persona review). Pivot away from commoditized agent/UI toward methods/provenance extract + prep-sanity (the layers the named user would actually pilot). FEP/ΔΔG explicitly deferred to Phase 3 (months, gated on user + domain partner). Claim-scoping: "structural equilibration," never ΔG convergence.
- **v0.3e (2026-06-26)** — **the durable build (§1.8)**: reference-oracle for MD. Canonical benchmark cases with stored reference metrics + `validate(run, case)` API — the agent-loop teacher that compounds as AI improves. Reframed "build for the future" as accumulate-durable-assets, not scaffold-largest-now. Charge/protonation prep check shipped earlier this session now folds into the prep-sanity family.
- **v0.3f (2026-06-26)** — **extension architecture (§1.8.1)**: `EngineAdapter` port + `service.py` stable API + thin `web.py` FastAPI dashboard. Diagnose refactored to engine→context→checks (data-driven, no behavior change). Proven seams: a fake fluid domain registers and is discovered; UI endpoints serve. 70 tests. "Ultimate-ready" = interfaces, not pre-built empty domains.
- **v0.2** — naming decided: Omnilator. (Reopened in v0.3 — D6.)
- **v0.1** — initial draft.
