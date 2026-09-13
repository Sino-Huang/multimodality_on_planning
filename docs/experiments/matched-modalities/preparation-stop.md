# Preparation stopped at the frozen Storage candidate boundary

The corrected CPU candidate run processed **192/192 candidates** and returned
**VALID_STOP**. Every required Storage candidate is ineligible: **56/64** overlap
retained task semantics and **8/64** exhaust the exact BFS allowance of 64
expansions. Independent read-only PDDL/controller verification reproduced all
64 rejections with the actual frozen generator arguments and seeds.

Blocksworld has 26 reference-eligible candidates and Ferry has 36; those still
need layout qualification. Neither domain replaces Storage. The frozen plan
requires all three domains and forbids expanding the candidate seed set or
changing profiles after exhaustion, so this version cannot admit its final
matrix. This is a task/reference resource stop before model evaluation, not
evidence of poor learned performance, a CUDA OOM or exhausted GPU clock.

## Implemented and verified

- `prepare_matched_final_tasks.py`: fixed local generator commands, semantic
  exclusion against 1,042 distinct retained task contexts, bounded full-state
  closure, four trusted exact controllers, ordered candidate/rejection records,
  dry-run, progress/ETA/20-second heartbeats and safe candidate-pool reuse.
- Explicit `task_path` support in the existing task loader/session: new tasks
  remain test tasks without insertion into historical train/dev manifests.
- `run_matched_modalities.py prepare/verify`: selected-record semantic audits,
  exact resource-stop replay, explicit interrupted-preparation resume and refusal
  to overwrite or resume a terminal result. Verify is read-only and returns zero
  for a correctly verified stop; prepare returns two for the resource stop.
- All **2,156 selected records** (2,048 train, 108 diagnostic) and **6,468 modality
  projections** passed the actual frozen CPU processor input counts, full
  text/drawing fact-and-goal parity, common Search Memory/candidate equality,
  selected semantic split isolation, conflicting-input/target checks and
  no-future-image bindings. Trusted goal checking replays source catalog states;
  it does not judge fabricated arbitrary states.
- Six stage dry-run commands expose readiness as false and start no workers.
  Qualify/train/evaluate are **resource-stop guards only**, not implemented GPU
  execution paths. This distinction is visible in CLI help and command output.
- Focused tests: **22 passed**. Existing visual-development/modality-parity
  regression tests: **36 passed**. These do not claim runtime GPU deadline,
  checkpoint-resume or hardware throughput qualification.

Existing #72–#74 scenes, source traces and reusable pages were referenced. No
original scene corpus, old planning trace, training run or scientific result was
regenerated or changed.

## Invalid preliminary preparation retained

The first implementation used the general Storage curriculum command builder,
which ignores supplied preset arguments in favour of its own smaller variant.
Its output is retained at
`outputs/matched_modalities/v1/preparation-invalid-storage-001` and explicitly
marked INVALID. It is not the source of the scientific stop above.

The correction binds the exact fixed arguments (`-c 2`, `-s 4`, and the other
declared options) directly while retaining the existing execution/normalization
adapter. Tests execute all three generators and check their actual commands and
seeds. The corrected second run produced the 56-overlap/eight-reference-failure
Storage outcome; independent verification checks those actual commands again.

## Unfulfilled prerequisites

#91 can close as completed bounded candidate preparation **with an eligibility
stop**, not as a successful final task release. #92 remains open. Missing work is:

1. An eligible Storage problem under a prospective successor task-selection plan.
2. Selection of a complete final panel and all new reachable-state/goal views,
   including processed readability previews and full live-input qualification.
3. The full GPU worker scheduler, cumulative deadline/resume enforcement and
   bounded hardware throughput qualification. Only static cap/port validation
   and no-launch guards are implemented at this resource-stop checkpoint.

The later #112–#115 and #93–#95 tasks have no completed new training/evaluation.
All GPU-stage allocations remain unspent: **0 / 3,600**, **0 / 18,000** and
**0 / 21,600 seconds**. No model inference or disposable GPU training probe ran.
No unrelated process was terminated.

This satisfies the current goal's explicit alternative of a documented resource
stop identifying unfulfilled prerequisites. It does not satisfy #92's qualified
input/hardware acceptance criteria. A new task-selection decision is needed
before dependent work can resume; the existing frozen settings are unchanged.

## Commands available now

```bash
source ~/cd_vlaplan
python -u scripts/prepare_matched_final_tasks.py --workers 4 --dry-run
python -u scripts/run_matched_modalities.py prepare --workers 4 --dry-run
python -u scripts/run_matched_modalities.py verify --workers 4
python -u scripts/run_matched_modalities.py qualify --devices 0 1 --master-ports 18775 18776
```

The final command returns VALID_STOP without loading a model. Do not rerun old
#75/#76 `all` commands to get around the missing final task. A completed candidate
pool is safely reused by the candidate command. An interrupted new preparation
attempt needs `prepare --resume`; the current completed stop is verified instead.

Evidence: [compact result](preparation-result.json),
[candidate progress](candidate-progress.jsonl),
[preparation progress](preparation-progress.jsonl), and
[independent verification progress](verification-progress.jsonl).
Full source data and the independently verified preparation report remain under
`outputs/matched_modalities/v1/preparation/`.
