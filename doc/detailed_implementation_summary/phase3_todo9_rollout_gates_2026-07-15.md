# Phase 3 Todo 9 Staged Rollout Gates

Todo 9 adds `scripts/phase3/rollout_gates.py`. It deterministically freezes eligible pair IDs plus source root/split/line/record provenance before rendering, and writes a promotion receipt only after release-mode verification and stage coverage pass. The generator accepts `--selection-file` to re-materialize only frozen pair IDs; arbitrary bounded smoke output cannot be promoted.

Stages are ordered `fixture`, `changed-canary`, `stratified-pilot`, `complete-domain`, and `frozen-full`. Changed canaries require 5-10 transitions per domain, pilots require 250-500 transitions with every selected nonempty domain/planner/split cell, and a prior approved receipt is required when one is supplied. A bad selection, failed release verification, incomplete receipt, provenance failure, coverage failure, or semantic-image failure yields a nonzero `assess` command and blocks advancement.

## Executed Evidence

The fresh strict fixture passed the real release verifier: one pair, two rendered states, one train full record, and one train step record. Its promotion receipt is approved and retained with semantic-image metrics at `tmp/phase3_release_fixture_task9_fixture_cli_20260715/diagnostics/state_render_manifest.jsonl`.

The bounded active-root probe on `outputs/phase3_curriculum_traces_15puzzle_easy_20260709_002417` found 688 pairs but zero strict-v1 eligible pairs because every row lacks `trace_contract_version`. The changed-canary selection and promotion receipt are controlled failures; no renderer, source root, cache, or `outputs/` corpus was changed. A contact sheet is not claimed because no source-root canary image was safely rendered.

Full details and exact observed counts are in `.omo/evidence/phase3-task-9-rollout-gates-2026-07-15.json`.

## Verification Commands

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_verify_planimation_vlm.py tests/phase3/test_planimation_pairing.py tests/phase3/test_render_semantics.py -q
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright scripts/phase3/rollout_gates.py scripts/phase3/generate_planimation_vlm.py scripts/phase3/planimation_pairing.py tests/phase3/test_verify_planimation_vlm.py
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/verify_planimation_vlm.py --output-root tmp/phase3_release_fixture_task9_fixture_cli_20260715 --mode release
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/rollout_gates.py assess --output-root tmp/phase3_release_fixture_task9_fixture_cli_20260715 --stage fixture --selection-file tmp/phase3_release_fixture_task9_fixture_cli_20260715/diagnostics/rollout_selection.json
```
