# Omnilator — Audit v1 (5-pass synthesis)

> **Register note (2026-09-11):** §A–E below are the historical planning audit
> (pre-rename; kept verbatim). The verification-oracle audit register — the
> authoritative record of oracle-hardening findings against HEAD 7495370 —
> is §F at the bottom of this file.

> Synthesis of five independent analysis passes: competitive positioning, technical architecture, risk/oversight hunt, Hive codebase audit, product/UX/scope.
> Convergent findings (flagged by ≥2 passes) are high-confidence. The audit's own conclusion is in §D.

---

## A. Convergent findings (≥2 independent passes agree)

**A1. Two products, not one — cut creative as a vertical.** *(A, D-implicit, E)*
Generative Blender/Godot art and GROMACS MD share only the Blender binary — different users, workflows, willingness to pay, retention loops. **blender-mcp already ships the creative half for free** (23k★, MIT, opencode/Cursor/Claude-native). Recommendation: Blender = render target for sim output *only*; move generative-creative to Out-of-Scope. **This reopens the naming decision** — "Omnilator" (omni) contradicts a sim-only thesis.

**A2. No user named; and NL-first fights the paying user.** *(A, C, E)*
Experts (comp chemists, CFD engineers, biotech R&D) pay and don't churn — but they want determinism and reproducibility, which NL+LLM actively undermines. NL solves a *novice* problem; novices churn. The expert's actual complaint about GROMACS is "setup is boilerplate and sweeps are hard to manage," not "I wish I could type English at it." That's a tooling problem, not a conversation problem.

**A3. Chat UI contradicts the reproducibility principle.** *(B, E)*
§9 promises reproducibility-from-day-one; §3's chat UI hides provenance. The truthful shape of reproducible science is a **notebook** (Jupyter-shape) with NL-accepting cells + an always-on provenance panel, not "chat + canvas." Chat is the viral demo and the worse product.

**A4. Verification is the real moat — and the biggest hand-wave.** *(A, B, C, E — all four non-codebase passes)*
"Validator agent" must become: **deterministic diagnostics** (energy drift from `.edr`, RMSD/Rg via MDAnalysis, unit checks, equilibration gates) + **human sign-off** for semantic correctness. An LLM-validator checking an LLM-executor is *correlated failure* (same training biases). This is the one thing the free agent+MCP+Docker combo can't do (rated ~5% solved) — so it must be the **headline**, not a Phase-3 line.

**A5. GROMACS→USD is fiction — use the existing stack.** *(A, B)*
No USD/glTF schema for particles/bonds/PBC/thermodynamics; building it is a multi-month second product. Drop it for MD. Use **MDAnalysis** (reads `.xtc/.trr/.edr` natively) + **NGLView** (live) + **Molecular Nodes** (Blender render addon). **HDF5/numpy as interchange.** Reopen USD only if a non-MD vertical needs scene interchange.

**A6. Phase 1 is ~3× over-built.** *(A, B, C, E)*
Gateway/Registry (Anthropic + GitHub now run MCP registries — redundant), the 5-agent graph, K8s — all wrong for solo Phase 1. **Minimal Phase-1 stack:**
```
notebook UI (defer canvas/timeline)
  → one ReAct agent (LangGraph create_react_agent, cloud model via LiteLLM)
  → MCP client (langchain_mcp_adapters, stdio) — no gateway
  → tools.yaml registry (name/transport/command)
  → docker run + mounted ./workspace volume
  → GROMACS MCP server (you write it)
  → MDAnalysis → HDF5/numpy (no USD)
  → NGLView (live) | Molecular Nodes (render)
  → deterministic diagnostics (gmx energy + RMSD + thresholds → pass/fail)
  → JSON provenance manifest (params, image digest, hashes, diagnostics)
```

