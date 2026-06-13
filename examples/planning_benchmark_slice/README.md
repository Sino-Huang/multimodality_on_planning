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
