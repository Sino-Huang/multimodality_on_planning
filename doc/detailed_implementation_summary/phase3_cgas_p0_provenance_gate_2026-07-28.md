# Phase 3 CGAS P0 Provenance Gate

## Scope

Todo 2 adds a strict Blocksworld-only source gate for canonical FIFO BFS and exact width-1 local IW. It does not use historical GBFS rows as BFS, Planimation image alignment, certificates, or Qwen conversion.

## Commands

```bash
source ~/cd_vlaplan && python -m pytest -q tests/phase3/test_cgas_provenance.py tests/planning_benchmark/test_experts_bfs_iw.py
source ~/cd_vlaplan && python -m scripts.phase3.cgas_provenance --source-manifest <instances.jsonl> --output-root data/planning_cgas_v1
source ~/cd_vlaplan && python -m scripts.phase3.cgas_provenance --verify --output-root data/planning_cgas_v1
source ~/cd_vlaplan && python -m pytest -q tests/phase3/test_cgas_provenance.py tests/phase3/test_cgas_provenance_adversarial.py tests/planning_benchmark/test_experts_bfs_iw.py
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_bfs.py scripts/phase3/cgas_provenance.py scripts/phase3/local_iw.py scripts/phase3/local_planner_types.py tests/phase3/test_cgas_provenance.py tests/phase3/test_cgas_provenance_adversarial.py
git diff --check
```

## Result

The generator snapshots the source manifest and referenced PDDL under the candidate root, then publishes `source/train.jsonl`, `source/dev.jsonl`, `source/test.jsonl`, `manifest.json`, and digest-bound `approved.json` only after every split has replay-valid BFS and IW coverage. BFS records bind a distinct `collections.deque` implementation with sorted legal actions. IW is sourced from the local implementation at exactly width one and rejects `plan_recovery` output.

Verification regenerates rows, provenance digests, trace evidence, stable record IDs, and derived structural-OOD membership from the retained inputs. Any mismatch reports zero accepted rows, requires the approval digest, and withdraws `source/` to `.invalid-source` so invalid JSONL is not trainable. Publication restores the previous output root if the candidate move fails after staging.
