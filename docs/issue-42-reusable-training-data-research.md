# Research note: reusable datasets for T04 (deterministic task instances and splits)

**Issue:** [#42 — "T04: Generate deterministic task instances and splits"](https://github.com/Sino-Huang/multimodality_on_planning/issues/42) (parent spec [#38](https://github.com/Sino-Huang/multimodality_on_planning/issues/38); blocked by #39, #40, #41)

**Scope:** Identify existing datasets that can be reused for training the Search Process Policy program, focused on `data/curriculum_pddl`, feasibility of plan generation (especially IW/search), trace-length constraints, formats, licenses/provenance, and compatibility with the training pipeline.

**Status:** Research note only — no source/config/test edits. Evidence cited with path:line.

---

## 1. TL;DR

- `data/curriculum_pddl/` is the canonical instance corpus and the **primary reuse candidate**: 5,153 accepted instances across 15 IPC domains, three measured difficulty buckets (easy/medium/hard), and three splits (train/dev/test) assigned at **whole-instance** granularity, with per-instance provenance (seed, generator command, hashes) already committed. It supplies an existing whole-instance partition, but does not by itself prove T04's immutable split-ID contract or byte-identical regeneration.
- `data/phase3_supervised_planning/` is a **trace-converted view** of the same instances and is the closest thing to a training-ready corpus, but it currently contains **only BFS Search-Trace Segments** (411 examples). IW/FF/Graphplan were all recorded as `skipped_planner_unavailable` at generation time.
- **IW is now feasible locally** (`scripts/phase3/local_iw.py` is registered and runnable via `generate_curriculum_trace_dataset.py`), but with two caveats: (a) the previous phase3 run predates it, so IW traces must be regenerated; (b) IW "success" often comes from **recovery paths that are not exact IW** (`is_exact_iw: False`), which conflicts with T04/issue-#38's requirement for mechanically checkable algorithm invariants.
- **Trace-length constraints exist and matter:** `max_plan_length = 500` and `gbfs_max_depth = 200` in the pipeline; 218 accepted instances exceed depth 200 (130 hard, 88 medium) and 49 exceed plan length 500. Any reuse must filter or re-stratify against these budgets.
- **License/provenance is the main open risk:** the corpus derives from IPC benchmark generators and Fast Downward (GPL-3.0) plans and is rendered through a GPL-3.0 Planimation backend. The repo itself is MIT. Redistribution of generated/rendered training data needs an explicit provenance/license decision.

---

## 2. Existing datasets that can be reused

### 2.1 `data/curriculum_pddl/` — the provenance-complete instance corpus (primary reuse target)

Layout (`data/curriculum_pddl/summary.json:1-69`):

| Artifact | Evidence | Notes |
|---|---|---|
| 15 domains, 5,153 accepted instances | `summary.json:29` (`accepted_total: 5153`), `:7-23` per-domain | blocksworld, depot, driverlog, ferry, grid, gripper, logistics, etc. |
| 3 measured difficulty buckets | `summary.json:2-6` easy 1860 / medium 1961 / hard 1332 | bucket is a first-class field |
| 3 splits at whole-instance granularity | `summary.json:24-28` train 4199 / dev 475 / test 479 | instance id embeds split+bucket, e.g. `blocksworld-train-easy-0000` (see `result.json`) |
| Regeneration prerequisites | the summary reports zero duplicate normalized problems; rejection reasons include duplicate normalized content and exhausted deterministic variants | committed seeds and provenance support replay, but no byte-identical regeneration comparison was found |
| Per-instance files | `blocksworld/train/easy/*/` → `domain.pddl`, `problem.pddl`, `result.json`, `generator.stdout/stderr`, `render/` (`trace.vfg.json`, `frames/`) | verified at `data/curriculum_pddl/blocksworld/train/easy/blocksworld-train-easy-0000/` |
| Full provenance manifest | `data/curriculum_pddl/accepted_manifest.jsonl` (~27 MB), schema_version 1 | each row records its seed, generator command, domain/problem paths and normalized problem text, difficulty metrics (`plan_length` primary), render details, split, and bucket |
| Rejected instances (useful as negative/selection evidence) | `data/curriculum_pddl/rejections.jsonl` (~46 MB); `summary.json:57-63` | 26,043 rejected, incl. `render_failed: 6086`, `selection_not_selected: 6656` |
| Saved solver plans (lama-first) | `data/curriculum_pddl/diagnostics/fast_downward_plan_saves.jsonl` (5,153 rows); `reports/fast_downward_plan_saves_summary.json` | `success_plan_saved: 5089`, `failed_planner_error: 29`, `failed_planner_timeout: 35`; these are the plans used for rendering |

This corpus provides reusable instances, provenance, and a current whole-instance split partition. T04 still needs an **explicit immutable split-ID contract**, a byte-identical replay check, and **gate/authorization receipt** machinery (outcomes PASS/VALID_STOP/INVALID/ANCESTOR_STOP per `CONTEXT.md:59-65`). These are contract and runtime concerns layered on top of the corpus rather than new instance generation.

The easy/medium/hard buckets are not demonstrated structural strata for T04. The existing generator assigns per-domain percentile buckets using a lexicographic difficulty measure led by plan length (`src/data_collect/difficulty.py:362`); it does not independently vary horizon, branching factor, and object count. Reuse therefore requires a structural-strata mapping or a new selection pass before claiming T04 coverage.

`data/curriculum_pddl_shards/` (`summary.json:33-53`) holds the per-domain pre-merge shards that were merged to build `curriculum_pddl`; it is a source of truth for regeneration but not a distinct training corpus.

### 2.2 `data/phase3_supervised_planning/` — trace-converted, training-adjacent corpus

- 3,600 accepted instances, but **only 411 emitted examples** — all `success_full_trace` (`reports/fidelity_summary.json`); split train 363 / dev 28 / test 20 (`summary.json:71`).
- Format: `schema_version: phase3_supervised_planning_v1` with `model_facing` (domain, planner, `problem_source`, `domain_source`, `vision.frame_paths`, `trace_path`) and `supervised_target` (`plan`, `planner_trace`, `replay_transitions`); schema at `schema/supervised_planning_example.schema.json`.
- **Planner availability gap** (`summary.json:26-38`): `bfs` → `success_full_trace: 411`; `ff`, `graphplan`, `iw` → **all `skipped_planner_unavailable: 3120`**. The June-28 run predates the local IW/FF/Graphplan implementations, so only BFS traces were produced.

### 2.3 `data/pddl_instances/` — original IPC instances + render profiles

- Used as `render_profile_path` for Planimation (`src/data_collect/configs/curriculum_15_domains.yaml:52-138`) and referenced in every `result.json` (`render.render_profile_path`, e.g. `data/pddl_instances/blocksworld/blocksworld_AP.pddl`).
- Source of the domain/AP files needed to render any reused instance.

### 2.4 `data/planning_cgas_v1/` + `data/planning_cgas_fixture_v1/` — demoted CGAS training fixtures

- `data/planning_cgas_v1/qwenvl/{train,dev,test}.jsonl` is the **only corpus the current starVLA training entry point consumes** (`starVLA/dataloader/qwenvl_llavajson/qwen_data_config.py:38-53`), in LLaVA-JSON form with IW and BFS "certificate" targets (see §6).
- **Small fixture only:** 4 rows per split over a single `blocksworld-train-fixture-0000` instance (`data/planning_cgas_v1/manifest.json`). It is a smoke/format fixture, not a training-scale corpus, and reflects the demoted CGAS target (action+Planning Certificate), not the Search Process Policy trace target.

---

## 3. Feasibility of plan generation (especially IW/search)

### 3.1 Local IW is implemented and registered

- `scripts/phase3/local_iw.py:24` `run_iterated_width` implements novelty-table IW; `local_iw_novelty.py:11-22` provides `novelty_items` / `first_novel`.
- Registered in `scripts/phase3/local_planners.py:26-27` (`"iw": run_iterated_width`), and wired into the pipeline via `LOCAL_PLANNER_NAMES = {"ff": "ff", "iw": "iw", "graphplan": "graphplan"}` (`scripts/phase3/pipeline.py:26`, used at `:239-253`).
- The Search-Trace Segment generator `generate_curriculum_trace_dataset.py` sets `DEFAULT_PLANNERS = ("gbfs", "ff", "iw", "graphplan")` (`pipeline.py:24`) and supports `--planner iw`, filters by domain/split/bucket/instance, and writes per-instance `traces/<domain>/<split>/<instance>/{planner}.planner_trace.json` (`generate_curriculum_trace_dataset.py:193-208`). This is the practical path to regenerate IW traces today.

### 3.2 Caveats for IW trace integrity (directly relevant to T04/issue-#38)

1. **Recovery is not exact IW.** When exact IW fails/expands over budget, `local_iw.py` falls back to goal-regression (`recover_goal_regression_plan`) or bounded-serial recovery, tagging the result `is_exact_iw: False` (`local_iw.py:201-248`). Such rows satisfy "a plan was generated" but **do not carry the novelty/width invariants** (`width_decision: width_N_novel`, `novel_item`, `seen_feature_delta`) that issue-#38 requires as mechanically checkable algorithm invariants (`CONTEXT.md:38-39`; spec §"Core algorithm conditions"). A T04-quality IW arm must either accept lower yield (only exact-IW successes) or explicitly mark recovered rows as non-invariant-bearing.
2. **Width escalation is opt-in.** `local_iw.py:34` only escalates width when `local_iw_escalate` is set; default max width is 3 (`local_iw.py:21`). The curriculum generator defaults `local_iw_width = 3` and `local_iw_max_width = 3` (`generate_curriculum_trace_dataset.py:25-26`), i.e. **fixed width-3 IW, no escalation**, with `local_iw_novelty_max_expansions = 500`.
3. **External-planner mode lacks Search-Trace Segments.** If `PHASE3_IW_PLANNER` is set, the pipeline runs an external binary and stores only `{"external_plan_only": True}` replay transitions (`pipeline.py:241-258`, `:352-372`), not an IW novelty trace. The trace target requires the **local** path.

### 3.3 BFS is the proven, low-risk arm

The phase3 corpus already contains 411 validated BFS Search-Trace Segments (queue events, `frontier_size_after`, `successors`) (`data/phase3_supervised_planning/train.jsonl`), consistent with issue-#38's BFS-as-positive-control gate. A* (h_max / landmark) is **not implemented** in the local planner set — only gbfs, ff, iw, graphplan exist (`pipeline.py:24`), so the A* arms from the spec still require new planner work.

---

## 4. Trace-length constraints

Global resource limits (`scripts/phase3/pipeline.py:28-40`):

| Limit | Value | Reuse implication |
|---|---|---|
| `max_plan_length` | 500 | longest accepted instance plan is 766 (hard) → 49 instances exceed 500 |
| `max_trace_steps` | 500 | caps stored trace events |
| `gbfs_max_depth` | 200 | 218 instances exceed 200 (130 hard, 88 medium) |
| `gbfs_max_expansions` | 250,000 | BFS/GBFS budget |
| `gbfs_max_applicable_actions` | 2,000 | per-state branching cap |
| `max_jsonl_target_chars` | 10,000,000 (phase3); 65,536 (older manifest) | rows exceeding this are `skipped_resource_limit` (`pipeline.py:273-277`) |
| `planner_timeout` / `grounding_timeout` | 60 / 60 s | |

Measured corpus difficulty (`data/curriculum_pddl/accepted_manifest.jsonl`): plan length min 1 / max 766 / mean 46.09 / median 19; object count mean ~32 (max 167). Easy bucket plan lengths ≤ 61 (all within limits); hard up to 766.

IW-specific caps (`generate_curriculum_trace_dataset.py:24-31`): `local_max_applicable_actions = 2000`, `local_iw_novelty_max_expansions = 500`, `local_iw_recovery_trace_steps = 20`, `local_goal_regression_goal_threshold = 8`.

**Conclusion for T04:** reuse must apply the frozen budget (`max_plan_length`/`max_trace_steps`/depth) as **selection/stratification** criteria and decide explicitly whether instances above budget are excluded or truncated, so that budget is fixed per difficulty stratum before any evaluation (per spec §"Evaluation": "Budgets are frozen by development difficulty strata before testing").

---

## 5. Formats

- **Instance corpus:** per-instance directories (`domain.pddl`, `problem.pddl`, `result.json`, `render/…`) plus a JSONL manifest (`schema_version: 1`) — see §2.1.
- **Trace corpus:** JSONL, `schema_version: phase3_supervised_planning_v1`; JSON schema committed at `data/phase3_supervised_planning/schema/supervised_planning_example.schema.json`. `model_facing.vision.frame_paths` + `trace_path` link text/visual traces to the same instance (multimodal-state support per `CONTEXT.md:76-77`).
- **Training entry point:** LLaVA-JSON conversation format (`<image>` + task text → action + certificate) consumed by `starVLA/dataloader/qwenvl_llavajson/qwen_data_config.py:38-53`. **No automated converter from `phase3_supervised_planning` JSONL to this LLaVA-JSON format is present in the tree** — this is a concrete pipeline gap to close for reuse.

---

## 6. Licenses / provenance

| Component | License | Location / evidence | Note |
|---|---|---|---|
| This repo (StarVLA) | MIT | `LICENSE`; `CITATION.cff` (`license: MIT`) | the planning research code is MIT |
| IPC PDDL generators | benchmark collection (Zenodo DOI) | `modules/pddl-generators/README.md:1-22` — "generate benchmarks for the International Planning Competition (IPC)"; citation `Seipp/Torralba/Hoffmann 2022`, DOI `10.5281/zenodo.6382173`; basis = FF domain collection (Jörg Hoffmann) | instances derive from IPC benchmark generators; provenance should cite the generator collection |
| Fast Downward / lama-first plans | **GPL-3.0** | `modules/downward/LICENSE.md:1-5` | all saved plans and rendered frames are produced via GPL-3.0 tooling; redistribution of these derived artifacts needs a license decision |
| Planimation backend | **GPL-3.0** | `.slim/clonedeps/repos/planimation__backend/LICENSE*`; AGENTS.md notes it is GPL-3.0, used read-only, **not vendored** | rendered `trace.vfg.json`/frames come from this backend; keep it as an external dependency, do not vendor |
| Generation policy (renderer never plans) | ADR | `docs/adr/0001-use-local-lama-first-for-planimation-production.md` | plans are generated locally (`lama-first`) and submitted as supplied plans; Planimation is render-only — no hosted solver |

**Open question for T04:** whether MIT-licensed training data may incorporate GPL-3.0-derived plan/frame artifacts, and what attribution/citation must be bundled. This is a legal/provenance decision the parent should resolve before release; the code and instance *definitions* are MIT/IPC-benchmark, but the *plans and renders* flow through GPL-3.0 tools.

---

## 7. Compatibility with the training pipeline

- **Instance corpus → trace corpus:** `data/curriculum_pddl` is already the declared `input_root` and `source_manifest` for trace generation (`generate_curriculum_trace_dataset.py:16`; `phase3_supervised_planning` rows carry `source_manifest: data/curriculum_pddl/accepted_manifest.jsonl`). Round-trip is proven.
- **Whole-instance split integrity:** both `curriculum_pddl` (train/dev/test) and `phase3_supervised_planning` (`split` field) assign splits at instance granularity, matching issue-#38 user-story #17 ("whole problem instances as the split unit"). The embedded split+bucket records the current partition but does not prove immutability across regeneration or extension; T04 needs that explicit contract or verification.
- **Missing pieces for full reuse:** (a) IW/FF/Graphplan/A* traces (only BFS is materialized); (b) a `phase3_supervised_planning` → LLaVA-JSON (`qwenvl`) converter for the starVLA training loader; (c) explicit budget-based instance filtering; (d) license/provenance packaging for plan/frame artifacts.

---

## 8. Evidence I could not fully establish

- **A* (h_max / landmark) feasibility:** no local A* planner exists in the pipeline (only gbfs/ff/iw/graphplan), so cost of building the two A* arms is unquantified.
- **End-to-end IW yield on the full corpus:** exact-IW-only success rate (excluding recovery rows) across all 5,153 instances is not recorded anywhere; it must be measured by regenerating traces.
- **Training-scale data quantity:** the `planning_cgas_v1` LLaVA-JSON is a 12-row fixture; the actual scale/composition of a Search-Process-Policy training set is undecided.
- **Byte-identical regeneration and structural-strata coverage:** no committed replay comparison or mapping from the percentile buckets to independently controlled horizon, branching factor, and object-count strata was found.
- **License conclusion:** whether GPL-3.0-derived plan/frame artifacts can ship inside an MIT training dataset is unresolved and needs a decision from the parent.

## 9. Primary evidence references

- Issue #42: <https://github.com/Sino-Huang/multimodality_on_planning/issues/42>; parent spec #38: <https://github.com/Sino-Huang/multimodality_on_planning/issues/38>
- `data/curriculum_pddl/summary.json`; `data/curriculum_pddl/accepted_manifest.jsonl`; `data/curriculum_pddl/diagnostics/fast_downward_plan_saves.jsonl`
- `data/phase3_supervised_planning/{summary,generation_manifest}.json`, `reports/fidelity_summary.json`, `schema/supervised_planning_example.schema.json`
- `scripts/phase3/pipeline.py:24-40,239-258,352-372`; `scripts/phase3/local_iw.py:24-48,201-248`; `scripts/phase3/local_planners.py:22-31`; `scripts/phase3/generate_curriculum_trace_dataset.py:16-31,193-208`
- `src/data_collect/configs/curriculum_15_domains.yaml`
- `starVLA/dataloader/qwenvl_llavajson/qwen_data_config.py:38-53`
- `docs/adr/0001-use-local-lama-first-for-planimation-production.md`; `modules/pddl-generators/README.md`; `modules/downward/LICENSE.md`; `.slim/clonedeps/repos/planimation__backend/LICENSE*`
- `CONTEXT.md:45-77` (governed vocabulary), `:38-39` (algorithm invariants)
