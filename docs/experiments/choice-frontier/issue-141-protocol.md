# Choice-frontier second realisable policy protocol — issue #141

Frozen and committed before any #141 GPU launch or model episode (2026-09-25 UTC). Machine-readable twin: `configs/experiments/choice-frontier-v6/protocol.json`. This follow-up answers review 20 finding 69(b) (#131): the validated choice-frontier measurement has ranked only one realisable, non-trivial policy (our #136/#138 imitation adapter). It amends no #132–#140 protocol, script, config or evidence. Frozen files (`scripts/*choice_frontier*` up to v5, `outputs/choice-frontier/{v1,o4,v2,v3,v4,v5}/`, `configs/experiments/choice-frontier{,-v2,-v3,-v4,-v5}/`) are imported or read, never edited. The held-out manifest `data/bfws_phase_v1/fresh-test-manifest.jsonl` and `data/curriculum_pddl/*/dev/` are never read. No new panel and no new control episode is created.

## Arm choice (decided before any outcome)

The ticket names two candidate arms. Preference order: (a) InternVL3.5-8B trained with the frozen #138 recipe (seeds 17/29/71), else (b) a zero-shot prompt of the base Qwen3-VL-8B with a relaxed call cap.

**Feasibility of (a), measured on CPU (no GPU used):**

- The stack supports InternVL: `backbone_port.py` pins `OpenGVLab/InternVL3_5-8B-HF@741a7d03…`, the weights are present offline under `HF_HOME`, and `load_training_model` / `VisualPolicy(backbone=…)` / `page_processor_for("internvl3_5-8b")` exist from the #101–#103 second-backbone branch.
- Token cost: under the InternVL processor a 768×1024 page is 3,330 tokens (Qwen 768) and a 128 px scene is 258 tokens (Qwen 64). Over the 4,128 records of the frozen #136 store (`outputs/choice-frontier/v3/preparation/store.json`) the choice observation averages **11,748 InternVL tokens** (max 21,530) against **3,111 Qwen tokens** (max 5,840): ×3.78.
- Training time: the frozen #136 cell took 1.9 GPU-h for 4,096 samples on Qwen. The measured InternVL probe (`outputs/expanded-study/v1/second-backbone-v3/probe.json`, `training_step.visual-state`) took 257.9 s for one 32-microbatch step at ≤ 11,564 tokens, i.e. ≈ 8.1 s per sample → ≈ 9.2 GPU-h per 4,096-sample cell. The token-ratio scaling of the #136 cell gives ≈ 7.2 GPU-h per cell. Six cells (2 algorithms × 3 seeds) cost **43–55 GPU-h of training alone**, before any InternVL evaluation (≈ 3.8× the Qwen per-call input).
- The ticket cap is **30 GPU-h**. Arm (a) with the frozen 3-seed recipe is therefore infeasible within the cap. Shrinking it (fewer seeds or samples) would break the ticket's "byte-identical hyperparameters except backbone" condition, so it is not run in any form.

**Primary (and only) arm: (b) `zero_shot_base`.**

## Arm `zero_shot_base`

- **Model:** the frozen base `Qwen/Qwen3-VL-8B-Instruct@0c351dd01ed87e9c1b53cbc748cba10e6187ff3b`, no adapter, the frozen #136 inference settings (`configs/experiments/choice-frontier-v3/protocol.json` `inference`: float32, `visual_sdpa`, greedy `do_sample: false`, max 384 new tokens, 32K context, inference seed 17).
- **Observation:** the frozen scene-only choice-frontier observation (`build_choice_observation` via `ChoiceFrontierTaskViews.observe_choices`: static task pages, initial-state scene, one unlabelled 128 px scene per frontier state in the seeded permuted menu order, goal pages; the frozen payload and `view_legend`). It is byte-identical to the adapter's observation except the system message.
- **System message (the only prompt change):** the frozen `CHOICE_SYSTEM_MESSAGE` followed verbatim by

  > ` Reply with exactly one JSON object and nothing else, of the form {"expand_choice": "<label>"}, where <label> is one of the frontier_menu choices (c0, c1, ...). Choose the frontier state whose scene appears closest to satisfying the goal pages.`

  Full-message sha256 `d2ea2b658b2fdb8a0b4c2c8cadd7be612186b56eac4526301634d6e62c919022`. Reason: the frozen prompt never states the output format; the adapters learned it in training, and the #135 base answered a bare `c0` (rejected as non-JSON) on its single call. The added sentence states the format and a zero-shot goal-similarity instruction; it adds no privileged information (no h_add, priority, scores or search history).
