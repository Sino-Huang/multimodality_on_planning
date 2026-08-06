# High-Level Execution Plan: Certificate-Guided Adaptive Scaffolding

**Revision 2, 2026-08-07.** Supersedes revision 1. Revision 1 both understated what was built and
sequenced the work so that the one decision that could kill the method — the calibration gate —
came after the most expensive artifact. See *What changed in this revision* for the four owner
decisions that forced the rewrite.

*Amended 2026-08-07: Phase A only. Gate A's stated pass condition referred forward to a number
Phase 3 produces two phases later, so it was not evaluable and has been demoted to a reporting
milestone; two measurement hazards that would have corrupted the probe result are recorded; and
the failure branch is corrected, since width escalation is justified by the vacuous
`width_decision` invariant independently of what the probe finds. No owner decision, phase order,
gate other than A, quota, selector constant, or contract is changed.*

## Purpose

This plan turns `doc/research_proposal.md` into a runnable, method-centered study of **Certificate-Guided Adaptive Scaffolding (CGAS)**. The target is not a broad modality ablation or an attention-analysis paper. The target is a learned controller that selects the least costly bounded support required to preserve a verifier-checked planning certificate.

The execution sequence is intentionally narrow, and its ordering principle is now explicit: **the cheapest decisive experiment runs first, and no expensive artifact is built before the gate that justifies it.**

1. probe whether the planner configuration can supply the corpus at all;
2. correct the trace contract once, carrying every known defect together;
3. run the calibration gate on a pilot corpus — the go/no-go for the whole method;
4. build the production corpus only at the scale calibration derives;
5. train CGAS against matched static and generic-routing baselines; and
6. evaluate the structural fidelity-cost frontier before expanding to other planners or domains.

---

## Current Baseline

### What already exists — and it is more than revision 1 recorded

| Area | Status | Evidence |
|---|---|---|
| Deterministic symbolic Blocksworld benchmark, expert traces, PDDL generation | Complete | `scripts/phase3/`, 159 modules |
| BFS-vs-GBFS provenance decision | **Resolved.** P0 systematic search is canonical FIFO BFS. | `scripts/phase3/cgas_bfs.py` |
| Aligned pre-action renders, replay-valid transitions, semantic verifier, versioned provenance | **Complete and released** at fixture scale | `data/planning_cgas_v1`, release digest `3bc89431…6b3c`, archived byte-for-byte at `data/planning_cgas_fixture_v1` |
| Typed BFS and IW certificates in the released schema | **Complete** | `cgas_certificates.py`, `cgas_certificate_contracts.py` |
| One-invariant counterfactual generator with contract tests | **Complete** — 3-4 counterfactuals per row | `tests/phase3/test_cgas_counterfactuals.py` |
| No-oracle-leakage contract | **Complete**, and already forward-declares `route_label`, `scaffold_costs`, `memory_payload` | `cgas_certificate_contracts.ORACLE_FIELDS` |
| Production corpus machinery: finite lazy candidate streams, characterization runner, immutable checkpoint chain, selector, atomic release gate | **Built and exercised** for one full round (281 candidates characterized, 53 paired-exact) | `cgas_candidate_characterization*.py`, `cgas_production_population*.py`, `cgas_release_gate.py` |
| Test surface | 109 test files under `tests/phase3/` | |

**Revision 1's "Recommended First Milestone" is complete** — one dataset slice with aligned images, replay-valid actions, typed certificates, deterministic verifier results, and one-invariant counterfactuals — with the sole exception of the memory stub. It should be retired, not repeated.

### What is genuinely missing

- A bounded live external-memory interface. No module exists.
- Route labels: the minimum-cost valid scaffold per step. Blocked on the memory cost model, not on the certificate work.
- Any trained planner model, VLM SFT run, or GPU-backed result.
- A production-scale corpus. The pipeline is proven at 12 steps across 4 instances.

### What is blocked, and why the recorded cause was wrong

The production corpus stopped at a proven-infeasible quota: the selector requires 190 paired-exact 4-object rows against a universe closed at 210 with a 15.9% yield, giving a ceiling of 136. That proof is correct and stands.

The *diagnosis* was not. Measuring exactness per planner rather than per pair shows that IW-exact is a strict subset of BFS-exact — 14/14, 23/23, 16/16 across the three object counts. "Paired-exact" is therefore precisely "IW-exact", and BFS alone solves **100%** of 4-object candidates:

