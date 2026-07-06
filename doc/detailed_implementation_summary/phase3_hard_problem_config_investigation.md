# Phase 3 Hard Problem Config Investigation

Date: 2026-07-06

## Scope

Investigated whether the current Phase 3 trace-generation config is adequate for hard planning problems by selecting one accepted measured-hard instance from each curriculum domain and probing the current local trace defaults.

The selected subset is stored in `tmp/phase3_hard_one_per_domain_input/accepted_manifest.jsonl`. It contains 15 rows, one for each domain, all with `bucket == "hard"` and `difficulty_measured == "hard"`.

## Selected Instances

- `15puzzle-dev-hard-0000`
- `blocksworld-dev-hard-0000`
- `depot-dev-hard-0000`
- `driverlog-dev-hard-0000`
- `elevators-dev-hard-0000`
- `ferry-dev-hard-0000`
- `freecell-dev-hard-0000`
- `grid-dev-hard-0000`
- `gripper-dev-hard-0000`
- `logistics-dev-hard-0000`
- `snake-dev-hard-0000`
- `sokoban-dev-hard-0000`
- `storage-dev-hard-0000`
- `towers_of_hanoi-dev-hard-0000`
- `visitall-dev-hard-0000`

## Commands

Create the filtered one-hard-per-domain input root:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python - <<'PY'
from __future__ import annotations
import json
import shutil
from collections import defaultdict
from pathlib import Path

source = Path('data/curriculum_pddl/accepted_manifest.jsonl')
input_root = Path('tmp/phase3_hard_one_per_domain_input')
if input_root.exists():
    shutil.rmtree(input_root)
input_root.mkdir(parents=True)
rows = [json.loads(line) for line in source.read_text(encoding='utf-8').splitlines() if line]
by_domain = defaultdict(list)
for row in rows:
    by_domain[str(row.get('domain_id'))].append(row)
selected = []
for domain in sorted(by_domain):
    hard = [row for row in by_domain[domain] if str(row.get('difficulty_measured')) == 'hard']
    candidates = hard or by_domain[domain]
    candidates.sort(key=lambda row: str(row.get('instance_id')))
    selected.append(candidates[0])
(input_root / 'accepted_manifest.jsonl').write_text(''.join(json.dumps(row, sort_keys=True) + '\n' for row in selected), encoding='utf-8')
(input_root / 'summary.json').write_text(json.dumps({'accepted_total': len(selected)}, sort_keys=True) + '\n', encoding='utf-8')
PY
```

Run the raw current-default helper as one batch:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/generate_curriculum_trace_dataset.py --input-root tmp/phase3_hard_one_per_domain_input --output-root tmp/phase3_hard_one_per_domain_current_defaults --quiet
```

That run timed out after 600 seconds in the original investigation. A preserved shorter proof was captured with:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && timeout 120s python scripts/phase3/generate_curriculum_trace_dataset.py --input-root tmp/phase3_hard_one_per_domain_input --output-root tmp/phase3_hard_one_per_domain_current_defaults_preserved_timeout/output --quiet
```

The preserved timeout metadata is `tmp/phase3_hard_one_per_domain_current_defaults_preserved_timeout/run_metadata.txt`, with exit status `124` after 120 seconds.

## Current-Default Probe Result

Per-domain/per-planner probes used the same helper in isolated subprocesses with a 45 second wrapper timeout. The exact command shape was:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && timeout 45s python scripts/phase3/generate_curriculum_trace_dataset.py --input-root tmp/phase3_hard_one_per_domain_input --instance-id <INSTANCE_ID> --planner <bfs|ff|iw|graphplan> --output-root tmp/phase3_hard_one_per_domain_probe_current/<DOMAIN>/<PLANNER> --quiet
```

Artifacts:

- `tmp/phase3_hard_one_per_domain_probe_current/probe_summary.json`
- `tmp/phase3_hard_one_per_domain_probe_current/*/*/diagnostics/planner_attempts.jsonl`

Observed normalized statuses across 60 attempts:

- `success_full_trace`: 2
- `timeout`: 19
- `skipped_grounding_limit`: 15
- `skipped_resource_limit`: 16
- `skipped_unsupported_pddl`: 8

Only Graphplan succeeded, and only for `elevators-dev-hard-0000` and `towers_of_hanoi-dev-hard-0000`.

## Recommended Config

The current raw defaults are not adequate as a broad hard-problem trace-completion config. The recommended config depends on the goal.

For a hard survey or safe batch, use a bounded diagnostic profile rather than trying to force complete traces:

```text
profile_name: hard_safe_batch_supported_cli
planners: bfs, ff, iw, graphplan
grounding_caps: pipeline defaults, max_grounded_actions=100000 and max_grounded_atoms=100000
bfs_pre_gate: enabled by pipeline defaults
local_max_applicable_actions: 2000
local_iw_width: 3
local_iw_max_width: 3
local_graphplan_max_expansions: 100000
planner_attempt_timeout_s: 12 as an external subprocess timeout
expected_semantics: batch terminates; full traces optional; skips/timeouts are diagnostics
```

Supported CLI command shape:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && timeout 12s python scripts/phase3/generate_curriculum_trace_dataset.py --input-root tmp/phase3_hard_one_per_domain_input --instance-id <INSTANCE_ID> --planner <bfs|ff|iw|graphplan> --output-root tmp/phase3_hard_one_per_domain_hard_safe_validate_supported/attempt_outputs/<DOMAIN>/<PLANNER> --local-max-applicable-actions 2000 --local-iw-width 3 --local-iw-max-width 3 --local-graphplan-max-expansions 100000 --quiet
```

Validation artifacts:

- `tmp/phase3_hard_one_per_domain_hard_safe_validate_supported/hard_safe_profile.json`
- `tmp/phase3_hard_one_per_domain_hard_safe_validate_supported/commands.jsonl`
- `tmp/phase3_hard_one_per_domain_hard_safe_validate_supported/probe_summary.json`
- `tmp/phase3_hard_one_per_domain_hard_safe_validate_supported/aggregate_summary.json`

The validated hard-safe profile completed the bounded 60-attempt survey without a batch hang. Aggregate statuses were:

- `success_full_trace`: 2
- `timeout`: 20
- `skipped_grounding_limit`: 15
- `skipped_resource_limit`: 15
- `skipped_unsupported_pddl`: 8

For hard full-trace research, a pure local-config change is not enough. The current hard blockers include unsupported PDDL in `snake` and `sokoban`, grounding explosions in `depot`, `freecell`, `grid`, `logistics`, and `storage`, and search/runtime explosion in several other hard domains. Use external planners or a lifted/symbolic backend, add parser support for unsupported PDDL, add helper-level per-attempt timeouts, and compress/retrieve traces through the external-memory design before using hard raw traces for LLM training.

## Conclusion

Current defaults are adequate for medium-style local trace recovery but not for broad hard-problem completion. For hard problems, use the bounded `hard_safe_batch_supported_cli` profile for diagnostic sweeps and treat full trace completion as a separate research profile requiring external/lifted planning support rather than larger global local caps.
