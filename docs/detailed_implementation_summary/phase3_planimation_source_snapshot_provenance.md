# Phase 3 Planimation Source Snapshot Provenance

## Changes

- Frozen pairing rows now point to root-relative JSONL records rather than standalone trace copies.
- Each row records root ID, root snapshot digest, JSONL relative path, split digest, physical line index, raw-record digest, example ID, and active planner ID.
- Reload validates the full root snapshot once per source root in an operation, validates the selected split from that snapshot, then reopens and hashes the selected JSONL row.
- Unsupported planners, including `bfs`, fail with `unsupported_active_planner`; changed source state fails with `source_snapshot_mismatch`.

## Verification

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_planimation_pairing.py -q
```

Expected result: `7 passed`.

```bash
source ~/cd_vlaplan && source .venv/bin/activate && output_root="tmp/phase3_task1_manifest_$(date +%Y%m%d_%H%M%S)" && python scripts/phase3/generate_planimation_vlm.py --dataset-root outputs/phase3_curriculum_traces_15puzzle_easy_20260709_002417 --output-root "$output_root" --domain 15puzzle --bucket easy --manifest-only && python scripts/phase3/verify_planimation_vlm.py --output-root "$output_root"
```

Observed result: a 688-row manifest verified with `errors: []` at `tmp/phase3_task1_manifest_20260715_191332`.

## Review-Blocker Follow-Up

- Source reload now verifies manifest planner, active planner ID, split, domain, instance ID, and plan hash against the row selected by its physical line index.
- Each operation indexes a source JSONL once, retaining original raw bytes for the source-record SHA-256 check. Root snapshots remain cached once per root.
- The preserved 688-row verifier completed in `7.37` seconds under the command below.

```bash
source ~/cd_vlaplan && source .venv/bin/activate && /usr/bin/time -f 'ELAPSED_SECONDS=%e EXIT_STATUS=%x' timeout 300s python scripts/phase3/verify_planimation_vlm.py --output-root tmp/phase3_task1_manifest_20260715_191332
```

Observed result: `errors: []`, `ELAPSED_SECONDS=7.37`, `EXIT_STATUS=0`.
