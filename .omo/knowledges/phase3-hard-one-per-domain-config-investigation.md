# Phase 3 Hard One-Per-Domain Config Investigation

Date: 2026-07-05

## Scope

Selected one accepted `hard` instance per curriculum domain from `data/curriculum_pddl/accepted_manifest.jsonl` and probed the current Phase 3 local trace defaults.

Selected instances:

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

Create the filtered input root:

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
    hard = [row for row in by_domain[domain] if str(row.get('bucket')) == 'hard']
    candidates = hard or by_domain[domain]
    candidates.sort(key=lambda row: str(row.get('instance_id')))
    selected.append(candidates[0])
(input_root / 'accepted_manifest.jsonl').write_text(''.join(json.dumps(row, sort_keys=True) + '\n' for row in selected), encoding='utf-8')
(input_root / 'summary.json').write_text(json.dumps({'accepted_total': len(selected)}, sort_keys=True) + '\n', encoding='utf-8')
PY
```

The combined current-default run:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/generate_curriculum_trace_dataset.py --input-root tmp/phase3_hard_one_per_domain_input --output-root tmp/phase3_hard_one_per_domain_current_defaults --quiet
```

Result: timed out after 600 seconds before `planner_attempts.jsonl` was written.

Preserved shorter timeout evidence was also captured for auditability:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && timeout 120s python scripts/phase3/generate_curriculum_trace_dataset.py --input-root tmp/phase3_hard_one_per_domain_input --output-root tmp/phase3_hard_one_per_domain_current_defaults_preserved_timeout/output --quiet
```

Evidence files:

- `tmp/phase3_hard_one_per_domain_current_defaults_preserved_timeout/run_metadata.txt`: exit status `124`, started `2026-07-06T00:38:11+10:00`, ended `2026-07-06T00:40:11+10:00`.
- `tmp/phase3_hard_one_per_domain_current_defaults_preserved_timeout/stdout.log`: empty.
- `tmp/phase3_hard_one_per_domain_current_defaults_preserved_timeout/stderr.log`: empty.

This proves the unbounded helper-level current-default batch did not finish within a 120 second wall-clock timeout on the same 15-domain hard subset.

Per-domain/per-planner probes used a 45 second subprocess timeout and wrote results under `tmp/phase3_hard_one_per_domain_probe_current`.

The exact per-probe command shape was:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && timeout 45s python scripts/phase3/generate_curriculum_trace_dataset.py --input-root tmp/phase3_hard_one_per_domain_input --instance-id <INSTANCE_ID> --planner <gbfs|ff|iw|graphplan> --output-root tmp/phase3_hard_one_per_domain_probe_current/<DOMAIN>/<PLANNER> --quiet
```

The machine-readable per-attempt summary is `tmp/phase3_hard_one_per_domain_probe_current/probe_summary.json`.

## Current Default Adequacy

Current defaults are not adequate as a broad hard-problem configuration. Out of 60 probes (15 domains x 4 planners), only 2 succeeded:

- `elevators-dev-hard-0000` with Graphplan.
- `towers_of_hanoi-dev-hard-0000` with Graphplan.

Observed status counts:

- `success_full_trace`: 2
- `timeout`: 19
- `skipped_grounding_limit`: 15
- `skipped_resource_limit`: 16
- `skipped_unsupported_pddl`: 8

By planner:

- GBFS: 13 `skipped_resource_limit`, 2 `skipped_unsupported_pddl`.
- FF: 8 timeouts, 5 `skipped_grounding_limit`, 2 `skipped_unsupported_pddl`.
- IW: 8 timeouts, 5 `skipped_grounding_limit`, 2 `skipped_unsupported_pddl`.
- Graphplan: 2 success, 3 timeouts, 3 `skipped_resource_limit`, 5 `skipped_grounding_limit`, 2 `skipped_unsupported_pddl`.

## Main Failure Classes