| n | emitted | BFS-exact | IW-exact | paired | BFS rate | IW rate |
|---|---|---|---|---|---|---|
| 4 | 88 | 88 | 14 | 14 | **100.0%** | 15.9% |
| 8 | 129 | 89 | 23 | 23 | 69.0% | 17.8% |
| 12 | 64 | 33 | 16 | 16 | 51.6% | 25.0% |
| all | 281 | 210 | 53 | 53 | 74.7% | 18.9% |

The corpus is gated entirely by **IW width-1 solvability on a domain that is not width-1 solvable**. This is a planner-configuration defect, not a quota that needs weakening.

### The cost inversion

Steps-per-instance equals plan length — mean 3.09, median 2 — because training transitions come from the replayed plan, not from search expansions. Yet full BFS traces are persisted at up to 14 GB each:

```
round-1 BFS corpus     2252.75 GB over 1,768,295 events
free on project quota  1.27 TiB   ->  0.58 rounds fit
snapshot-field share   98.5% - 99.5% of stream bytes
```

No further corpus round fits on disk. The three offending fields are exactly reconstructible, verified over 3,953 events on two streams with zero violations:

```
R1  frontier_before[i] == [state_id[i]]
R2  frontier_after[i]  == frontier_after[i-1][1:] + enqueued(i)
R3  visited_after[i]   == sorted(visited_after[i-1] | enqueued(i))
```

Dropping them projects the corpus to ~6.6 GB per round — a 342x reduction. Root cause: the trace contract bounded stream *record count* but never per-record *size*.

### Two latent defects that block the chosen direction

- **`run_iterated_width` does not iterate.** It runs one fixed width. With width frozen at 1, `width_decision` is the constant `"width_1_novel"` in every emitted certificate. The proposal names "valid width transition" as an IW invariant; at fixed width there is no transition to verify. The field currently carries zero information.
- **The IW novelty table is truncated to 200 entries** (`MAX_IW_TRACE_NOVELTY_ITEMS`). At width 1 this never bites — the largest table observed across all 558 streams is 150. At width 2 the table reaches 325 / 3,321 / 14,365 for n=4/8/12, so `seen_feature_delta`, computed as the difference of two truncated snapshots, becomes silently unsound. This is the same snapshot-versus-delta defect as the BFS side and takes the same fix.

### Existing-scope caveat

Phase closeout documents are engineering evidence, not empirical support for CGAS. No training, SFT, real VLM, GPU, or external-service execution is complete. Generated data and historical output roots must be revalidated before they become research inputs.

---

## What changed in this revision

Four owner decisions, taken on the evidence above:

| # | Decision | Consequence |
|---|---|---|
| 1 | **Raise IW to true iterative width 1→2** rather than decoupling the planner arms | Makes `width_decision` a real invariant; lifts the yield that gates the corpus; invalidates the frozen policy digest and the existing streams |
| 2 | **Drop the three redundant BFS snapshot fields** from persistence | 2.25 TB per round becomes ~6.6 GB; makes regeneration affordable, which is what makes decision 1 affordable |
| 3 | **No starVLA — this is a VLM study. Three backbones, not four** | Phase 4 moves to a standalone `planning_vlm/` package; generalization evidence for reviewers without 4x the runtime work |
| 4 | **Re-derive corpus scale from experiment needs** rather than holding 481 | `EXPECTED_*` selector constants become derived quantities, re-specified under a corrected planner |

And two structural changes that follow from them:

- **Calibration moves ahead of the production corpus.** It is the gate that decides whether CGAS is justified at all, and it needs a pilot corpus rather than the full one. Building the production corpus first risks paying for the wrong size.
- **A cheap planner probe runs before any contract change.** Whether width 2 actually lifts IW yield on partial-`on` Blocksworld goals is an empirical question, answerable in hours.

---

## Guiding Decisions

