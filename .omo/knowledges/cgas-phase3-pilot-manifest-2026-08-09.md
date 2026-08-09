# CGAS Phase 3 pilot manifest (2026-08-09)

## Resolved boundary

The owner approved the complete pilot-scope proposal. The approval is canonical at
`.claude/evidence/cgas-phase3-pilot-manifest/pilot-owner-approval.json` and binds the exact scope
report, signed v3 checkpoint/index, trace approval, contract, policy, candidate/selector inputs,
pilot-provenance decision, and immutable release digest.

The frozen source manifest selects exactly 90 paired-exact candidates by taking the canonical
`(raw_rank, candidate_id)` prefix of 30 candidates at each of 4/8/12 objects. Candidate identity,
raw rank, source-record digest, domain digest, BFS/IW trace digests, all upstream bindings, pilot
configuration, and all four pilot implementation digests are recorded in the canonical bytes.

## Composition-isolated roles

The historical held-out policy is 79/481. Applied to 90 instances this rounds to 15, and the
balanced object-count strata make that 5 held-out instances per count. The first 30 candidates at
each count admit an exact whole-composition subset of size 5. Signatures are considered in
`sha256(canonical_signature)` order with deterministic subset-sum discovery; entire signatures are
assigned to held-out calibration, so no signature crosses roles.

Held-out raw ranks are:

- 4 objects: `0, 1, 2, 4, 27`;
- 8 objects: `2, 10, 11, 12, 13`;
- 12 objects: `9, 10, 11, 12, 14`.

The result is 75 train / 15 held-out-calibration, with 25/5 at every object count. Diversity
measurements `(repeated signatures, stack profiles, goal-edge levels)` are `(7,5,3)`, `(8,10,6)`,
and `(6,8,7)` at 4, 8, and 12 objects respectively. Every approved floor is met without relaxing a
scientific choice.

## Row-budget contract

The contract pins `harvest=off_plan`, `stability_bar=10`, 7 certificate families, 3 object-count
levels, 21 cells, and at least 210 first-failure observations. The selected instances expose 790
on-plan rows, 31,171 total off-plan expansion rows, and 30,381 off-plan-only rows. Sampling order is
object count, role, raw rank, candidate ID, then trace order. No failure-rate assumption enters the
contract.

Artifact digests:

- approval: `7b4dedb1b59a2ec338c64a3f671156581a66db027ecf03569a2f6271fd8fed85`;
- manifest: `14e6ff873b0c86f2fcbbe9e342ef387880ae3815f30ca73c32767718915137f9`;
- row budget: `504e49aeb47c097b979a9e56a8d5a94fd4be8cde303657e346742751b8eb34f1`;
- report: `ce09cda6166b4dd3c96fa7e0933d896684df512fc39eb2379201db6c761f4c74`.

## Next dependency

The next implementation must consume the frozen manifest to materialize bounded off-plan source
rows, then audit/render missing images, bind alignment and `verify_steps`, build the Qwen corpus,
and run the strict native-loader preflight. The standalone `planning_vlm/` package is still absent.
No production selector/corpus loop, checkpoint 2, materialization, rendering, model load, training,
or release publication occurred in this milestone.
