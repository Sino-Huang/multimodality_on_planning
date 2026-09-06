# planning_benchmark_slice

Minimal example for reading one accepted instance from the merged curriculum PDDL dataset.

## Local supplied-plan Render Production

`planimation_render.produce_planimation_render` is the active Planimation production boundary. It accepts an ordered,
non-empty supplied plan and an HTTP loopback base URL, performs exactly one Plan Submission to `/upload/pddl`, and renders
the returned VFG to local PNG frames. Hosted endpoints, absent or malformed plans, and solver fallback URLs raise
`PlanimationRenderError` before any request is sent. Planimation does not select or generate a plan at this boundary.

## Command

```bash
python -m examples.planning_benchmark_slice --dataset data/curriculum_pddl --domain blocksworld --split dev --index 0 --json
```

## Output contract

The command prints JSON with at least:

- `instance_id`
- `domain`
- `split`
- `domain_pddl`
- `problem_pddl`
- `render_trace` (filesystem path to `render/trace.vfg.json`)
- `render_trace_payload` (parsed trace JSON)
- `render_frames`
- `goal_or_problem_view`
- `action_vocabulary` or `action_vocabulary_empty_reason`
- `language_or_text_description`

The loader reads `accepted_manifest.jsonl`, filters by `domain` and `split`, uses zero-based `index`, and resolves the real domain/problem/render files referenced by the selected manifest record.

## Failure behavior

The command exits nonzero with a clear stderr message when:

- `summary.json` is missing
- `domain` is not present in the merged dataset summary
- `split` is not present in the merged dataset summary
- `index` is out of range for the filtered slice
- any referenced PDDL or render artifact is missing

## StarVLA registry smoke dataset

The planning smoke dataset is auto-discovered by StarVLA from:

```text
examples/planning_benchmark_slice/train_files/data_registry/data_config.py
```

It registers:

- robot/data type: `planning_blocksworld`
- named mixture: `planning_blocksworld_dev_smoke`
- repo-relative smoke JSONL artifacts under `outputs/planning_artifacts/dataset_smoke/`

This is intentionally a registry smoke for Task 9 serialized Blocksworld planning
records. It is not a full production LeRobot conversion and does not define
continuous robot action tensors.

If generated outputs are absent or untracked, regenerate them from the repository
root before running the registry smoke:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.generate_experts --fixture tests/fixtures/planning/blocksworld_nontrivial.json --algorithms bfs iterated_width --output outputs/planning_artifacts/expert_smoke --json
```

Then serialize all four modalities:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.serialize_modalities --input outputs/planning_artifacts/expert_smoke --output outputs/planning_artifacts/dataset_smoke --modalities vision language vision_language vision_language_tool --json
```

Registry smoke check:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python - <<'PY'
from starVLA.dataloader.gr00t_lerobot.registry import DATASET_NAMED_MIXTURES, ROBOT_TYPE_CONFIG_MAP
assert "planning_blocksworld_dev_smoke" in DATASET_NAMED_MIXTURES
assert "planning_blocksworld" in ROBOT_TYPE_CONFIG_MAP
print("planning dataset registry smoke passed")
PY
```
# State-frame and partial-goal parity (#69)

`modality_observation.render_replayed_plan(request)` uses the localhost supplied-plan
Render Production boundary from #68. It first progresses every supplied action through
the PDDL authority, then checks the interpreted VFG action order and binds stage zero
to the initial state and each later stage to its progressed state. Within that supplied
Action Sequence, a repeated state always uses its first frame. A state absent from the
replayed sequence is an explicit error: supply a path covering that search state rather
than substituting a solution-path frame. The supplied path need not reach a goal.
For branching search, `render_replayed_paths(request, supplied_paths)` assembles one
catalog from multiple supplied paths. Paths are sorted by length and normalized action
order, and the first occurrence determines the binding independently of caller order.
Each path has its own output subdirectory. No path is found or planned by this API.

`build_matched_best_first_observations` takes those frames, the active best-first
controller, explicit `ModalityInputLimits`, a processor token counter, and a task-local
output directory. It returns text-state, visual-state, and multimodal-state observations
for the **current decision**, without choosing or applying an operation. Both active
settings (`best_first_add_w3`, `best_first_add_greedy`) use this boundary.

All three are projections of `best_first_semantic_input`: current dynamic facts and
fluents, static facts, initial facts and fluents, declared object types, and the partial
goal. The identical textual Search Memory includes the complete remaining candidate
table (including exact closed/frontier/dominated membership), scalar search values, and
the same accepted-delta window. Counts never replace candidate membership.

Visual-state contains two PNGs: the bound Planimation scene plus labelled relation
panels, and a separate partial-goal constraint panel. Predicate and ordered argument
boxes expose facts which domain animation profiles may omit. Goal rows are conjunctive
requirements; **unlisted goal facts are unconstrained**, not false and not copied from
a completed state. This release supports the positive conjunctive STRIPS goals used by
the additive best-first arms; other goal formulas fail explicitly. Multimodal-state
receives the same images and the relational text. `observation.messages()` exposes
only the prompt and images, excluding the replay/drawing metadata.

The relation panels, rather than arbitrary animation-profile geometry, define the
complete visual semantics. This is a labelled relational visual condition; it does not
certify that an unannotated Planimation scene alone conveys every task fact. Semantic
parity compares the text and the actual relation drawing commands to the current PDDL
and controller snapshot. It does not perform OCR, pixel comparison, artifact integrity,
or certify arbitrary profile geometry. Retain the drawing commands for replay.

`validate_modality_parity(observations, controller=...)` can also validate retained
observations at each position while replaying the recorded operations through a fresh
controller. An omitted fact, changed goal constraint, missing candidate membership, or
different memory capacity is a corpus defect and raises `ModalityParityError`.

Before using the adapter, freeze its tokenizer identity/revision, total input-token
limit, image dimensions, font, Search Memory byte capacity, accepted-delta capacity,
and increasing input-size bins (ending at the token limit). The supplied counter must
use that processor and include **image tokens**. Each input reports its measured token
count and bin. The adapter rejects oversized text, memory, or image panels without
truncating facts or shrinking labels. It creates two images per visual observation;
their dimensions and font are identical in both visual modalities. Use a separate
output directory for each task and frozen rendering contract.

This is supporting infrastructure. #70 owns the authorized matched episode and its
aligned evidence; production processor limits and representative size-bin coverage
must be fixed before throughput qualification. The unit tests use a small explicit
test capacity and simulated HTTP responses, not a production qualification or model
result. No long experiment is needed to run the supporting tests:

```bash
source ~/cd_vlaplan
python -m pytest -q tests/planning_benchmark/test_modality_parity.py
```