| Decision | Rationale |
|---|---|
| BFS and IW are the P0 algorithms. | Their certificate invariants and memory dependence are precise. |
| IW runs true width escalation 1→2. | Blocksworld is not width-1 solvable, and a fixed width makes the `width_decision` invariant vacuous. |
| Keep the core observation fixed to VLA. | CGAS must not confound support allocation with added task information. |
| FF and Graphplan are P2 only. | Their current semantics require validation or precise approximation labels. |
| Memory is live, bounded, state-keyed, and auditable. | A serialized gold queue is not a valid tool-use condition. |
| Persist deltas, never running snapshots. | The same defect produced a 2.25 TB corpus on the BFS side and an unsound certificate field on the IW side. |
| Corpus scale is derived from the calibration result. | A number fixed a priori is either too small to train on or larger than the study needs. |
| Analysis is calibration-sized. | One failure matrix, one route-calibration curve, and one controller ablation are enough. |
| Every main comparison is budget-matched. | CGAS must beat direct decoding on fidelity and always-on memory on cost. |

---

## Phase A — Planner Configuration Probe

*New in revision 2. Runs first because it is cheap and decisive.*

### Objective

Measure what IW at width 1→2 yields, per object count, before committing to a contract change and a full regeneration.

Note what this probe does **not** decide. Width escalation is justified independently of its
effect on yield: at `local_iw_width=1` there is no width transition, so the `width_decision`
field the proposal names as an IW verifier invariant carries no transition to verify. That is a
certificate-validity defect, and it is repaired by escalation whatever the yield turns out to be.
The probe informs corpus scale and the decoupled-arms question. It is not a referendum on
decision 1.

### Main tasks

- Re-materialize candidates at known raw ranks through the existing pure range API
  (`cgas_candidate_space.build_candidate`). No trace persistence, no BFS re-run, no cursor advance.
- Run IW with true width escalation, behind the probe, without touching the frozen approved policy.
- Measure **per planner, not per pair**, for each object count: width-1 exact rate, width-2 exact
  rate, BFS-only exact rate, expansions, wall-clock, and peak novelty-table size.
- Measure **plan-length inflation against BFS optimal**. Nothing currently checks this, and it
  determines whether width-2 plans are still usable as training targets.

### Two measurement hazards that would corrupt the result

- **The expansion cap can bind at n=12 and read as a planner result.**
  `DEFAULT_LIMITS["local_iw_novelty_max_expansions"]` is 10,000
  (`cgas_partition_contracts.py:15-27`), while the atom-pair universe bound on the width-2 novelty
  table reaches 325 / 3,321 / **14,365** for n=4/8/12. At n=12 the cap can trip before novelty
  exhausts, returning `skipped_resource_limit` and a depressed exact rate at exactly the object
  count that matters most for corpus scale. The probe must pass its own limits mapping with that
  cap raised. It must **not** edit `DEFAULT_LIMITS`, which is contract surface, nor
  `local_iw_max_width`, which is 1 there.
  *Measured 2026-08-07: the hazard did not bind on these instances — the largest width-2 run was
  8,851 expansions — but it was real to guard against, and the cap is still raised in v3 as margin.*
- **"Exact" here is not optimality.** `_planner_record` (`cgas_characterization_rows.py:143-147`)
  defines IW-exact as `"plan_recovery" not in trace` — solved by pure novelty search without falling
  back to `bounded_serial_plan` or goal regression. It is a lower bar than optimality, which is why
  plan-length inflation has to be measured separately rather than assumed.

### Gate — a measurement, not a stop

Gate A as originally written required the width-2 exact rate to "support the corpus at the scale
Phase 3 will derive". Phase 3 runs two phases later, so that condition is not evaluable here and
Gate A cannot fail as stated. It is therefore a reporting milestone, and the pass/fail is deferred
to Phase 0c, where the derived scale exists.

What the probe decides now is narrower and is decidable now: whether width 2 lifts the n=4 rate
enough for the closed 210-identity universe to supply the row count Phase 3 asks for.

If width 2 does not lift the rate materially, the correct response is to return to the owner with
the decoupled-BFS/IW-arms option **in addition to** width escalation, not instead of it. The two
address different defects — decoupling fixes corpus yield, escalation fixes a vacuous certificate
field — and a disappointing yield number is not an argument against escalation.

### Cost

Bounded, but the "hours, not days" estimate assumes width-2 search is cheap and should be checked
before launching. At n=12 the probe is up to ~14K expansions per instance against ~300 grounded
actions each, in Python, across 281 instances. Decide on parallelism or a stratified subsample
in advance rather than after a run overruns.

---

## Phase 0b — Trace Contract v3 and Corpus Regeneration

### Objective

