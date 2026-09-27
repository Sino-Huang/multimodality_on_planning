# Node choice for all four algorithms × text / visual / multimodal — issue #146 protocol

Frozen and committed on 2026-09-27 (UTC), before any #146 corpus derivation, render, panel reference,
control episode, training step or model episode. Machine-readable twin:
`configs/experiments/choice-frontier-v7/protocol.json`. Program `choice-frontier-v7`.

The authorization (cap, scope, observation definition and hardware) is in
`docs/experiments/choice-frontier/issue-146-feasibility.md` (author decision, 2026-09-27).

This protocol amends no earlier protocol, script, config or evidence. The following are read or
imported, never edited:

- `outputs/choice-frontier/{v1,o4,v2,v3,v4,v5,v6}/`
- `configs/experiments/choice-frontier{,-v2,-v3,-v4,-v5,-v6}/`
- `scripts/*choice_frontier*.py`
- `examples/planning_benchmark_slice/{choice_frontier,choice_frontier_views,best_first_controller,bfws_episode,iw_episode,bfs_pilot}.py`

The held-out manifest `data/bfws_phase_v1/fresh-test-manifest.jsonl` and
`data/curriculum_pddl/*/dev/` are never read.

## 1. Question

At every expansion the policy chooses which live open-list node the runtime expands next. It does
so for BFS, BFWS, greedy best-first h_add and weighted A* (w = 3, h_add), under text, visual and
multimodal observations. For each algorithm × observation cell we ask two questions:

1. Does learned node choice beat random-valid choice on held-out tasks?
2. Does the text/image split of the main grid reappear for node choice?

## 2. Contract (runtime)

Code: `examples/planning_benchmark_slice/node_choice.py`.

- **Algorithms.** `bfs`, `best_first_width`, `best_first_add_greedy` and `best_first_add_w3`.
- **Runtime ownership.** The runtime owns successor generation and admission, as in the main grid
  and #132. On an accepted choice it expands the chosen node atomically. Successors are generated in
  canonical applicable-action order. Per-successor admissions are runtime-internal and are not
  policy decisions.
  - `bfs`: FIFO. κ = generation serial. Duplicates are states generated before; they are never
    re-enqueued.
  - `best_first_width`: κ = ⟨w, #g, g, σ⟩. w is the novelty bucket at precision 2, computed at
    generation against the #g partition's table. Tables are updated in generation order, unpruned,
    and residual (w = 3) states are enqueued. #g is the unachieved goal count; g is depth; σ is the
    generation serial. Duplicates as for BFS. These are the frozen `bfws_episode` semantics.
  - `best_first_add_greedy` / `best_first_add_w3`: the frozen `ChoiceFrontierController` (#132),
    unchanged. κ = heap head of h_add / g + 3·h_add, ties by serial.
- **Goal test at selection** for all four algorithms. Selecting a goal node solves the task at no
  budget charge. Native BFWS tests at generation; this is a declared deviation. The native-prefix
  gate (§5) checks that the node-choice κ order reproduces the native order.
- **Menu.** At each decision the live open list is shown as unscored opaque labels `c0..cK`, in
  the frozen #132 per-decision seeded Fisher–Yates permutation (`choice_frontier.permuted_menu`,
  master seed 51131). Labels carry no order information.
- **Output.** Canonical JSON `{"expand_choice": "c<i>"}`, validated as in #132. Malformed JSON, a
  wrong key set, an unoffered label or a non-live node is rejected. The first rejection ends the
  episode as `deterministic_invalid_operation`.
- **Budget.** Decision cap = expansion cap = 2·R_t. R_t is the expansion count of the uncapped
  exact episode (§6).
- **Arms.**
  - `exact_reference`: always choose the κ_A head.
  - `random_valid`: uniform over the menu, `random.Random(seed)` per episode.
  - `process_sft`: learned adapter.
  - `zero_shot_base`: base model plus the #141 extractor (§8).
- **Overflow rule, all arms, controls included.** The complete input token count of the next
  observation is measured with the frozen Qwen3-VL processor (`frozen_processor().count`). If
  count + 384 > 32768, the episode ends before that decision as `observation_overflow`, and the
  task is unsolved from that point. Controls therefore depend on the observation type. Overflow
  counts are reported for every arm × cell.

### What node choice means for BFS and BFWS (pre-registered; author decision)

