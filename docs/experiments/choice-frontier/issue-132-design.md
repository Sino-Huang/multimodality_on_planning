# O3: choice-sensitive additive arm — frozen design (#132)

Frozen on 23 September 2026 (UTC) before any corpus materialization, model
outcome, or GPU launch of this window. Implements issue #132 as the
pre-registered follow-through of the #130 identity-audit finding
(`docs/experiments/native-arms/issue-130-design.md`, closeout
`issue-130-closeout.md`). No frozen arm, protocol, or published evidence is
modified: the native-arms v3 protocol, its store, episodes and ledgers, and
the #126–#130 artifacts are untouched.

## 1. Why: the finding this answers

The #130 identity audit established that the additive Search-Process contract
has zero decision headroom **structurally**: random_valid is decision- and
expansion-identical to exact_reference on 48/48 (task, algorithm) pairs
(`outputs/native-arms/v1/identity-audit.json`, verdict
`ZERO_DECISION_HEADROOM`). The structural basis is code: every decision submits
one remaining candidate, `finish_expansion()` requires the complete candidate
set, and heap serials derive from the deterministic sorted candidate order at
`start_expansion`, so frontier evolution is submission-order invariant. Under
that contract the policy is a candidate *enumerator*; choice quality is
unmeasurable by construction, so no panel selection can create headroom.

## 2. The redesign: choice-sensitive additive contract

One new arm, `visual-choice-frontier` (recipe `visual-choice-frontier-v1`),
implemented in `examples/planning_benchmark_slice/choice_frontier.py` +
`choice_frontier_views.py`.

**Contract inversion.** The runtime owns the frontier; the policy selects
**which frontier state to expand next**:

- At each decision the trusted runtime exposes the live frontier membership as
  an **unscored menu** of opaque choice labels `c0..cK`, assigned after a
  seeded Fisher-Yates permutation of the generation-serial member order
  (per-decision seed `int(sha256(f"{51131}|choice-frontier-menu|{sha256(canonical(serial_state_ids))}")[:8])`,
  master seed 51131, disjoint from every prior frozen seed).
- The policy's observation is **visual-only**: static task-context pages, the
  unlabelled 128px initial-state scene, one unlabelled 128px scene per
  frontier state **in menu order** (each labelled
  `frontier-choice (label c<i>)`), and the partial-goal pages. The payload
  carries only `algorithm`, the choice-label list, `representation`,
  `schema_version`, and the frozen legend. No state identifiers, scalar search
  values, scores, membership flags, search memory, accepted deltas, or history
  — the scenes are the only decision-relevant channel. `assert_no_text_leak`
  fails closed on any forbidden quoted key marker.
- The output contract is canonical JSON `{"expand_choice": "c<i>"}` with
  exactly one key. The trusted runtime validates strictly: malformed JSON,
  wrong key set, non-string label, label not offered by the pending menu, or
  label bound to a non-live frontier member each reject; the first rejection
  terminates the episode as `deterministic_invalid_operation` (mirrors the
  frozen convention).
- On acceptance the runtime performs the expansion **atomically**:
  `ChoiceFrontierController.expand_member` pops the *chosen* member from
  `_frontier_entries`, then inherits candidate generation (sorted grounded
  applicable actions), serial assignment (`serial_start + offset`,
  `setdefault` per target), admission (`apply_operation`, same code path as
  `start_expansion`/`apply_raw_output`), duplicate detection, reopening and
  `finish_expansion()` bookkeeping **verbatim** from the frozen
  `BestFirstController`. The per-candidate admissions are runtime-internal and
  do not count as policy decisions; one submitted choice = one decision.
- **Goal at selection**: selecting a frontier member that satisfies the goal
  solves the task without an expansion (`goal_reached`, zero budget charge).
  The exact episode therefore takes reference_expansions + 1 decisions.
- **Binding budget**: `decision_cap = expansion_cap = 2 × reference_expansions`
  (controller `max_budget`; the session stops at `decision_budget_exhausted` /
  `expansion_budget_exhausted`). Termination reasons: `goal_reached`,
  `frontier_exhausted`, `decision_budget_exhausted`,
  `expansion_budget_exhausted`, `deterministic_invalid_operation`.
- `best_first_controller.py` is **not modified**; the variant subclasses it
  and reuses its admission internals. The frozen enumeration contract and all
  published episodes are untouched.

**Why random_valid ≠ exact_reference by construction.** exact_reference always
selects the heap head (reproducing the frozen v3 exact traces expansion for
expansion); random_valid selects uniformly from the live menu
(`random.Random(seed)` per episode, seed semantics identical to the frozen
controls). Whenever a decision sees a frontier of size ≥ 2 the two controls
diverge with probability `1 − 1/K`; the episode's expansion sequence then
differs. On the derivation smoke task 131/132 decisions had menus ≥ 2 and
random_valid diverged from exact at decision 3 and exhausted the decision
budget unsolved. This is the property the identity audit (§6) re-measures as
the pre-registered gate.