One new persistence contract carrying every known defect, one owner approval, one regeneration.

### Main tasks

- Implement true iterative width escalation in `local_iw.py` so `width_decision` records a real transition.
- Stop persisting `frontier_before` / `frontier_after` / `visited_after`. Add a reader shim that rebuilds `frontier_order_summary` by a running FIFO fold — `cgas_certificate_contracts.py` is the only consumer of a full snapshot, and it already reduces the other two fields to `[0]` and a delta.
- Replace the IW truncated novelty snapshots with emitted deltas, removing the 200-entry cap as a correctness hazard.
- Add the per-record **size** bound the previous contract omitted.
- Re-approve through the existing `cgas_trace_contract_approval` path.

### Owner action required

The width change invalidates the 558 existing streams. Retain the characterization checkpoints and accounting — small, immutable, still evidentially useful. Release the 2.25 TB of stream bytes.

### Gate

Regenerated streams verify under v3, and certificates rebuilt from them match the fixture release's certificate semantics on overlapping instances.

---

## Phase 3 — Pilot Corpus and Calibration

*Moved ahead of the production corpus. This is the go/no-go for the method.*

### Objective

Establish that a recurrent, certificate-localized failure exists, and derive the corpus scale the study needs.

### Main tasks

- Build a **pilot** corpus — the smallest that supports a first-failure matrix, not the production target.
- Train a direct VLM action-plus-certificate baseline on one backbone.
- On held-out calibration instances, record the first failed certificate invariant by family and structural difficulty.
- Freeze the certificate field set, scaffold palette, operation costs, and counterfactual sampling policy.
- **Report the step count required for a stable first-failure matrix and route-calibration curve.** This number sets the Phase 0c target.
- Pre-register the CGAS configuration and the main evaluation split before the method run.

### Scale note to carry in

*Updated 2026-08-07 from the Phase A result and the pilot-sizing analysis
(`.claude/knowledge/calibration-pilot-sizing-2026-08-07.md`).*

Steps per instance equals plan length, because training transitions come from the replayed plan
rather than from search expansions. Width escalation improved this: under width-1 paired-exactness
the set was 53 instances at mean plan length 3.09 (~6.2 steps/instance); under width-2 it is 158
instances at mean 5.22 (**~10.4 steps/instance**), because escalation admits longer-plan instances.
481 instances therefore yields ~5,000 steps rather than ~2,977. Still thin for SFT of an 8B VLM,
but materially less so.

**The "pilot rather than the full corpus" premise is bar-dependent and the bar is unstated.** The
first-failure matrix has 21 cells (7 certificate invariant families × 3 object counts). At >=10
observations per cell the pilot is 204–306 instances — smaller than production, and this phase
ordering pays for itself. At >=30 per cell it is 613–919 — *larger* than the production target,
and the ordering buys nothing, because the production corpus would have to be built to run the gate
meant to size it. **State the stability bar before planning this phase.**

The lever that settles it is off-plan expansions: BFS expands a mean of 275 states per instance
against a 5.22-step plan, a 53× ratio. Harvesting certificate targets from expansions rather than
only from the replayed plan puts every sizing target within reach of 50–100 instances. **Decide
this before Phase 0b**, since it is a question about what the trace contract must retain. Contract
v3 as specified does not foreclose it — the three dropped fields are the reconstructible ones, and
the per-event data off-plan certificates need is retained.

The other levers remain more instances and longer-horizon instances. Decide on evidence, not now.

### Gate — a real stop

At least one recurrent, certificate-localized failure must exist. If certificates rarely fail, or failures are diffuse rather than localized, there is no justified adaptive-scaffolding method and the direction must be reconsidered **before** any production corpus is built.

### Deliverable

A compact calibration report, a frozen CGAS specification, and a derived corpus-scale target.

---

## Phase 0c — Production Corpus at the Derived Scale

### Objective

Build the corpus the study actually needs.

### Main tasks

- Re-specify `EXPECTED_ROW_COUNT`, `EXPECTED_OBJECT_COUNTS`, and `EXPECTED_SPLIT_COUNTS` from the Phase 3 target and the Phase A yields. This is a re-derivation under a corrected planner, not a weakening of a quota under the old one.
- Run the existing characterization-selector round loop, already built and proven for one round.
- Resume materialization, renders, alignment, typed steps, canonical model-independent records, and atomic release unchanged.

