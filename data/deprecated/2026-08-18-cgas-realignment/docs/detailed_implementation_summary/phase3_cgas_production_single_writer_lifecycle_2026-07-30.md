# Phase 3 CGAS Production Single-Writer Lifecycle

## Retained Trusted Artifacts

- Repository: `/data/scratch/projects/punim0478/sukaih/multimodality_on_planning`
- Source manifest: `data/curriculum_pddl/accepted_manifest.jsonl`
- Trusted state root: `tmp/.cgas-characterization/`
- Final bundle: `tmp/.cgas-characterization/planning_cgas_v1-characterization-481.cgas`
- Work root: `tmp/.cgas-characterization/planning_cgas_v1-characterization-481.cgas.work`
- Private candidate root: `tmp/.cgas-characterization/private`
- Bundle name: `planning_cgas_v1-characterization-481.cgas`

The selected final, work, and lock leaves were absent before `fresh`. Existing
`cgas-state-gate-158105.cgas` artifacts were inspected and preserved. The
source manifest has 5,153 accepted records overall; the run contract filters
the authoritative 481 Blocksworld records.

## Contract and Output Attestation

- Contract shard count: `1`
- Contract population: 481 rows, splits `dev=39`, `test=40`, `train=402`,
  object counts `4=190`, `8=198`, `12=93`.
- Final bundle size: `2118813` bytes.
- Final bundle metadata: regular file, mode `0600`, uid `15306`, gid `10504`,
  nlink `1`.
- Logical member `run-contract.json`: 292559 bytes.
- Logical member `characterization.jsonl`: 1824737 bytes.
- Logical member `characterization_manifest.json`: 951 bytes.
- Manifest `owner_approved=false`. No approval marker or promotion was made.

All 481 rows are `characterized`. BFS outcomes are
`exact_search_complete_trace=24`, `exact_search_bounded_trace=174`, and
`search_not_exact=283`. Width-1 native unrecovered IW outcomes are
`exact_search_complete_trace=24`, `exact_search_bounded_trace=42`, and
`search_not_exact=415`. Exact statuses are BFS
`exact_solution_replayed=198` / `not_exact_solution=283` and IW
`exact_solution_replayed=66` / `not_exact_solution=415`.

## Lifecycle Receipts

`fresh` stdout:

```json
{"bundle_name":"planning_cgas_v1-characterization-481.cgas","characterized_count":0,"command":"fresh","status":"ok"}
```

The first blocking `resume` was externally terminated at the 1500-second tool
boundary after durably publishing 442 checkpoints. Its retained state passed
read-only work verification as valid but incomplete. A second `resume` safely
continued from that work root and stdout reported:

```json
{"bundle_name":"planning_cgas_v1-characterization-481.cgas","characterized_count":39,"command":"resume","status":"ok"}
```

Work verify stdout:

```json
{"bundle_name":"planning_cgas_v1-characterization-481.cgas","checkpoint_count":481,"command":"verify","complete":true,"errors":{},"publishable":false,"status":"ok","target":"work","valid":true}
```

Finalize stdout:

```json
{"bundle_name":"planning_cgas_v1-characterization-481.cgas","checkpoint_count":481,"command":"finalize","status":"ok"}
```

Final verify stdout:

```json
{"bundle_name":"planning_cgas_v1-characterization-481.cgas","checkpoint_count":481,"command":"verify","complete":true,"errors":{},"publishable":true,"status":"ok","target":"final","valid":true}
```

The wall-clock interval from fresh completion to final verify completion was
1996.191714368 seconds (33 minutes 16.192 seconds). Timed completed commands:
fresh 3.58 seconds, resumed remainder 116.89 seconds, work verify 2.94
seconds, finalize 109.19 seconds, and final verify 110.17 seconds. The first
resume consumed the 1500-second execution boundary before its restart.

Raw command receipts and independent bundle inspection are retained under
`/tmp/opencode/planning_cgas_v1-characterization-481-*`.

## Reproducible Read-Only Checks

Do not rerun `fresh` or `finalize` for this retained bundle. From the repository
root, these checks read the completed artifacts without changing them:

```bash
source ~/cd_vlaplan && PYTHONDONTWRITEBYTECODE=1 python -m scripts.phase3.cgas_partition_characterization verify --repository-root . --source-manifest data/curriculum_pddl/accepted_manifest.jsonl --bundle-name planning_cgas_v1-characterization-481.cgas --private-root tmp/.cgas-characterization/private --target work
source ~/cd_vlaplan && PYTHONDONTWRITEBYTECODE=1 python -m scripts.phase3.cgas_partition_characterization verify --repository-root . --source-manifest data/curriculum_pddl/accepted_manifest.jsonl --bundle-name planning_cgas_v1-characterization-481.cgas --private-root tmp/.cgas-characterization/private --target final
source ~/cd_vlaplan && # identity check of the final bundle:
tmp/.cgas-characterization/planning_cgas_v1-characterization-481.cgas
```

The final verifier recomputes the authoritative planner rows with canonical FIFO
BFS and native width-1 IW under the unchanged 10,000 expansion limits.
