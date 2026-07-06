# Planning docs closeout checker, Task 11, 2026-06-24

`examples.planning_benchmark_slice.docs_check` is the narrow Phase 1-3 closeout verifier. It checks that required closeout docs exist, required `.sisyphus/evidence/phase1-3-*` paths exist, required caveat/status phrases are present, and no Phase 4 training/model completion is claimed.

Primary commands:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.docs_check --phase 1 2 3 --json > .sisyphus/evidence/phase1-3-task-11-docs-check.json
source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.docs_check --no-phase4-claims --json > .sisyphus/evidence/phase1-3-task-11-no-overclaim.json
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/planning_benchmark/test_docs_check.py -q
```

The execution plan status is intentionally limited to Blocksworld-only P0 for Phases 1-3. Phase 4 remains not complete.
