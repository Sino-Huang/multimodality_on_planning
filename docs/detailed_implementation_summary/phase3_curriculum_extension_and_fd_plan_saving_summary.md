# Phase 3 curriculum extension and Fast Downward plan-saving summary

Date: 2026-06-28

## Scope

This work extended the existing curriculum PDDL data-collection tooling rather than replacing it. The accepted-instance contract still comes from `src.data_collect generate`, shard assembly still comes from `src.data_collect merge-shards`, and duplicate prevention still uses normalized PDDL hashes through `AcceptedProblemHashIndex`.

The initial requested target was approximately 8,000 accepted instances, represented by the historical `7995 = 533 * 15` per-domain target. Later workflow runs safely extended the visible root in place to 5,153 accepted instances with zero duplicate normalized problem hashes. Based on the observed generator yield, `7995` is no longer the recommended default target for the current generator/configuration mix: several domains appear low-yield or effectively exhausted under the existing settings, so repeated runs add rows slowly and unevenly.

## Code changes

- Added `scripts/phase3/save_fast_downward_plans.py`.
  - Reads `accepted_manifest.jsonl` from a curriculum root.
  - Saves per-instance Fast Downward plans under `<instance>/plan/sas_plan` using `--plan-file`.
  - Writes diagnostics to `diagnostics/fast_downward_plan_saves.jsonl`.
  - Writes summary metadata to `reports/fast_downward_plan_saves_summary.json`.
  - Skips existing plan files unless `--force` is supplied.
  - Requires manifest domain/problem paths and plan output directories to resolve under the selected input root.
  - Rejects symlinked `plan/` directories.
  - Captures planner launch failures as per-row diagnostics.
- Added `tests/phase3/test_save_fast_downward_plans.py`.
- Updated `src/data_collect/cli.py`.
  - Added `--candidate-multiplier` to the `generate` CLI.
  - Included the resolved multiplier in dry-run JSON.
  - Passed the multiplier through to `orchestrate_generation(...)`.
  - Rejects non-positive candidate multipliers before dry-run or generation.
- Updated `src/data_collect/generate.py`.
  - Candidate pool sizing during generation now uses `remaining_quotas` instead of absolute target quotas.
  - This preserves first-run behavior and avoids excessive pool generation during resumed extension runs.
- Updated data-collection tests for the new CLI flag and resumed-extension behavior.
- Added `scripts/phase3/extend_curriculum_workflow.py`.
  - Resumably extends `data/curriculum_pddl_shards/<domain>` only.
  - Verifies shard duplicate/missing hashes after bounded generation commands.
  - Staged-merges to a candidate root under `/tmp/opencode` by default.
  - Optionally runs Fast Downward plan saving. When `--update-root` is supplied, plans are saved after the final-root update so they appear under `data/curriculum_pddl`; otherwise they are saved under the staged candidate root.
  - Supports `--update-root` to update `data/curriculum_pddl` from the fully merged shards after a successful hidden safety merge.
  - Supports `--verbose` live progress logs to stderr while preserving JSON output on stdout.

## Current data checkpoint

Read-only accounting at the latest checkpoint:

- `data/curriculum_pddl`: 5,153 accepted rows, zero duplicate accepted problem hashes.
- `data/curriculum_pddl_shards`: merged into the final root through `scripts.phase3.extend_curriculum_workflow --update-root`.
- No missing normalized hashes, missing PDDL paths, or missing render artifacts were found in the latest integrity checks.
- No plan files are present yet in the latest final root; run full Fast Downward plan saving after accepting this checkpoint as final.
- Latest final-root summary:
  - `accepted_total=5153`
  - `accepted_by_split={"train": 4199, "dev": 475, "test": 479}`
  - `accepted_by_bucket={"easy": 1860, "medium": 1961, "hard": 1332}`
  - `duplicate_accepted_problem_hashes=0`

Domain totals at the latest checkpoint:

- `blocksworld`: 481
- `depot`: 451
- `logistics`: 451
- `grid`: 441
- `sokoban`: 421
- `snake`: 397
- `storage`: 389
- `15puzzle`: 378
- `driverlog`, `elevators`, `ferry`, `visitall`: 255 each
- `freecell`: 244
- `gripper`, `towers_of_hanoi`: 240 each

## Verified commands

Focused tests and diagnostics:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/data_collect/test_cli.py tests/data_collect/test_generate_orchestrator.py tests/data_collect/test_merge_shards.py tests/phase3/test_save_fast_downward_plans.py tests/phase3/test_docs_phase3_summary.py
```

Expected signal observed after review fixes: `30 passed`.

Shard duplicate/hash checkpoint:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python - <<'PY'
import json
from collections import Counter
from pathlib import Path
root=Path('data/curriculum_pddl_shards')
total=0
hashes=[]
for shard in sorted(p for p in root.iterdir() if p.is_dir()):
    rows=[json.loads(line) for line in (shard/'accepted_manifest.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    total += len(rows)
    hashes.extend(r.get('normalized_problem_hash') for r in rows)
    c=Counter((r['split'], r['bucket']) for r in rows)
    print(shard.name, len(rows), {b:c[('train',b)] for b in ('easy','medium','hard')})
print({'TOTAL': total, 'duplicate_hashes': len(hashes)-len(set(hashes)), 'missing_hashes': sum(1 for h in hashes if not h)})
PY
```

Expected signal observed at the earlier checkpoint: `{'TOTAL': 4492, 'duplicate_hashes': 0, 'missing_hashes': 0}`. Later workflow runs moved the final root to the 5,153-row checkpoint above.

