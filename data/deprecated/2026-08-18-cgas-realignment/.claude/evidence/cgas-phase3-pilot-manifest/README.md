# CGAS Phase 3 pilot-manifest evidence

This packet freezes the approved Phase 3 pilot source-instance boundary over the real signed v3
checkpoint. It does not materialize certificate rows, render images, build a Qwen corpus, load model
weights, train, or publish a release.

## Owner approval and bound inputs

The canonical owner ruling is `pilot-owner-approval.json`, SHA-256
`7b4dedb1b59a2ec338c64a3f671156581a66db027ecf03569a2f6271fd8fed85`. It approves and binds:

- scope report `ed09d0ba44e74b1e74eadfdf74f0daf4ff1e448a504b1033e09103821b6d82bd`;
- v3 checkpoint `0fa9d3e5bcad06e6e50381a2142d4b6777818feffb0e1a4012c010a1fdebf76b`;
- v3 current index `e86d42a7ec94c29169cadb4eb65baa93e5b4502eda65bc9bbb333b5c9a2bce97`;
- signed trace-v3 approval `bf00880f94692160d42103aab689ea2501607b48df53114b282bdc404b34dbe7`;
- trace contract `be1a3eb9f42d387e57a7e714ce95154f2657833114a68d41e5b88342ef1234d1`;
- trace policy `51acff53d15652663d2212902d3d94261e44de9e3edf66b9970fc3c75197d436`;
- pilot-provenance decision `7fdd048cb751f2ed59be69bd1fecc3167a25377b1522ca3eaa47e94d8a6e2c36`;
- immutable release digest `3bc894314f4fa674ff36489c664d8cc9db7f23e2144c5ffcef1444fd30feb6c3`.

The approved decisions are `stability_bar=10`, `harvest=off_plan`, the measured 90-instance
diversity floor, and reproducibility-only pilot provenance under all four conditions in
`DECISION-pilot-provenance.md`.

## Frozen artifacts

- `pilot-source-manifest.json`: SHA-256
  `14e6ff873b0c86f2fcbbe9e342ef387880ae3815f30ca73c32767718915137f9`;
- `pilot-row-budget.json`: SHA-256
  `504e49aeb47c097b979a9e56a8d5a94fd4be8cde303657e346742751b8eb34f1`;
- `pilot-manifest-report.json`: SHA-256
  `ce09cda6166b4dd3c96fa7e0933d896684df512fc39eb2379201db6c761f4c74`.

The selector takes the first 30 paired-exact rows per object count under canonical
`(raw_rank, candidate_id)` ordering. The result is exactly 90 unique source instances, 30 each at
4/8/12 objects. A deterministic whole-composition subset assigns exactly 5 held-out-calibration
instances per count and leaves 25 train instances per count, for 75 train / 15 held out overall.
No composition signature appears in both roles.

| objects | instances | repeated signatures | stack profiles | goal-edge levels | train | held out |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 4 | 30 | 7 | 5 | 3 | 25 | 5 |
| 8 | 30 | 8 | 10 | 6 | 25 | 5 |
| 12 | 30 | 6 | 8 | 7 | 25 | 5 |

The row-budget contract exposes 790 on-plan rows, 31,171 total off-plan expansion rows, and 30,381
off-plan-only rows. Its 7 certificate families by 3 object counts form 21 cells and require at
least 210 first-failure observations before exhaustion.

## Reproduction

```bash
cd /data/scratch/projects/punim0478/sukaih/multimodality_on_planning
source ~/cd_vlaplan
python -m scripts.phase3.cgas_pilot_manifest \
  --repository . \
  --checkpoint tmp/cgas-p0-characterized-v3/checkpoints/reservoir_checkpoint_000001.json \
  --checkpoint-index tmp/cgas-p0-characterized-v3/current.json \
  --scope-report .claude/evidence/cgas-phase3-pilot-scope/report.json \
  --approval .claude/evidence/cgas-phase3-pilot-manifest/pilot-owner-approval.json \
  --output .claude/evidence/cgas-phase3-pilot-manifest
```

The command exhaustively verifies all 562 checkpoint-bound v3 streams. First publication recorded
`read_only=false`; an exact replay recorded `read_only=true` and preserved the three artifact bytes.

## Verification

RED was `6` unimplemented-boundary failures plus `1` approval-implementation provenance mutation
failure. The final focused seam suite is `55 passed, 1 deselected`; the real-checkpoint integration
is covered by both the broad suite and manual QA. Broad CGAS is `476 passed, 3 failed`; the three
failures are the unchanged planner-probe baseline listed in `gates.json`. Ruff, basedpyright, the
no-excuse audit, and the trace-contract surface audit pass.

The v2 characterization-root metadata digest remains
`3e1d918ad6f17bd86c6bd119afe111e1672118f2f23e7a1cb76d1bf27b63536f`; the v3 digest remains
`a4e86491848c7064e6d250fada7d02e8c0d639bcfca0223594a56c60c68274be`. Checkpoint 2 is absent in
both roots.