**A7. Security / RCE surface is unacknowledged — CRITICAL.** *(C primary; D found Hive's eval-skills as a liability to avoid)*
Arbitrary Python via `bpy` = **remote code execution as a product feature.** Containers aren't a default boundary (shared kernel); community images are unscanned; MCP has had prompt-injection / tool-poisoning CVEs. The word "security" appears nowhere in the plan. Mitigations: rootless/gVisor/Kata containers, `--network=none --read-only`, no-default-egress, digest-pinned images, **human approval gate before any generated code runs**, treat MCP tool results/descriptions as untrusted input.

**A8. GPL licensing constrains the paid/cloud layer — unanalyzed.** *(A, C)*
GROMACS (LGPL/GPL), Blender (GPLv3), OpenFOAM (GPLv3). **The plan's own "no forks, wrappers-only" rule is what makes open-core legal** — arm's-length invocation (subprocess/container/MCP socket) doesn't propagate copyleft. This must be stated explicitly + backed by a **license-audit task (R9)**. "Deep integration" must mean *deep-at-the-boundary*, never *by-linking*, or the proprietary tier becomes GPL-derivative.

**A9. The reproducibility claim is internally contradicted.** *(B, C)*
LLM planning is non-deterministic (same prompt → different `.mdp` → different trajectory); GPU/CUDA results differ across hardware; images drift. Honest claim: **captured artifacts** (params, scripts, image digest, seed, hardware/CUDA record) **are re-runnable**; the NL→artifact step is **not** bit-reproducible. Drop "bit-for-bit" from any external-facing language.

**A10. "Local-first" conflates two things.** *(B, C, E)*
- **Execution/data local-first** = achievable, worth defending.
- **LLM local-first** = impossible on 4GB N5000s; marginal even on Proxmox without a 40GB+ VRAM GPU (→ only 7B–32B models, too weak for reliable bpy/GROMACS codegen; they hallucinate `.mdp` params).
**Cloud LLM is effectively required for Phase 1.** Reframe: *"local-first where it matters (data, control, compute); cloud-assisted where it must (LLM)."* Abstract the model behind LiteLLM so local stays a config swap.

**A11. Greenfield Python, not Hive reuse — decided with evidence.** *(B, C, D-audit)*
Hive (`aispace`) is TS/Next.js/Vercel-AI-SDK + hardcoded code-tools + business-SaaS schema (Operator/Inbox/BusinessTemplate, LEGAL/MARKETING agent roles), **dormant ~4.5 months** (last real feature commit 2026-02-11; the May commit is a WIP snapshot). Its agent runtime — the heart of Omnilator — doesn't transfer to Python/LangGraph/MCP. Reuse tax > rewrite cost. The salvageable language-agnostic bits (Docker pool, realtime, queue) are each <400 lines and trivially portable. **`openclaw/` is an unrelated vendored messaging-assistant — ignore it.**
→ Steal 4 *patterns* (not code): (1) container-pool + sandbox flags (`container-pool.ts`, `docker.ts`), (2) circuit breaker, (3) review/approval + LLM quality-gate (maps 1:1 to sim-correctness human-in-loop), (4) realtime event vocabulary + tool-policy model. **§4 #2 and #3 → RESOLVED: greenfield Python.**

**A12. Meta-risk: over-planning may already be the failure mode.** *(C, E)*
A session was spent on naming. Phase 0's R1/R2/R5/R6 are best answered **by building the slice**, not by more research. For a solo dev running ~10 projects, permanent pre-build is the classic death. Highest-leverage move: collapse Phase 0+1 into a **2–3 week timebox with a kill-by date.**

**A13. Competitive landscape is empty; the existence-proof threat is real.** *(A, C)*
- **Surrogate vendors** (PhysicsX, BeyondMath, Navista SimAI) build ML models that *skip the solvers Omnilator wraps* — a strictly better tech vector. Need a thesis for why "orchestrate slow legacy solvers" wins (candidate: "trustworthy ground-truth while surrogates mature").
- **Incumbents** (Schrödinger, Rescale, SimScale, Cadence) own the buyer *and* the natural paid layer (managed reproducible compute). Rescale's model = your paid layer; the wedge is the sub-$1k/mo indie/academic price point they ignore + local-first.
- **Jupyter ecosystem** is where the scientist user already lives and already does CAD+MD+CFD+provenance. "New workbench" is the wrong framing for that user.
- **The composite substitute** (AI coding agent + community MCP servers + Docker) gets ~60–70% for throwaway single-tool work. Omnilator's 30–40% gap is *entirely the unsexy layer*: converters, provenance, verification, job survival. That gap is the product. Lead with it.

---

## B. Decisions the audit forces (the forks)

| # | Decision | Audit recommendation |
|---|---|---|
| D1 | **Scope & user** | Narrow to **one vertical (GROMACS MD) for one user (biotech/pharma R&D; secondary: rusty PI)**. Cut generative-creative. This cascades to name, UI, and registry abstraction. |
| D2 | **Runtime** (was §4 #2/#3) | **Greenfield Python.** Hive = reference only. RESOLVED. |
| D3 | **LLM sourcing** | **Cloud LLM for Phase 1** (Claude/GPT via LiteLLM); local execution/data. Resolves the local-first ambiguity. |
| D4 | **Verification model** | **Deterministic diagnostics + human sign-off**, not an agent. Promote to Phase-1 exit criterion. |
| D5 | **Process** | **Collapse Phase 0 into Phase 1**, 2–3 week timebox, kill-by date. Stop researching, build. |
| D6 | **Name** (was §4 #5) | **Reopen.** If scope narrows to simulation (recommended), "Omnilator/omni" is dissonance. The folder rename shouldn't anchor you. |

---

## C. Recommended concrete edits to PLAN.md (propose as v0.3)

1. **Rewrite §1 vision line** → "reproducible simulation workbench with NL assist, provenance, and shared viz." Drop "creative tools" from the vision; Blender = viz implementation detail.
2. **Add §1.5 "Primary user + JTBD."** Named persona, ARPU, current alternative (Schrödinger/CHARMM-GUI/GROMACS+VMD), daily loop = **parameter sweep + compare (RMSD/Rg/energy) + export reproducible bundle.**
3. **Add §1.6 "Existence proof."** blender-mcp, Jupyter-AI, the agent+MCP+Docker composite, and the % gap table. Lead the pitch with the gap.
4. **Add §2.5 "Competitive landscape"** — surrogates / incumbents / Jupyter / composite, with a one-line wedge each.
5. **Rewrite §3 architecture diagram** to the minimal Phase-1 stack (A6). Soften "Blender universal viz" from axiom to Phase-2 review point; for MD, NGLView/ChimeraX/OVITO are purpose-built.
6. **Delete the MCP Gateway/Registry box** (or reduce to "consume Anthropic/GitHub registries; do not build one").
7. **§3 UI line** → "notebook with NL-accepting cells + always-on provenance panel + comparison view" (not chat+canvas).
8. **Resolve §4 #2/#3 → greenfield Python** (A11). Resolve §4 #5 → **reopened** (D6). Add §4 #6: "paid layer + buyer + price band."
9. **Rewrite R6** → "size integration of MDAnalysis/NGLView/Molecular Nodes" (drop USD research for MD). **Add R9 (license audit per tool)** as a pre-paid-layer gate.
10. **§6 risk register** — add rows: Security/RCE (Critical), GPL/cloud licensing (High), Meta-risk: over-planning & solo-bandwidth (High, *up-rated*), Cost/context-window (Med-High). **Split "sim-correctness" into ≥4 sub-risks**; strike "Validator agent," replace with "deterministic linters + assertions; LLM summarizes only; human sign-off on export."
11. **§7** — collapse Phase 0 into Phase 1 (2–3 wk timebox + kill-by date). Phase-1 exit criterion: *"a target user completes a real weekly task unaided, the diagnostics flag a deliberately-broken run as failed while passing a sane one, and exports a reproducible bundle."*
12. **§9 reproducibility line** → honest two-tier claim (A9).
13. **Add §10 "Kill criterion"** — one paragraph: what observation, on what date, kills Omnilator.
14. **Add §11 "Licensing & open-core boundary"** (A8).

---

## D. What to do RIGHT NOW (the audit's own conclusion)

The five passes agree on one meta-point: **the planning process is at risk of becoming the product.** Naming got a session; Phase 0 as written could eat months for a solo dev who context-switches across ~10 projects — and R1/R2/R5/R6 are lower-information than just building the slice.

So the real fork is binary:

- **(a) Commit and build.** Approve D1–D5, apply the §C edits as v0.3, and start the GROMACS thin slice inside a 2–3 week timebox with a kill-by date. No more research passes.
- **(b) Shelve honestly.** If you can't name (i) the one user, (ii) your own day-2 loop, or (iii) why this beats Tebian/Neutron/Teploy for your bandwidth — Omnilator is architecture-as-fun, and the kind move is to park it until there's a real first user.

Doing another planning round is *not* on this list. The highest-quality next action is a decision, not more analysis.

---

## E. Questions only Tyler can answer (sharpest across all passes)

1. **Opportunity-cost kill criterion:** why does Omnilator get bandwidth over Tebian / Neutron / Teploy? Which of those slips so this ships?
2. **Have you talked to a single comp chemist / CFD engineer / biotech researcher about NL control specifically?** If not, that's task #1 — ahead of any code.
3. **Unfair advantage:** domain knowledge of MD/CFD? Agent orchestration? Viz? If none, a specialist out-executes you on any single vertical. Where do you win?
4. **Would you use this weekly yourself, for what?** If you can't name your own day-2 loop, the target user can't either.
5. **Is "local-first" a religious constraint or a marketing differentiator?** (Audit says: for sim on your hardware it's *factually* cloud-assisted. Are you willing to say that out loud in the positioning?)
6. **Is the paid layer real or hypothetical?** If hypothetical, GPL-licensing risk drops a tier. If real/near-term, R9 (license audit) is the most urgent task in the doc.
7. **Did the naming session feel like progress or procrastination?** (Honest calibration of whether A12 is already active.)

---

## Per-pass one-liners

- **A (positioning):** blender-mcp already ships the creative half free; the only defensible product is the hard half — trusted, reproducible, multi-tool *scientific* sim. Lead with the gap, not "NL workbench."
- **B (architecture):** 3× over-built for solo Phase 1; kill gateway/5-agent/K8s; verification + GROMACS→USD are the two load-bearing hand-waves.
- **C (risk):** §6 covers ~30% of the real surface — security, GPL, silent-wrong-physics, and the meta-risk of over-planning are all missing.
- **D (Hive audit):** greenfield Python; Hive is TS/AI-SDK/code-tools, dormant 4.5 mo; steal 4 patterns, ignore `openclaw/`.
- **E (product/UX):** engineering architecture wearing a product's clothes — no user named, and its three loudest choices (NL-first, chat UI, creative+science) each contradict its own reproducibility principle.

---

## F. Verification-oracle audit register (2026-09-11)

Findings verified against HEAD `7495370` by an external review; implemented
in the commits below. simval is the trust anchor — a false pass is the worst
failure mode, so every fix errs toward failing closed.

| ID | Severity | Area | Finding | Status |
|---|---|---|---|---|
| ORA-001 | P0 | oracle/validate.py | `compare_metrics` silently skipped reference metrics absent from the candidate or lacking a tolerance rule; `all_pass` stayed true for unexamined fields | Fixed — every reference metric is mandatory (missing-from-candidate = FAIL, missing-policy = hard config error); per-case `ignore` list (default empty); count/version-like metrics exact by default; corpus test proves every shipped metric resolves to exactly one rule |
| ORA-002 | P0 | oracle + references | Physical ceilings encoded as abs-distance-from-golden (wave CFL 1.4 passed vs ref 0.5 tol 1.0) | Fixed — `max`/`min`/`interval` bound kinds with finiteness required; wave CFL max 1.0, EM Courant max 1.0, energy-growth ceilings as max, tau interval [0.5,2.0], fourier max 0.5, p_up_swing min 0.9 |
| ONT-001 | P0 | ontos_gravity/orchestrate | Oracle derived body count, horizon, feature modes and events from the candidate stream; orchestrator did not persist radial/restitution/friction/walls | Fixed — immutable `GravityContract` from metadata validated before replay (body count, exact horizon, event schedule) and after (multipole/radial/shells record presence, contact params bit-exact); replay modes driven by the contract; every CLI-affecting field persisted to ontos.json; all 20 corpus examples carry full contract metadata |
| ONT-002 | P0 | ontos.py, ontos_gravity.py | No strict grammar/cardinality/EOF finalization; a header-only v1 stream passed with zero mismatches | Fixed — strict per-version parser state machines (per-tick record order and cardinality, duplicate/omission rejection, no timestamped records outside an open frame, dangling boundary records at EOF rejected, non-consecutive ticks rejected); reference-match independently fails on zero compared records; mutation suite: header-only, TickHeader-only, drop-one, duplicate-one, duplicate-frame, append-after-last-tick |
| ONT-003 | P0 | ontos_gravity.py | v2 Snapshot population parsed but only counted as compared | Fixed — compared against the stream header body count; single-bit flip in a corpus tag-2 payload produces nonzero mismatch_count |
| ONT-004 | P0 | ontos.py, ontos_gravity.py | Totals/State/Body records never checked their tick against the active TickHeader | Fixed — every timestamped record must repeat its frame tick, including pre-tick records vs the TickHeader they precede; tick +/-1 mutations on Totals/State/Body/pre-tick records all rejected |
| ONT-005 | P0 | ontos.py, ontos_gravity.py | Noncanonical encodings aliased (v1 level != 1 became coarse; region coords ry*2+rx unvalidated so (2,0) aliased (0,1)) | Fixed — v1 levels strictly {0,1}; v2 levels documented sets; rx/ry each validated in {0,1} on every region-carrying record; body ids strictly sequenced; body region/level bytes and contact pseudo-id ranges validated |
| ONT-006 | P0 | orchestrate.py, ontos_gravity.py | Friction validated only as `friction < 0.0` so NaN passed | Fixed — all externally-supplied floats (grid spec + ContactParams in streams) require isfinite with positively-expressed range checks at both layers; NaN/+inf/-inf restitution and friction rejected |
| GOLD-001 | P1 | oracle/cases.py | `reference_version` present in goldens but never parsed or gated | Fixed — parsed into ReferenceCase; 0.1.x series accepted; missing/unsupported fails closed before metric comparison (99.0.0 fixture rejected) |
| AUDIO-001 | P1 | ontos_audio.py | Monopole contacts resolved against FINAL collapse mass, not the mass at contact time | Fixed — collapse-mass timeline captured in one stream-order pass at each Contact record (body masses immutable, resolve post-pass); falsifying recollapse test (mass 10 -> contact -> recollapse 20 -> contact); corpus WAVs unchanged (walls corpus carries identical recollapse masses); the ontos Rust CLI already computed mu at contact time |
| PIPE-001 | P1 | context.py, pipeline.py, manifest.py | Applicable diagnostics raising Exception were silently skipped and absent from the all() verdict | Fixed — ImportError from known optional deps is an explicit skip; any other raise from an applicable check (charge_state, hydrogen_bonds, per_residue_rmsf, box_cutoff, steric_clashes) is a failing status=error DiagnosticResult that blocks the verdict; CA-load distinguishes not-applicable (ValueError) from errored |
| ORCH-001 | P1 | orchestrate.py | Grid run names used as filesystem paths, recursively deleted if present | Fixed — names preflight-validated (no absolute/separators/../duplicates) before any filesystem mutation; run directories use internal `cell-<index>` ids with display names kept separate; sentinel-file and ../escape tests |
| ORCH-002 | P1 | orchestrate.py | normalize_spec ran outside the per-cell try, aborting the whole grid | Fixed — normalization inside the failure boundary; errors attributed to cell index/name in an `_error` row; [valid, invalid, valid] yields 3 rows with the third executed |
| ORCH-003 | P1 | orchestrate.py, cli.py | Empty grid loaded fine and `all([])` exited 0 | Fixed — load_grid rejects an empty list; CLI success requires bool(results) |
| IO-001 | P1 | _util.py, validate.py, pipeline.py, context.py | Input selection used first glob match (filesystem-order dependent); provenance hashed one file per pattern | Fixed — semantic inputs require exactly one match (ambiguity = error); RunContext.consumed_inputs tracked by the synthetic/Gromacs/ontos engines; manifest hashes ALL consumed inputs, canonically sorted; mutating any consumed .npy fails verify-manifest |
| DET-001 | P2 | manifest.py, orchestrate.py | Wall-clock timestamps/timings embedded in reports break byte-determinism | Fixed — canonical_digest over the payload with volatile keys (created_at, wall timings) recursively stripped; identical verifications produce identical digests; orchestrate --out carries the canonical digest alongside raw rows |

Golden/reference files touched, and why:

- `references/h2_rhf.json` — `final_energy` renamed to `final_energy_hartree`
  (and its tolerance entry) to match the metric the oracle actually computes;
  `_pyscf_metrics` now also reports `n_cycles`/`scf_last_delta`.
- `references/wave_pulse_stable.json`, `em_pulse_stable.json` — ceilings
  re-encoded as bounds (ORA-002), counts exact.
- `references/fluid_flow_stable.json` — tau as interval [0.5, 2.0] mirroring
  check_tau_stability; tau_in_range exact.
- `references/quantum_spin.json` — p_up_swing as min 0.9 floor.
- `references/diffusion_heat.json` — fourier as max 0.5 mirroring
  check_fourier_stability.
- `examples/ontos*/**/ontos.json` — all 20 corpus runs upgraded with full
  run-contract metadata (mode, ticks, bodies, events, observer, contact
  flags/params, multipole) derived from each stream's own records; the two
  legacy pre-spec-20 examples (`collapse`, `collapse_observer`) marked
  multipole=false. No stream or WAV bytes changed; every example still
  verifies through the full engine path.

---

## G. Verification-oracle audit register, batch 2 (2026-09-12)

Findings verified against HEAD `0bdb2d3` by an external review; implemented
in the commits below. Same posture as §F: simval is the trust anchor, every
fix errs toward failing closed. Three findings (GROM-001, FEP-002,
PIPE-002-residual) are regressions from the §F batch — the locking tests and
half-fixes are corrected this time.

| ID | Severity | Area | Finding | Status |
|---|---|---|---|---|
| FEP-001 | P0 | fep.py, oracle/validate.py, references | MBAR overlap compared as abs-distance from the golden (golden stored 0.0), so a zero-overlap candidate passed while check_overlap() declared it unreliable | Fixed — overlap is a `min` bound invariant (>= 0.05) mirroring check_overlap. `benzene_hydration_fep` RETIRED: the alchemtest fixture's actual MBAR overlap min-eigenvalues (Coulomb leg 7.4e-4, VDW leg 1.4e-8, pymbar 4.0.3) are far below the 0.05 invariant, so the golden as shipped contradicted the domain check; regeneration impossible, case removed (owner decision, documented here — not silently dropped). fep_synthetic remains the shipped FEP reference |
| ONT-007 | P0 | ontos_gravity._main, ci.yml | Standalone/cross-verify CLI path called verify_stream_gravity with expected=None, bypassing the expected-run contract; CI cross-verification used that path | Fixed — the CLI requires the contract: `--metadata ontos.json` or the same flags given to ontos (--ticks/--bodies/--demote-at/.../--restitution/--friction/--test-ic), translated into a GravityContract (gravity) or the life contract check; bare-stream replay exists ONLY behind `--no-contract` with a loud stderr warning and a `[NO CONTRACT]` output marker, and is not used by CI; ci.yml cross-verify now passes the full contract (life cases too) |
| ONT-008 | P0 | ontos_gravity.py | Observer-run contract validation dropped event multiplicity (extra got-want events skipped when observer exists; check_zoom_policy used membership sets), so duplicated RegionLevel records passed | Fixed — both layers compare multisets: check_zoom_policy requires stream events == Counter(policy) + Counter(requested); the verifier contract requires the same equality, computing the deterministic policy from (seed, observer, ticks, requested); metadata carrying an observer but no ticks now fails closed (the policy needs the requested horizon). Duplicate-request and duplicate-policy-record mutation tests reject |
| ONT-009 | P0 | ontos.py, ontos_eng.py, orchestrate.py | Life-mode contract checked event identity/counts but not placement — untimed initialization events accepted at any frame boundary | Fixed — life_contract_problems (shared by the engine adapter and the CLI) attributes every RegionLevel record to the boundary tick it precedes and requires requested events to precede TickHeader 1; any later-boundary occurrence is a contract violation. Moving a scheduled demote to a later boundary fails the ontos_run_contract check |