**Menu permutation** guarantees the label carries no positional information:
label ↔ state binding changes per decision via the seeded permutation, so the
policy must ground its choice in the scenes, not in label positions.

## 3. Corpus: teacher traces under the new contract (CPU)

`examples/planning_benchmark_slice/choice_frontier_corpus.py` replays the
frozen paired-phase v3 exact traces
(`data/best_first_paired_phase_v3/exact-traces/pairs`) through the new contract
on CPU and freezes the membership at
`configs/experiments/choice-frontier/membership.json` (sha256 pinned in the
protocol).

**Algorithm naming.** The ticket's parenthetical "(best_first_add_greedy,
best_first_add_astar)" names the two additive algorithms of the frozen study;
the frozen membership and runtime register them as `best_first_add_greedy` and
`best_first_add_w3` (weighted A*, w=3 — the study's A*-family additive arm).
This design freezes `best_first_add_greedy` + `best_first_add_w3`, the same
pair the #130 audit and the native arms ran.

**Membership freeze rule (pre-registered).** The frozen matched-modalities
membership (512 training + 27 diagnostic record ids per additive algorithm,
`configs/experiments/matched-modalities/membership.json`, sha256
`f939f864…bfbc23`) indexes **old-contract decisions**. Each old decision maps
to the expansion whose candidate set it submitted into (per-event decision
cumsum of the stored exact trace). Unique (task, expansion) pairs in
first-occurrence order form the base set (357 greedy / 355 w3). Because
several old decisions share one expansion, the set is topped up to 512 by
round-robin over the frozen task order (first occurrence in the frozen
training ids), each pass taking the task's next uncovered expansion index.
Diagnostics are the unique-expansion set of the frozen diagnostic ids (11 per
algorithm), no top-up. Record ids keep the frozen shape
`{task}:{algorithm}:{expansion_index}`. Result: exactly 512 training + 11
diagnostic records per algorithm over 26 training tasks (+1 diagnostic-only
task), identical task mix to the frozen study's additive cells.

**Teacher target.** At membership decision e the teacher output is the exact
reference choice: the menu label bound to the heap head (canonical
`{"expand_choice": "c<i>"}`).

**Verification gates (all fail-closed, CPU, before any training).**

1. **Exact-trace gate**: every derived episode matches its stored exact trace
   expansion for expansion — same expanded state order, same per-candidate
   actions in grounded order, same trusted runtime fields (`status/g/h/
   priority/best_cost_before/target_state_id`) per admission, same expansion
   and reopen totals. 54/54 episodes (27 tasks × 2 algorithms) must match.
2. **Token gate**: every record's measured input tokens + 384 ≤ 32768.
3. **Leak gate**: `assert_no_text_leak` per record.
4. **Image-resolve gate**: every bound scene/page resolves to a file.
5. **Membership gate**: materialized record ids == frozen membership ids.

Scenes: v5 scene-only store (`outputs/matched_modalities/v5/preparation/
scene-views.json`, outcome PASS, recipe `scene-only-128-unlabelled-v1`) covers
all 26 training tasks; missing menu-state scenes are rasterized from retained
catalog VFG stages at 128px unlabelled (same `_render_states` machinery as the
native arms). Static/goal pages come from the v5 store or the task's frozen
32k view manifest `reusable_pages`.

Store: `outputs/choice-frontier/v1/preparation/visual-choice-frontier/store.json`
(schema `choice_frontier_scene_store_v1`) + `report.json`.

## 4. Training: identical recipe

Two cells: `visual-choice-frontier × {best_first_add_greedy, best_first_add_w3}`,
each 512 records in frozen membership order, one per GPU. Recipe byte-identical
to the study-v5 training block (sha256 `1f1518…d72b` pinned): seed 17, 16
optimizer updates, LoRA r64/α128/dropout 0.05 all-linear excl. visual, lr 1e-4
cosine, warmup 0.03, global batch 32, microbatch 1, bf16, gradient
checkpointing, final checkpoint at update 16 only. Backbone
`Qwen/Qwen3-VL-8B-Instruct @ 0c351dd…ff3b` (project-local HF cache). Post-hoc
audit enforces r=64, α=128, steps=16, seed=17, 512 records per cell. Output:
`outputs/choice-frontier/v1/training/visual-choice-frontier/<algorithm>/final`.

## 5. Smoke gate (pre-registered, before evaluation)

Frozen subset: the 3 cheapest panel tasks (storage-compact-919000,
elevators-compact-914002, ferry-compact-915000) × 2 algorithms = 6 episodes,
learned adapter, seed 17, 2× reference decision cap, greedy decoding. Measure:
schema-valid grounded rate = accepted calls / total calls. Gate: PASS iff rate
≥ 0.5 (the frozen native-arms threshold). FAIL → the arm's model evaluation is
gated out and that is the reported outcome.

## 6. Evaluation + identity-audit gate

Frozen panel membership: the 9-task panel from the native-arms v3 protocol
(sha256 canonical form `20ea888d…e854`, unchanged). Conditions per
(task, algorithm): `learned_adapter` (seed 17), `pretrained_base` (seed 17,
hard 1-call cap), `random_valid` (seeds 17, 5077, 6131, 7409, 8527 — the
frozen prime set, disjoint from prior windows' control seeds),
`exact_reference` (seed 17). Episodes: 36 GPU (18 learned + 18 base) + 108 CPU
controls (90 random + 18 exact) = 144 total. Decision cap 2 × reference
expansions per episode; expansion cap identical.

**Identity-audit gate (the redesign's own pass condition, pre-registered).**
For each of the 18 (task, algorithm) control pairs compare the seed-17
random_valid episode against the exact_reference episode: divergent iff the
expanded-state sequences or the decision/expansion counts differ. Verdict:

- ≥ 1 divergent pair → `CHOICE_SENSITIVE`: the contract measures choice; the
  audit reports per-pair divergence plus the headroom profile (per-episode
  count of decisions with menu size ≥ 2 in the exact episode).
- 0/18 divergent → `ZERO_DECISION_HEADROOM`: the redesign failed; that is the
  reported outcome. No re-runs, no variant shopping.

**Independent replay.** Every episode (model and control) is independently
replayed at finalize: `replay_choice_episode` re-derives every menu binding,
payload and trusted transition from the stored events and asserts equality of
inputs, menus, runtime results and the final result, through the frozen views
class (`ChoiceFrontierTaskViews`, read-only) so pixel bindings are checked
against retained scenes. Complete coverage or explicit missingness.

**Analysis.** Frozen bootstrap conventions: paired whole-problem unit, seed
61813, 10000 resamples, percentile 95% interval, materiality = interval
excludes 0, strata with < 8 cells descriptive-only. Contrasts:
`learned_minus_pretrained_base` (per task × algorithm success delta),
`learned_minus_random_valid` (random frequency over the 5 seeds),
`random_valid_minus_exact_reference` (the headroom demonstration). Primary
measure: `invariant_valid_success` (goal reached ∧ zero invalid operations);
secondary: decision/expansion counts.

## 7. Budget, schedule, execution rules

Window: `docs/experiments/choice-frontier/schedule.json`, program
`choice-frontier-v1`, branch `choice_frontier`, cap **12.0 GPU-h** (ticket
realized estimate 4–8). Frozen estimand: training 2 × 0.73 (2 × the native-arm
0.36334 GPU-h cell basis, conservative for larger menu inputs) + smoke 0.1 +
evaluation 1.0 (168 learned calls + 18 base calls over 2 workers) + overhead
0.3 ≈ **2.6 GPU-h** planned, reservation inside the 12.0 cap. Ledger
`outputs/choice-frontier/v1/budget.json`; MASTER_PORT pool 18814–18817
(disjoint from every prior pool); scheduler
`scripts/run_expanded_study.py launch --ledger … --schedule …` with frozen job
JSONs under `configs/experiments/choice-frontier/`.

Per the program conventions: protocol frozen and committed before any launch;
no outcome-selected variants; independent replay of every episode; complete
coverage or explicit missingness; commit/push and close only against verified
evidence. Corpus is CPU-only; GPU work is training + smoke + evaluation only.

## 8. Declared code surface

New files only; no frozen file is modified:

- `examples/planning_benchmark_slice/choice_frontier.py` (contract + runtime
  variant + session + replay)
- `examples/planning_benchmark_slice/choice_frontier_views.py` (observation
  contract + views)
- `examples/planning_benchmark_slice/choice_frontier_corpus.py` (membership
  derivation + store + dataset)
- `scripts/run_choice_frontier.py` (stage runner: validate / prepare /
  audit-prepare / train / audit-train / smoke / audit-smoke / evaluate-inputs /
  evaluate-worker / finalize / identity-audit / analyze)
- `configs/experiments/choice-frontier/choice-frontier-protocol-v1.json`,
  `membership.json`, `*-job.json`
- `docs/experiments/choice-frontier/issue-132-design.md`, `schedule.json`,
  closeout at `issue-132-closeout.md`
- Evidence tree `outputs/choice-frontier/v1/**`

Reuse without modification: `best_first_controller.py` (admission internals),
`native_arm_corpus._render_states`, `expanded_views.ExpandedTaskViews`,
`visual_model.train_visual` + `VisualPolicy`, `expanded_scheduler.py`, the v5
scene store, the paired-phase v3 traces, the 32k corpus manifests.