In every observation type, a menu node carries **only its state**. There is no depth, serial,
score, novelty, membership flag or search history. The policy must choose the κ head from the
menu states, the initial state and the goal. κ is not fully identifiable from this observation:

- BFS serial: depth is only approximately inferable.
- BFWS: w depends on search history, and g and σ are not shown.
- w3: g is not shown.
- Greedy h_add: a function of the state and task.

The primary question (learned vs random-valid within 2·R_t) does not need identifiability, and the
identity gate (§5) checks that node choice matters.

## 3. Observations

Code: `examples/planning_benchmark_slice/node_choice_views.py`. Payload schema
`node_choice_model_input_v1`, representations `text-node-choice`, `visual-node-choice` and
`multimodal-node-choice`.

- **text.** A canonical JSON payload with the #72 fact blocks as text lines (`label: facts`,
  `modality_pages.fact_blocks`):
  - `static_context`: objects, types and static facts.
  - `initial_state`.
  - `goal_constraints`: the source-goal blocks.
  - `frontier_menu.states`: one `{choice, facts}` entry per menu node, in menu order.

  No images.
- **visual.** The frozen #132 layout:
  - static-context pages;
  - the unlabelled 128 px initial-state scene;
  - one unlabelled 128 px scene per menu node, labelled `frontier-choice (label c<i>)`, in menu
    order;
  - partial-goal pages.

  The payload has the #132 keys only, and the legend is the #132 legend verbatim.
- **multimodal.** The text payload plus the visual pages.
- **System message.** For the additive algorithms it is the #132 message verbatim. BFS and BFWS
  get the same sentence frame, naming the runtime-owned FIFO order (BFS) or the novelty /
  goal-count / depth priority (BFWS).
- **Payload checks.** Payload keys are checked structurally against the frozen key set per type,
  failing closed.

## 4. Reuse of additive × visual evidence (author decision)

The additive × visual cells use the frozen `visual-choice-frontier-v1` contract. It differs from
the new schema only in the schema/representation strings. The following are reused, and no
additive × visual adapter is trained:

- the #136/#138 adapters (seeds 17/29/71), `outputs/choice-frontier/{v3,v4/seeds}/training`;
- their #139 learned episodes on P2/P2u (`outputs/choice-frontier/v4/panels/<panel>/evaluation`).

The additive × visual controls are recomputed under §2 (CPU). By construction they equal the #139
zoo `exact_reference` / `random_valid` episodes whenever the overflow rule never fires; that
equality is checked. The zero-shot arm is run under the new contract for all 12 cells, additive
visual included (§8).

## 5. Gates (CPU, fail-closed, before any GPU launch)

1. **Native-prefix gate** on every panel task (§6) and every derived corpus episode:
   - BFS: the exact node-choice expansion sequence equals `bfs_pilot.exact_fifo_bfs` (same R).
   - BFWS: the native `bfws_episode.run_best_first_width` expansion sequence is a prefix of the
     node-choice sequence. For corpus episodes, which are truncated, the sequences are compared up
     to the shorter length.
   - Additive: R_t equals the frozen #139 membership value.
2. **Identity gate** (the §1 contract requirement, pre-registered). For each algorithm and
   observation type, compare the seed-17 `random_valid` episode with `exact_reference` on every
   pooled panel task. A pair diverges if the expanded-state sequences differ. A task is
   non-trivial for an algorithm if its exact episode has at least one decision with menu ≥ 2.
   - Verdict per algorithm: `CHOICE_SENSITIVE` if at least one non-trivial task diverges;
     otherwise `ZERO_DECISION_HEADROOM`. That verdict is then the reported outcome for that
     algorithm, with no re-runs or variants.
   - The divergence count and the per-task headroom (decisions with menu ≥ 2) are reported.
3. **Corpus gates** (§7): independent bit-exact re-derivation, token gate, image resolution,
   membership re-hash, teacher-label binding and the augmentation last-label check.

## 6. Panels

- The frozen #139 panels, read-only:
  - **P2** (screened): 11 tasks / 8 domains, `membership_sha256`
    `5c009e856a191ff279195985bec7ddf3bf0041b7ec9ea7dc89fc248e18e114e5`.
  - **P2u** (unscreened): 12 tasks / 7 domains, `495e752e3fa27815d4a7149d69f0786970ce7f59b90f5df388562943fab2f464`.
  - **Pooled**: P2 ∪ P2u, 23 tasks.