At v3 sizes a round is ~6.6 GB rather than 2.25 TB, so round count is no longer disk-bound and the O(rounds²) validation cost stops being decisive.

### Gate

Every row has a decodable image, a replay-valid action transition, and an accepted certificate target. A row lacking any one of these is excluded, not repaired by inference.

---

## Phase 2 — Bounded Live Certificate Memory

*Runs in parallel with Phase 0c. Not on the critical path for the Phase 3 gate — the calibration baseline needs no memory.*

### Objective

Implement the support palette used by CGAS without leaking oracle planner state.

### Main tasks

- Implement `read`, `append`, `replace`, and `delete` for an environment-owned certificate store.
- Key records by search-state identity and certificate version.
- Enforce byte, operation-count, and latency budgets.
- Allow only model predictions or prior verifier-approved certificate entries to be stored.
- Log every operation and returned payload for cost and provenance evaluation.
- Implement identical stores for CGAS and always-on-memory baselines.
- **Generate route labels:** evaluate each permitted scaffold against the verifier and emit the minimum-cost valid one. `ORACLE_FIELDS` already reserves `route_label` and `scaffold_costs`, so the leakage contract is in place.

### Deliverable

A deterministic, audited live-memory interface with a testable no-oracle-leakage contract, and a route-label dataset builder.

---

## Phase 4 — CGAS Planner Model

### Objective

Implement the method and matched baselines.

### Repo surface

**`planning_vlm/` — a standalone top-level package. Not `starVLA/`.** This is a VLM study; the StarVLA framework, action heads, FAST tokenizers, and robot-control paths are out of scope.

### Main tasks

- Add action and typed-certificate prediction heads to the selected VLM backbone.
- Add a small scaffold controller consuming the predicted certificate, prior support use, and a fixed-size observation representation.
- Implement direct, compact-certificate, and memory paths with the same backbone and action head.
- Train route selection from counterfactual minimum-cost labels.
- Implement a parameter-matched confidence or entropy router.
- Keep raw VLA observation, context budget, training examples, and action vocabulary fixed across core methods.

### Backbones — three, not four

Train and calibrate on one; carry the other two for the generalization result that reviewers will expect.

| Model | Role |
|---|---|
| `Qwen/Qwen3-VL-8B-Instruct` | Primary — training, calibration, main result |
| `OpenGVLab/InternVL3_5-8B-HF` | Generalization |
| `allenai/Molmo2-8B` | Generalization |
| ~~`Zyphra/Zamba2-VL-7B`~~ | Dropped — highest integration risk; confirm at detailed-planning time |

### Deliverable

A runnable CGAS model plus direct, always-on-certificate, always-on-memory, and generic-router baselines.

---

## Phase 5 — Main Method Evaluation

### Objective

Measure the structural fidelity-cost frontier with matched baselines.

### Main tasks

- Run at least five seeds when compute permits.
- Evaluate in-distribution and structural OOD grids for horizon, object count, branching, composition, naming, and rendering.
- Report verified certificate fidelity, valid-plan success, scaffold cost, latency, and route optimality.
- Compare at matched cost and matched fidelity against direct and always-on baselines.
- Add uniform certificate/process supervision and a robust-fusion or modality-dropout comparator where feasible.
- Run one controller ablation that removes certificate inputs; do not require an attention-map study.

### Deliverable

Paper-ready tables and figures showing whether CGAS separates from generic routing and from fixed support policies.

---

## Phase 6 — Secondary Generalization and Extensions

### Objective

Test scope only after the main method result is established.

### Main tasks

- Add FF and Graphplan-style certificates only after their exact semantics or approximation labels are locked.
- Run vision-only and language-only stress tests as secondary resource analyses.
- Extend to additional planning domains only if the P0 certificate verifier remains valid.
- Treat cross-task transfer, continuous world models, and broad attention analysis as follow-on work rather than ICLR requirements.

---

## Consequences for the Standing Production Plan

`.claude/plans/production-p0-corpus-experiment-readiness.md` is approved and blocked at Todo 4. This revision supersedes parts of it:

| Todo | Disposition |
|---|---|
| 1 — trace-v1 freeze, trace-v2 contract | **Reopened.** v3 supersedes v2; the fixture freeze and archive stand. |
| 2 — finite lazy candidates | **Stands.** Reused unchanged by Phase A and Phase 0c. |
| 3 — characterization runner | **Stands, re-runs.** Logic unchanged; new contract, new quotas. |
| 4 — 481-row population | **Constants re-derived.** Unblocks by re-specification under a corrected planner. |
| 5-10 — review, approval, staging, release | **Stand.** Sequencing unchanged, run at the derived scale. |
| 11-16 — four-model readiness | **Reduced to three models.** Todo 14 loses its Zamba2 half. |

The 481 target, the paired-exact requirement, and `local_iw_width=1` were all approved decisions. Changing them is the owner's call, recorded here rather than assumed.

---

## Practical Build Order

1. Probe IW width 1→2 on already-enumerated ranks. **(Gate A — reporting milestone)**
2. Ship trace contract v3: width escalation, dropped BFS snapshots, IW novelty deltas, per-record size bound. Obtain owner approval. **(Gate 0b)**
3. Regenerate the corpus under v3; release the v2 stream bytes.
4. Build the pilot corpus and run the direct-VLM calibration baseline. **(Gate 3 — go/no-go)**
5. Freeze the scaffold palette, costs, and route-label policy; derive the corpus-scale target.
6. Re-specify selector constants and build the production corpus. **(Gate 0c)** — in parallel, implement audited bounded memory and route labels.
7. Implement CGAS and matched baselines in `planning_vlm/`.
8. Run the main structural OOD and budget sweep across three backbones. **(Gate 5)**
9. Decide whether FF/Graphplan transfer is justified.

## Recommended Next Milestone

**Run the Phase A probe and report the IW width-2 exact rate per planner and per object count.**

It is the cheapest experiment in the plan, and it sizes the corpus question before anything
expensive is built. It does not decide whether width escalation ships — that is settled by the
vacuous `width_decision` invariant, independently of yield. What it decides is whether escalation
alone is *sufficient* to supply the corpus, or whether decoupling the BFS and IW arms has to
accompany it.

## Immediate Next Steps

1. Implement true width escalation in `local_iw.py` behind the probe, without touching the frozen approved policy.
2. Run the probe over the 281 already-characterized candidate ranks; report **per planner** the
   exact rate, expansions, peak novelty-table size, and plan-length inflation against BFS optimal,
   per object count. Raise `local_iw_novelty_max_expansions` in the probe's own limits so the n=12
   result is a planner measurement rather than a cap artifact.
3. Draft trace contract v3 covering all four corrections, with its unapproved owner packet.
4. Size the pilot corpus for calibration, and decide whether it can reuse the 53 already-characterized paired-exact instances.
5. Specify the bounded certificate-store API and its no-oracle-leakage tests.
6. Create one direct-VLM calibration configuration and one evaluation command that reports first certificate failures.

## Gates and Falsification

| Gate | Passes when | If it fails |
|---|---|---|
| **A** IW width 2 measured | *Reporting milestone, not a stop.* Rates reported per planner and per object count, with the n=12 expansion cap raised so it does not masquerade as a planner result | Pass/fail deferred to 0c. A weak lift argues for decoupled arms **in addition to** escalation, not instead of it |
| **0b** Contract v3 sound | Streams verify; certificates match fixture semantics on overlapping instances; regeneration fits comfortably on disk | Do not regenerate at scale |
| **3** Calibration *(hard stop)* | A recurrent, certificate-localized failure exists | No justified adaptive-scaffolding method — reconsider the direction before building the corpus |
| **0c** Corpus | Derived quotas reached; every row has decodable image, replay-valid transition, accepted certificate | Exclude rows; do not repair by inference |
| **5** Method | CGAS separates from direct on fidelity and from always-on memory on cost | Report the negative result, per proposal §8 |

## Success Criteria for the Research Infrastructure

The repository is ready for the main CGAS experiment when it can:

- emit aligned VLA observations and replay-valid action transitions;
- generate and verify BFS/IW certificates and one-invariant counterfactuals, with every certificate field carrying information;
- persist planner traces at a size bounded per record, not only per record count;
- run a live bounded certificate store with complete operation logs;
- train direct, always-on, generic-router, and CGAS variants from the same dataset in `planning_vlm/`;
- evaluate fidelity, plan validity, scaffold cost, and route optimality on structural OOD splits; and
- reproduce every reported result from a versioned manifest and configuration.