Staged merge verification:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m src.data_collect merge-shards --shards-root data/curriculum_pddl_shards --output /tmp/opencode/curriculum_pddl_candidate_4492 --force --json
```

Expected signal observed at the earlier checkpoint: `accepted_total=4492`, `duplicate_accepted_problem_hashes=0`. Use the compact verification command below for the latest final-root state.

Latest compact verification command:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python - <<'PY'
import json
from collections import Counter
from pathlib import Path

root = Path('data/curriculum_pddl')
rows = [json.loads(line) for line in (root / 'accepted_manifest.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
hashes = [row.get('normalized_problem_hash') for row in rows]
missing_paths = 0
missing_render = 0
plan_instances = 0
for row in rows:
    for key in ('domain_path', 'problem_path'):
        value = row.get(key)
        if not value or not (root / value).exists():
            missing_paths += 1
    render_dir = row.get('render_dir')
    if render_dir and not (root / render_dir).exists():
        missing_render += 1
    instance_dir = (root / row['problem_path']).parent if row.get('problem_path') else None
    if instance_dir and (instance_dir / 'plan').exists() and any((instance_dir / 'plan').glob('sas_plan*')):
        plan_instances += 1
print(json.dumps({
    'accepted_total': len(rows),
    'duplicate_hashes': len(hashes) - len(set(hashes)),
    'missing_hashes': sum(1 for value in hashes if not value),
    'missing_domain_or_problem_paths': missing_paths,
    'missing_render_artifacts': missing_render,
    'plan_instances': plan_instances,
}, sort_keys=True))
PY
```

Expected signal at the latest checkpoint: `accepted_total=5153`, `duplicate_hashes=0`, `missing_hashes=0`, `missing_domain_or_problem_paths=0`, `missing_render_artifacts=0`.

Fast Downward plan-save smoke on the protected baseline root:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.save_fast_downward_plans --input-root data/curriculum_pddl --limit 1 --timeout-seconds 120 --json
```

Expected signal observed: `plan_available_total=1`, `status_counts={"success_plan_saved": 1}`.

Fast Downward plan-save smoke on the staged candidate root:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.save_fast_downward_plans --input-root /tmp/opencode/curriculum_pddl_candidate_4492 --limit 5 --timeout-seconds 120 --json
```

Expected signal observed: `plan_available_total=5`, `status_counts={"success_plan_saved": 5}`.

## Safe continuation commands

All-in-one resumable workflow command that keeps the visible dataset at `data/curriculum_pddl` updated. Use this only if you intentionally want to keep trying for more rows despite diminishing returns:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.extend_curriculum_workflow \
  --target-total 5600 \
  --candidate-root /tmp/opencode/curriculum_pddl_candidate_auto \
  --final-root data/curriculum_pddl \
  --update-root \
  --max-generate-commands 60 \
  --command-timeout-seconds 180 \
  --attempt-window 120 \
  --max-attempts-per-bucket 1600 \
  --save-plans \
  --plan-limit 5 \
  --verbose \
  --json
```

Rerun the same command until the JSON `after.accepted_total`, `merge_summary.accepted_total`, and `final_summary.accepted_total` approach the target. With `--verbose`, progress is printed to stderr; JSON remains on stdout. The script still uses `/tmp/opencode/curriculum_pddl_candidate_auto` internally as a safety merge, but it also updates `data/curriculum_pddl` when `--update-root` is present. The old `7995` target should be treated as aspirational only unless generator configs, quotas, or domains are changed.

Recommended finalization command for the current 5,153-row checkpoint:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.extend_curriculum_workflow \
  --target-total 5153 \
  --candidate-root /tmp/opencode/curriculum_pddl_candidate_auto \
  --final-root data/curriculum_pddl \
  --update-root \
  --max-generate-commands 0 \
  --save-plans \
  --verbose \
  --json
```

This command performs the safety merge/update path without launching more generation commands, then saves Fast Downward plans for all accepted rows. It intentionally omits `--plan-limit` so every manifest row is attempted.

Important plan-saving behavior:

- `--plan-timeout-seconds` is the supported workflow timeout flag; `--timeout_seconds` is not accepted by this CLI.
- `--plan-limit` now defaults to all rows when omitted. Use `--plan-limit 5` only for smoke testing.
- Older workflow revisions saved plans into `--candidate-root` before `--update-root`; the final-root update then re-merged from shards, so those candidate-root plans were not visible under `data/curriculum_pddl`. The workflow now saves plans after the final-root update when `--update-root` is present.

Continue generation only against shard roots, not directly against `data/curriculum_pddl`. Use absolute quota targets and bounded attempt windows. Example:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m src.data_collect generate \
  --config src/data_collect/configs/curriculum_15_domains.yaml \
  --output data/curriculum_pddl_shards/depot \
  --domains depot \
  --splits train \
  --quota easy=155 \
  --seed 20260628 \
  --max-attempts-per-bucket 621 \
  --candidate-multiplier 1 \
  --json
```

After enough shard progress, verify by staged merge first:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m src.data_collect merge-shards --shards-root data/curriculum_pddl_shards --output /tmp/opencode/curriculum_pddl_candidate_NEXT --force --json
```

Only replace `data/curriculum_pddl` once the staged root has the intended accepted count, zero duplicate hashes, and successful plan-saving diagnostics.

## Notes

- `7995` was based on a uniform per-domain target and is not a good default for the current observed generator yield.
- `15puzzle` medium and `snake` medium were compute-heavy and caused long foreground timeouts. Prefer high-yield domains/buckets first only if the user explicitly wants more rows.
- `gripper`, `towers_of_hanoi`, `freecell`, `driverlog`, `elevators`, `ferry`, and `visitall` remain far below the old 533-per-domain target and are likely lower priority unless the generator strategy changes.
- A fresh merge from shards does not preserve plan files saved only in `data/curriculum_pddl`, so run `scripts.phase3.save_fast_downward_plans` after the final staged merge.
