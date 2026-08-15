# Phase 3 CGAS Alignment

## Scope

Todo 3 adds `scripts.phase3.cgas_alignment`, a fail-closed CLI that maps only
provenance-verified CGAS P0 source transitions to Planimation replay renders.
It emits one `vision_available_step_aligned` record per accepted transition in
`<output-root>/alignment/{train,dev,test}.jsonl`.

Each record carries the source transition ID, replay `state_before` hash,
action, PNG path/hash, VFG action index, source/render trace digests, and a
mapping rationale. The verifier requires a readable t=0 initial frame, a
matching persisted PNG/VFG digest, a decodable semantic render, a derived-PDDL
initial state equal to replay `state_before`, and VFG actions matching the
replay action prefix through the selected action.

## Commands

```bash
source ~/cd_vlaplan && python -m pytest -q tests/phase3/test_cgas_alignment.py tests/phase3/test_planimation_pairing.py tests/phase3/test_verify_planimation_vlm.py
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_alignment.py tests/phase3/test_cgas_alignment.py
source ~/cd_vlaplan && python -m scripts.phase3.cgas_alignment --help
source ~/cd_vlaplan && python -m scripts.phase3.cgas_alignment --source-root .omo/evidence/task-3-cgas-dataloader-and-experiment-support/fixture-build/test_alignment_cli_emits_one_r0/planning_cgas_v1 --render-manifest .omo/evidence/task-3-cgas-dataloader-and-experiment-support/fixture-build/test_alignment_cli_emits_one_r0/renders/state_render_manifest.jsonl --output-root .omo/evidence/task-3-cgas-dataloader-and-experiment-support/manual-output
source ~/cd_vlaplan && python -m scripts.phase3.cgas_alignment --verify --source-root .omo/evidence/task-3-cgas-dataloader-and-experiment-support/fixture-build/test_alignment_cli_emits_one_r0/planning_cgas_v1 --render-manifest .omo/evidence/task-3-cgas-dataloader-and-experiment-support/fixture-build/test_alignment_cli_emits_one_r0/renders/state_render_manifest.jsonl --output-root .omo/evidence/task-3-cgas-dataloader-and-experiment-support/manual-output
```

## Results

- RED was captured before implementation: the new CLI module did not exist.
- GREEN: 84 focused tests passed in 29.19s and basedpyright reported zero errors and warnings.
- Direct CLI build and `--verify` each accepted 12 bounded-fixture rows with all five failure counters at zero.
- Adversarial tests reject swapped frames, mutated VFG actions, missing t=0 frames, unreadable PNGs, and stale state hashes.

Evidence is retained in `.omo/evidence/task-3-cgas-dataloader-and-experiment-support/`.
