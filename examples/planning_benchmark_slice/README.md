# planning_benchmark_slice

Minimal example for reading one accepted instance from the merged curriculum PDDL dataset.

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
source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.generate_experts --fixture tests/fixtures/planning/blocksworld_nontrivial.json --algorithms bfs fast_forward iterated_width graphplan --output outputs/planning_artifacts/expert_smoke --json
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