- **Output extraction (deterministic, part of the policy):** the first `{…}` substring (no nested braces) that parses as a JSON object with exactly the key `expand_choice` and a string value is submitted as `canonical_choice(value)`; otherwise, if the stripped text fully matches `c[0-9]+`, `canonical_choice(text)` is submitted; otherwise the raw text is submitted unchanged. The frozen session then applies its unchanged contract: an unparseable or non-offered choice is rejected and terminates the episode (`deterministic_invalid_operation`). The raw model text is stored per call, and replay re-applies the extractor.
- **Relaxed call cap:** decision cap = expansion cap = **2 × R_t**, the same cap as the learned adapter (R_t = the #135/#139 uncapped exact expansions in the membership rows). The #135/#139 `pretrained_base` rows keep their frozen 1-call cap and are not rerun.
- **One realisation per (task, algorithm):** greedy decoding with a content-seeded menu order makes the arm deterministic. "Seed mean" below is this single inference-seed-17 realisation.

## Panels and reused evidence (read-only)

- `v2`: the frozen #135 validation panel `configs/experiments/choice-frontier-v2/membership.json` (12 tasks; sha `b2d909cafc22efd3997fdfaa312fd8b04af5725f0e672ffa2f0d9be70311cd07`, asserted). It was used throughout the #136–#140 development line: **development-stage**.
- `p2`: the frozen #139 held-out P2 panel `configs/experiments/choice-frontier-v4/membership-p2.json` (11 tasks; sha `5c009e856a191ff279195985bec7ddf3bf0041b7ec9ea7dc89fc248e18e114e5`, `confirmatory: true`, asserted).
- P2u is not evaluated (optional in the ticket; omitted to keep the matrix to the two pre-registered panels).
- Controls and the exact-eps ladder: `outputs/choice-frontier/v2/zoo` (#135) and `outputs/choice-frontier/v4/panels/p2/zoo` (#139). Qwen adapter (3 training seeds 17/29/71): #135 panel from `outputs/choice-frontier/v3/evaluation` + `outputs/choice-frontier/v4/seeds/evaluation`; P2 from `outputs/choice-frontier/v4/panels/p2/evaluation`. Native views: `outputs/choice-frontier/v2/reference-views.json` and `outputs/choice-frontier/v4/panels/p2/reference-views.json`; live renders go under `outputs/choice-frontier/v6/evaluation/<panel>/views`.
- The analyzer recomputes the reused control and adapter per-task M1 through the frozen loaders and asserts equality with `outputs/choice-frontier/v4/panels/metrics/analysis.json` (`arms.<panel>`).

## Matrix

`zero_shot_base` × 2 algorithms (`best_first_add_greedy`, `best_first_add_w3`) × (12 + 11) tasks = **46 model episodes**, 4 jobs `cfv6-evaluate-<panel>-<algorithm>`.

## Smoke check (infrastructure, not a gate)

The #132 smoke definition on this arm (job `cfv6-smoke`): `expanded-final/{storage-compact-919000, elevators-compact-914002, ferry-compact-915000}` × 2 algorithms, seed 17, greedy, cap 2 × #132 R, native views `outputs/expanded-study/v1/panel-v2/reference-views.json`. It reports the accepted-call rate against the 0.5 threshold and `audit-smoke` replays the 6 episodes. **It does not gate the evaluation:** an arm that emits invalid choices is measured as such, which is itself a result. The evaluation is blocked only if the smoke job crashes on infrastructure (relaunch rule below).

## Replay

`finalize` independently replays every episode of both panels (fresh PDDL authority; inputs, menus, view bindings, trusted runtime results, results) and re-applies the extractor to every stored raw model text. Analysis requires 0 missing and 0 mismatches.

## Metrics and bootstrap

M1 = the #133/#135 trapezoidal solve-versus-budget AUC over m ∈ {1, 1.25, 1.5, 1.75, 2} (caps 2 × R_t; functions imported from `scripts/analyze_choice_frontier_v2.py`), per task averaged over the two algorithms, stochastic controls averaged over their 5 seeds. Intervals: paired task-cluster percentile bootstrap, `random.Random(133)`, 10,000 draws, 95% (the #135 convention). Each draw resamples tasks; the adapter's 3 seeds are averaged inside the draw.

## Pre-registered endpoints (per panel: `v2`, `p2`)

1. **Primary — D3** = M1(zero_shot_base) − M1(random_valid). The #138 rule, δ = 0.05, equivalence ±0.05, in order: **POSITIVE** lo > 0 and D3 ≥ 0.05 and every seed's point > 0 (one realisation here); **EQUIVALENT** −0.05 < lo and hi < 0.05; **NEGATIVE** hi < 0; **INCONCLUSIVE** otherwise.
2. **Co-primary — S** = M1(zero_shot_base) − M1(exact-eps-0.75). **SEPARATED_ABOVE** lo > 0; **SEPARATED_BELOW** hi < 0; **NOT_SEPARATED** otherwise.
3. **Co-primary — A** = M1(zero_shot_base) − M1(Qwen adapter, 3-seed mean), paired by task and algorithm. In order: **SEPARATED_ABOVE** lo > 0; **SEPARATED_BELOW** hi < 0; **EQUIVALENT** −0.05 < lo and hi < 0.05; **NOT_SEPARATED** otherwise.

Verdicts on P2 are held-out confirmatory; verdicts on the #135 panel are development-stage.

## Descriptive

- Pooled 23-task (v2 ∪ P2) D3, S and A with the same rules (descriptive).
- Per panel and pooled: arm M1 with interval, M1 of every control/ladder rung and of the adapter per seed; **ladder position** of the arm per panel and on both panels together (pooled rung M1s).
- Exact two-sided **sign-flip permutation p-value** over the per-task differences for every D3, S and A (per panel and pooled; all 2^n sign vectors; p = share with |mean| ≥ |observed| − 1e-12). Descriptive, answering review 20's small-cluster concern.
- Teacher agreement − chance, first/last-label rate, solved at 2×, terminations (incl. invalid-output terminations), valid-output rate, extractor-rule usage, and the D3 vs eps-0.50 separation.

## Prediction (pre-registered)

The zero-shot base will mostly emit valid choices, but its choices will be close to uniform over the frontier: D3 within ±0.05 of 0 (EQUIVALENT or INCONCLUSIVE, not POSITIVE), S SEPARATED_BELOW and A SEPARATED_BELOW on both panels, ladder position at the random_valid rung. **Either outcome is a result:** if the instrument ranks the zero-shot arm with random-valid and below the adapter, that shows the measurement separates a trained from an untrained realisable chooser; if the zero-shot arm scores above random-valid or matches the adapter, that says the adapter's effect is not specific to training.

## Budget and scheduling

New ledger `outputs/choice-frontier/v6/budget.json`, schedule `docs/experiments/choice-frontier/schedule-v6.json`: cap **30 GPU-h**, allocation `choice_frontier` 30, never summed with any other ledger. GPU 0 only (GPU 1 belongs to #142 unless it reports it free). MASTER_PORT pool **18840–18843**; the render backend for this ticket runs on **port 18848** (`http://127.0.0.1:18848`, a dedicated `scripts/serve_issue70_planimation.py` process under the hub process tool). All GPU work goes through `scripts/run_expanded_study.py launch`.

Estimate: the adapter's calls took 5.4 s on average (1,501 #138 calls). Worst case every episode runs to its cap (#135: 458 + 386, P2: 394 + 366 calls) at ≤ 30 s per call (prefill plus up to 384 decoded tokens): ≤ 3.8 GPU-h per job, ≤ 15.3 GPU-h total plus 0.2 smoke. The expected cost is ≈ 3 GPU-h. Each job has `max_seconds` 14,400.

Infrastructure failures are relaunched at most twice with an explicit `resume_reason`. The arm, prompt, extractor and cap never change.

## Code

- `scripts/run_choice_frontier_v6_zero_shot.py` (stages `validate`, `smoke`, `audit-smoke`, `evaluate-inputs`, `evaluate-worker --panel P --algorithm A`, `audit-evaluate-worker`, `finalize`). It imports the frozen v3/v4 machinery (task loading, views, policy loading, the #136 inference settings) and keeps its own session factory, episode runner and replay for the new condition.
- `scripts/analyze_choice_frontier_v6_zero_shot.py` → `outputs/choice-frontier/v6/metrics/analysis.json` with blocks `primary` (D3 per panel), `co_primary` {S, A per panel}, `pooled`, `per_panel`, `ladder_position`, `permutation`, `behaviour`, `reuse_checks`.
- Job files `configs/experiments/choice-frontier-v6/cfv6-*-job.json`; test `tests/planning_benchmark/test_choice_frontier_v6_zero_shot.py` (extractor rules, verdict boundaries, exact sign-flip p-value).

Freeze order: (1) this protocol and its JSON twin, pushed before any launch; (1b) the schedule with the protocol; (2) runner, analyzer, test and job files, committed before the first model episode; (3) evidence, closeout. No number above changes after any result is seen; any change is a dated amendment written before the affected outcome exists.
