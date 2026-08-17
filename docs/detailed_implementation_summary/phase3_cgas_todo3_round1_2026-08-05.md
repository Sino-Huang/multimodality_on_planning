# Phase 3 CGAS Todo 3 Round 1 Implementation Summary

## Scope

Todo 3 now owns the approved trace-v2 candidate characterization lifecycle. The runner validates approval, candidate configuration, selector linkage, predecessor/range/cursor state, and trace-v2 streams before read-only replay or side effects. It publishes immutable predecessor-linked checkpoints and atomically replaces the current index only after the complete accounting and characterization state is validated.

The BFS planner now caches canonical state IDs and maintains sorted visited IDs incrementally. The optimization preserves canonical trace bytes while avoiding repeated state identity computation and whole-set sorting. BFS and IW use bounded-memory trace sinks, and each actual stream is persisted as `bfs.trace-v2.jsonl` or `iw.trace-v2.jsonl` with a trailer and identity chain.

## Exact Commands

```bash
source ~/cd_vlaplan && python -m scripts.phase3.cgas_candidate_characterization next-round --round 1 --approved-trace-contract .omo/evidence/cgas-production-p0/approved-trace-v2.json --candidate-config configs/cgas/production_p0_candidates.json --candidate-root tmp/cgas-p0-candidates --output tmp/cgas-p0-characterized --json
source ~/cd_vlaplan && pytest -q tests/phase3/test_cgas_candidate_characterization.py tests/phase3/test_cgas_candidate_characterization_contracts.py tests/phase3/test_cgas_planner_trace_streaming.py tests/phase3/test_cgas_planner_semantic_parity.py tests/phase3/test_cgas_planner_performance.py tests/phase3/test_cgas_partition_characterization.py tests/phase3/test_cgas_trace_contract_v2.py tests/phase3/test_cgas_production_candidates.py tests/phase3/test_cgas_production_candidates_remediation.py
source ~/cd_vlaplan && ruff check scripts/phase3/cgas_candidate_characterization*.py scripts/phase3/cgas_bfs.py scripts/phase3/local_iw.py scripts/phase3/local_iw_novelty.py scripts/phase3/local_planner_types.py tests/phase3/cgas_candidate_characterization_support.py tests/phase3/test_cgas_candidate_characterization*.py tests/phase3/test_cgas_planner_trace_streaming.py
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_candidate_characterization*.py scripts/phase3/cgas_bfs.py scripts/phase3/local_iw.py scripts/phase3/local_iw_novelty.py scripts/phase3/local_planner_types.py tests/phase3/cgas_candidate_characterization_support.py tests/phase3/test_cgas_candidate_characterization*.py tests/phase3/test_cgas_planner_trace_streaming.py
```

The first command completed with checkpoint `tmp/cgas-p0-characterized/checkpoints/reservoir_checkpoint_000001.json`. The exact immutable rerun returned `{"checkpoint":"tmp/cgas-p0-characterized/checkpoints/reservoir_checkpoint_000001.json","read_only":true,"receipt":null,"status":"ok"}` and is recorded in `.omo/evidence/production-p0-corpus-experiment-readiness/task-3/immutable-rerun.log`.

## Results

- Checkpoint identity: `tmp/cgas-p0-characterized/checkpoints/reservoir_checkpoint_000001.json`.
- Accounting: 481 rows, `emitted=281`, `duplicate=52`, `solved=148`.
- Characterizations: 281 actual candidate rows; paired-exact reservoir: 53 rows and 34 signatures.
- Cursors: `{4:190, 8:198, 12:93}`; all three streams remain non-exhausted.
- Trace storage: 281 immutable candidate directories, approximately 1.1 TB. Complete successful traces remain untruncated.
- A real sample BFS stream is 12,824,621,775 bytes with 10,000 events and a trace-v2 trailer; its paired IW stream is 135,686 bytes with 59 events and a trace-v2 trailer.

## Verification

The focused and adjacent suite passed with 90 tests. Ruff, basedpyright, the 16-file no-excuse/size audit, and LSP diagnostics on all 20 Todo 3 source/test files passed. The alternate unapproved owner template was rejected before side effects with `approved_trace_contract_invalid`. Todo 4 was not invoked because the checkpoint is non-exhausted and no selector feedback exists.