1. Unsupported PDDL: `snake` needs negative preconditions; `sokoban` needs equality and quantifiers. No numeric config fixes these for the current local parser.
2. Naive grounding explosion: `depot`, `freecell`, `grid`, `logistics`, and `storage` exceed the default `max_grounded_actions=100000` for FF/IW/Graphplan local planners. Static schema estimates are roughly 5.4M (`depot`), 881B (`freecell`), 4.6M (`grid`), 1.5M (`logistics`), and 205M (`storage`), so simply raising the local grounder cap is not a practical general hard-problem solution.
3. Search/runtime explosion: `15puzzle`, `blocksworld`, `driverlog`, `elevators`, `ferry`, `gripper`, `towers_of_hanoi`, and `visitall` frequently timed out for FF/IW/Graphplan or hit GBFS resource gates.
4. GBFS pre-gate: every selected hard instance tripped the current GBFS pre-gate (`object_count > 8`, `goal_count > 8`, or estimated applicable actions > 2000). This is deliberate protection against raw local search trace explosion.

## Recommended Hard Config

Do not use a single raised local default profile for all hard problems. It either still fails unsupported/grounding-explosion domains or risks huge traces and long runtimes.

Recommended profiles:

1. Hard survey / safe batch profile:
   - Name: `hard_safe_batch_supported_cli`.
   - Planners: `gbfs`, `ff`, `iw`, `graphplan`.
   - Grounding caps: pipeline defaults, `max_grounded_actions=100000`, `max_grounded_atoms=100000`.
   - GBFS pre-gate: keep enabled by pipeline defaults.
   - Local applicable-action gate: `--local-max-applicable-actions 2000`.
   - IW: `--local-iw-width 3 --local-iw-max-width 3`.
   - Graphplan expansion cap: `--local-graphplan-max-expansions 100000` for the hard-safe survey profile; pipeline default is `250000`.
   - Planner-attempt timeout: external subprocess timeout, validated at 12 seconds per instance/planner attempt for the survey profile.
   - Expected semantics: the batch should complete without hanging; full traces are optional; `timeout`, `skipped_resource_limit`, `skipped_grounding_limit`, and `skipped_unsupported_pddl` are valid hard-domain diagnostics.

   Supported CLI command shape:

   ```bash
   source ~/cd_vlaplan && source .venv/bin/activate && timeout 12s python scripts/phase3/generate_curriculum_trace_dataset.py --input-root tmp/phase3_hard_one_per_domain_input --instance-id <INSTANCE_ID> --planner <gbfs|ff|iw|graphplan> --output-root tmp/phase3_hard_one_per_domain_hard_safe_validate_supported/attempt_outputs/<DOMAIN>/<PLANNER> --local-max-applicable-actions 2000 --local-iw-width 3 --local-iw-max-width 3 --local-graphplan-max-expansions 100000 --quiet
   ```

   Validation artifacts:

   - `tmp/phase3_hard_one_per_domain_hard_safe_validate_supported/hard_safe_profile.json` records the concrete profile.
   - `tmp/phase3_hard_one_per_domain_hard_safe_validate_supported/commands.jsonl` records all 60 exact subprocess commands.
   - `tmp/phase3_hard_one_per_domain_hard_safe_validate_supported/probe_summary.json` records per-attempt outcomes.
   - `tmp/phase3_hard_one_per_domain_hard_safe_validate_supported/aggregate_summary.json` records aggregate results.

   Validation result on the same 15-domain hard subset: all 60 bounded attempts finished or timed out under the wrapper, so the batch did not hang. Aggregate statuses were `success_full_trace=2`, `timeout=20`, `skipped_grounding_limit=15`, `skipped_resource_limit=15`, and `skipped_unsupported_pddl=8`. The two full traces were Graphplan for `elevators-dev-hard-0000` and Graphplan for `towers_of_hanoi-dev-hard-0000`.

2. Hard trace-completion profile for local Python traces:
   - Not recommended as a global profile.
   - For domains with small grounded counts, tune per-domain and per-planner caps only after a focused probe.
   - Never raise grounding caps into the multi-million/billion range for `freecell`, `storage`, `depot`, `grid`, or `logistics` with the current naive grounder.

3. Hard full-trace research profile:
   - Use external planners or a lifted/symbolic planner backend for hard domains.
   - Extend parser support before expecting `snake` or `sokoban` local traces.
   - Keep native helper timeouts enabled before running hard batches unattended: default `--planner-attempt-timeout-seconds 1200` and `--domain-timeout-seconds 3600`.
   - Add trace compression/external-memory summaries before feeding raw hard traces to LLMs.
   - This profile is not currently implementable as a pure local-config change with the existing helper. It requires either external planner integration already available through `--use-external-planners` where planner binaries are installed, or a new lifted/symbolic backend for domains where the current naive grounder is the blocker.