- "Screened" keeps its #139 meaning, the additive random-control screen. No new screen is run per
  algorithm.
- **R_t.** For `bfs` and `best_first_width`, R_t is the uncapped exact node-choice expansion count
  with no overflow rule. It is algorithmic and shared by all observation types. The additive R_t
  are the frozen #139 values.
- `configs/experiments/choice-frontier-v7/panels.json` records per task: the task row, R_t for all
  four algorithms, C\* from the #139 membership, and the gate-1 result. It is committed before any
  control or model episode.
- **Views.**
  - Base: the #139 reference views `outputs/choice-frontier/v4/panels/<panel>/reference-views.json`,
    read-only (static pages, goal pages, retained scenes).
  - States not retained there are rendered live by the frozen `ExpandedTaskViews` path, 128 px
    unlabelled.
  - Live renders go to per-episode directories under `outputs/choice-frontier/v7/`.

## 7. Corpus and training recipe (matched to #136)

**BFS and BFWS records.** Built as in #136:

- **Task pool.** The #136 training-task pool, `configs/experiments/choice-frontier-v3/training-tasks.json`
  (sha256 `97dc70ac…0995`): the non-excluded rows, in file order (the #136 seed-major walk). It is
  disjoint from P2/P2u (#139 exclusion b), from the #135 panel and from the expanded-study final
  panel.
- **Teacher.** The uncapped `exact_reference` node-choice episode from PDDL.
- **Eligibility.** A decision is eligible if its menu has ≥ 2 nodes and its **multimodal**
  observation passes the token gate (count + 384 ≤ 32768). Multimodal is the largest type, so an
  eligible record fits every type, and the same records serve text, visual and multimodal.
- **Selection.**
  - The first 64 eligible decisions per (task, algorithm).
  - Walk the tasks until 2048 training records per algorithm; the last task may be partial.
  - The next 16 eligible records are the teacher-forced diagnostics.
- **Drops.** A (task, algorithm) derivation longer than 600 s is dropped (`derivation_timeout`).
  A task whose render fails is dropped for all observation types (`view_render_failed`).
- **Record id.** `<task_id>:<algorithm>:<decision_index>`.

**Scenes.** The same per-task catalog recipe as #136 (`collect_task_scenes`, render profiles
`configs/experiments/issue71/v2/render.json`, backend `http://127.0.0.1:18880`). The catalog holds
the initial state and every admitted successor of each teacher expansion before the last used
decision. It includes unlabelled 128 px scenes, unlabelled static pages and goal pages.

**Additive text and multimodal records.** These are exactly the #136 membership
(`configs/experiments/choice-frontier-v3/membership.json`, `membership_sha256` `f5cc9b2a…c077`):
2048 training + 16 diagnostic records per algorithm. They use the #136 store scenes and pages
(`outputs/choice-frontier/v3/preparation/store.json`), read-only. Menu states are recovered by
replaying the #136 teacher episode from PDDL, and must re-bind to the stored menus. A #136 record
whose multimodal observation would overflow is dropped from both new additive cells and counted;
no replacement is drawn.

**Augmentation.** Each training record appears twice. Copy k ∈ {0, 1} permutes the record's menu
with `run_choice_frontier_v3.augment_menu` (seed `aug:<record_id>:<k>`) and relabels `c0..cK`.
Scenes and fact lists stay bound to their states. The target is the label of the teacher's κ-head
node after the permutation. Check: the target-is-last share must lie within ±5 pp of the chance
rate mean(1/menu size).

**Sample order.** The 4096 samples are shuffled once with `random.Random("order:17")` for every
seed (the #138 pin), so the training seed changes only LoRA initialisation and dropout.

**Recipe.**

- The #136 recipe: `configs/experiments/matched-modalities/study-v5.json` `training` via
  `visual_model.train_visual` (sha256 `1f151846…d72b`).
- One epoch over 4096 samples: 128 optimizer updates. Global batch 32, microbatch 1.
- lr 1e-4, cosine schedule, warmup 0.03.
- LoRA r 64 / α 128 / dropout 0.05, all-linear excluding visual.
- bf16, gradient checkpointing, adamw_torch, weight decay 0, max grad norm 1.
- Backbone `Qwen/Qwen3-VL-8B-Instruct` @ `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b`.
- Adapters are saved in fp32, as in #136–#141.
- Resumability: a checkpoint every 16 updates, resumed by the HF Trainer. This is declared; it does
  not change the optimisation.
- Teacher-forced diagnostics at updates 42 and 84.

**Cells (30).**

- {bfs, best_first_width} × {text, visual, multimodal} × seeds {17, 29, 71}.
- {best_first_add_greedy, best_first_add_w3} × {text, multimodal} × seeds {17, 29, 71}.

**Audit per cell.** r = 64, α = 128, dropout 0.05, steps = 128 = ceil(samples/32), seed, record
count and sample count.

## 8. Evaluation

- **Smoke gate** (the #132 definition, per new cell at seed 17, 10 cells). The tasks are the #132
  subset `expanded-final/storage-compact-919000`, `expanded-final/elevators-compact-914002` and
  `expanded-final/ferry-compact-915000`, with views from
  `outputs/expanded-study/v1/panel-v2/reference-views.json` (read-only). R_t is the uncapped exact
  node-choice expansion count.
  - Rate = accepted calls / model calls over the 3 episodes. **PASS if ≥ 0.5.**
  - On FAIL, that (algorithm, observation) cell's learned evaluation is gated out for all three
    seeds, and the gate outcome is reported for the cell.
  - The smoke also measures seconds per call.
- **Learned.** Each of the 30 cells runs on all 23 pooled tasks (690 episodes), with greedy
  decoding and inference seed 17. The inference block is #136's: float32, `visual_sdpa`, no
  sampling, per-call KV cache. A single input above the 24,000 padded-batch cap is allowed up to
  32,384 tokens, as in study-v5. Additive × visual learned episodes are reused from #139 (§4).
- **Zero-shot base.** 12 cells × 23 tasks, one realisation (seed 17), cap 2·R_t, base model, no
  adapter.
  - The system message is the cell's system message plus the #141 format sentence. The trailing
    clause is observation-specific:
    - visual: the #141 sentence verbatim, "...whose scene appears closest to satisfying the goal
      pages";
    - text: "...whose facts appear closest to satisfying the goal constraints";
    - multimodal: "...whose scene and facts appear closest to satisfying the goal constraints and
      pages".
  - Output goes through the #141 deterministic extractor (`run_choice_frontier_v6_zero_shot.extract_choice`),
    which is re-applied at replay.
- **CPU controls.** `exact_reference` (seed 17) and `random_valid` (seeds 17, 5077, 6131, 7409,
  8527), for all 12 cells × 23 tasks under the overflow rule (1,656 episodes).
- **Independent replay.** Every episode (control, learned and zero-shot) is independently replayed:
  menus, observation bindings and token counts, trusted transitions and the overflow stop.
  Coverage must be complete, or missingness is stated explicitly (0 mismatch required).

## 9. Metrics and pre-registered tests

- **M1.** The #133 trapezoidal solve-vs-budget AUC over m ∈ {1, 1.25, 1.5, 1.75, 2}, weights
  0.125/0.25/0.25/0.25/0.125. An episode solves at m if its goal selection is decision
  ≤ ⌊m·R_t⌋ and the preceding expansions are ≤ ⌊m·R_t⌋. Overflow, invalid and budget stops are
  unsolved. Stochastic seeds are averaged within a cell; tasks are weighted equally.
- **Solved-at-2R.** The m = 2 solve fraction.
- **Uncertainty.** A task-cluster bootstrap, `random.Random(133)` (fresh per statistic), 10,000
  draws, 95 % percentile interval (the #133 convention). Adapter seeds are averaged inside each
  draw.

**Test 1: primary, per (algorithm, observation) cell, 12 cells.**

- D3 = mean over seeds {17, 29, 71} of M1(learned, s) − M1(random_valid; 5-seed mean), on the
  pooled 23 tasks.
- Verdict (the #138 rule, δ = 0.05, equivalence ±0.05), applied in order:
  - **POSITIVE**: lo > 0, D3 ≥ 0.05 and every seed's point > 0.
  - **EQUIVALENT**: −0.05 < lo and hi < 0.05.
  - **NEGATIVE**: hi < 0.
  - **INCONCLUSIVE**: otherwise.
- Family-wise: Holm over the 12 cells at α = 0.05, using the one-sided bootstrap p (share of draws
  with D3 ≤ 0), reported as `beats_random_holm`.
- A smoke-FAIL cell's verdict is `SMOKE_FAIL`. A cell whose algorithm has `ZERO_DECISION_HEADROOM`
  is reported as such.

**Test 2: per panel.** Test 1 on P2 and on P2u separately. The verdict is reported; these are
secondary.

**Test 3: text/image split.**

- For each algorithm, and pooled over the four algorithms (algorithm mean per task), compare the
  learned 3-seed M1 contrasts text − visual, multimodal − visual and text − multimodal. Use a
  paired task-cluster bootstrap and the verdicts SEPARATED_ABOVE (lo > 0), SEPARATED_BELOW
  (hi < 0) and NOT_SEPARATED.
- The same contrasts are computed on D3 (learned − random within the observation type), which
  nets out overflow-driven capacity differences in the controls.
- The comparison with the main grid's split is descriptive, and its direction is stated in the
  closeout.

**Secondary (descriptive).**

- Learned vs `exact_reference` (the remaining gap).
- Learned vs `zero_shot_base`.
- `zero_shot_base` vs `random_valid`.
- κ-head agreement minus chance (on-policy decisions with menu ≥ 2, recomputed at replay).
- The label-position histogram.
- Invalid-output and overflow counts per arm × cell.
- Per-task learned − random differences (concentration).

**Sensitivity (descriptive).** Tests 1 and 3 are repeated after excluding every (task, algorithm)
pair where `exact_reference` overflows under any observation type.

No number above changes after any result is seen.

## 10. Budget, hardware, scheduling

- **Cap.** 400 GPU-h (author decision) on the new ledger `outputs/choice-frontier/v7/budget.json`,
  schedule `docs/experiments/choice-frontier/schedule-v7.json`. Failed attempts count, and these
  hours are never added to any other ledger.
- **Hardware.** 2 × NVIDIA H100 80GB PCIe on `spartan-gpgpu170`, at most one own model worker per
  GPU. The GPU cutoff is 2026-10-11T06:00Z, inside the Slurm allocation.
- **Ports.** MASTER_PORT pool 18870–18873: worker GPU 0 → 18870, worker GPU 1 → 18871. Render
  backends: 18878 (GPU 0 worker), 18879 (GPU 1 worker) and 18880 (CPU preparation). These are
  disjoint from every earlier pool (18800–18863).
- **Execution.** One resumable queue worker per GPU, launched through
  `scripts/run_expanded_study.py launch`. Workers claim slots in a fixed priority order:
  1. training of each cell (BFS/BFWS before additive), then its smoke if seed 17;
  2. learned evaluation, per cell;
  3. zero-shot evaluation, per cell.
- **Stop rule.** A worker claims nothing new once charged GPU-h (terminal attempts plus running
  elapsed time) exceed 380. Unrun work is explicit missingness, dropped in reverse priority order
  (zero-shot first).
- **Failures.** A slot that fails twice is blocked and recorded. The recipe never changes.
- **Estimate** (feasibility note): ~227 GPU-h expected, ~325 if every episode runs to the 2R cap.

## 11. Declared code surface

New files only:

- `examples/planning_benchmark_slice/node_choice.py`: contract, runtime, session, replay.
- `examples/planning_benchmark_slice/node_choice_views.py`: observations and token counting.
- `scripts/run_choice_frontier_v7.py`: stage runner (`validate`, `panels`, `prepare`,
  `audit-prepare`, `controls`, `identity-gate`, `worker`, `status`, `finalize`, `analyze`).
- `configs/experiments/choice-frontier-v7/{protocol,panels,membership}.json` and `*-job.json`.
- `docs/experiments/choice-frontier/issue-146-{feasibility,protocol,closeout}.md` and
  `schedule-v7.json`.
- `tests/planning_benchmark/test_node_choice.py`.
- The evidence tree `outputs/choice-frontier/v7/**`.

## 12. Commit order

1. This protocol and `protocol.json`, before any derivation.
2. Runtime, views, runner, test, `panels.json` and `membership.json`, before any control episode
   or training.
3. Schedule and job files, before the first GPU launch.
4. Analyzer and closeout: the evidence commit.
