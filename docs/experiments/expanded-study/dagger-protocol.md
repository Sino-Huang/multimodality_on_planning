# Expanded DAgger correction and comparison protocol

Goal 4 defines the reusable correction boundary for #78 and freezes the
comparison for #79. `dagger-protocol.json` is the authoritative ordinary config.
It was frozen before any new correction collection or persistent parameter
update. Goal 4 runs only unscored capacity probes and discarded in-memory
optimizer steps; Goals 5 and 6 own collection and scientific training.

## Correction boundary

Collection uses BFS on the 25 whole training instances represented by the
original ordered 512-record BFS membership. Development and final tasks are
rejected by the interface. Each modality and iteration has at most 512 student
decisions and 128 expert corrections. Each task keeps a model-call limit equal
to twice its matching exact-reference decision count, independent of
expansions.

The student output is strictly parsed and submitted to a pure trusted-runtime
validator. A rejected operation consumes one invalid-operation charge and is
never applied. The record preserves the raw student text, parse result, trusted
runtime result, complete last-valid Search Memory, observable model input and
page binding. If correction quota remains, the deterministic BFS expert is
queried using that identical input and binding. Its accepted operation is linked
to the resulting rollout event and is applied so collection can continue. Replay
reconstructs the session and verifies every input, rejection, correction,
accepted event and final Search Memory without a model call.

If the correction quota is already exhausted, the next rejected student output
is retained without an expert query and that modality/iteration stops. All
unused decision and correction quota expires in its own cell. It is never moved,
duplicated, filled with invented corrections or used to expand another cell.

## Aggregation and training

Corrections are cumulative through the current iteration. Genuine repeated
inputs remain in collection evidence, but only the earliest occurrence enters
training; conflicting expert targets for identical inputs invalidate the data.
Every verified unique correction replaces one record at the end of the ordered
original-SFT membership. The remaining prefix of original records fills unused
correction slots, yielding exactly 512 records without duplicating corrections.

Both DAgger and continued-SFT use one epoch, 512 records, global batch 32,
microbatch 1, gradient accumulation 32, seed 17, a sequential sampler with
reshuffling disabled, and exactly 16 optimizer updates. Each iteration loads
adapter weights only and starts a new optimizer and scheduler. Continued-SFT
uses the unchanged original 512 records in both iterations. DAgger iteration 1
starts from the verified v5 BFS adapter; iteration 2 collection and training
start from the same modality's DAgger iteration-1 final adapter. The analogous
continued-SFT iteration 2 starts from continued-SFT iteration 1.

Collection and updates alternate: collect/replay iteration 1, train both arms,
collect/replay iteration 2 using the updated DAgger policy, train both final
arms, then evaluate final checkpoints. Only the final checkpoint from the single
seed-17 training run enters evaluation. No training-seed variance is claimed.

The estimand is the within-modality difference between two-iteration DAgger and
exposure-matched continued SFT from the same starting adapter. Each modality is
collected on-policy, so trajectories and correction examples need not match.
Cross-modality contrasts therefore do not isolate a modality effect.

## Hardware and cost qualification

Two shared-scheduler workers loaded all three verified BFS adapters on the two
A100s. GPU 0 used `MASTER_PORT=18800` for text and multimodal; GPU 1 used
`MASTER_PORT=18801` for visual. Each modality passed prompt-only scalar and
repeated-batch generation at the full 384-token output allowance. Repeated
batches and the first scalar/batch item were byte-identical for every modality.
Each adapter also completed one finite discarded in-memory optimizer step as a
trainable adapter without changing its source checkpoint. Both worker hooks and
the final CPU hook passed. The probes consumed 0.141611 GPU-hours and produced
no collection decisions, corrections or persistent updates.

The full model-call allowance would require an estimated 234.941909 GPU-hours,
so completion under every worst-case episode allowance is not guaranteed. The
frozen historical-consumption estimate is 35.458081 GPU-hours including the
qualification probes, below the 48-hour DAgger ceiling. This conditional
admission does not remove tasks or inspect model scores for coverage selection.
If realized calls exceed the estimate, the absolute cutoff preserves explicit
missingness rather than changing the protocol or budget.

The executed qualification commands are:

```bash
source ~/cd_vlaplan && python scripts/qualify_expanded_dagger.py prepare
source ~/cd_vlaplan && python scripts/run_expanded_study.py launch --job configs/experiments/expanded-study/dagger-qualification-0-job.json
source ~/cd_vlaplan && python scripts/run_expanded_study.py launch --job configs/experiments/expanded-study/dagger-qualification-1-job.json
source ~/cd_vlaplan && python scripts/run_expanded_study.py launch --job configs/experiments/expanded-study/dagger-qualification-final-job.json
```

`dagger-qualification.json` contains the retained measurements and cost
admission. Raw unscored capacity outputs, scheduler terminals, heartbeats and
hook results remain under the corresponding ignored job directories.

## Iteration-one collection commands

Goal 5 pins the resumable collector at commit
`f338b17589ce4454d255b68a4ef75b7eacedf772`. Each episode journals the raw
student output before applying it, then atomically records its validation,
expert query when charged, accepted rollout link, and live-view provenance.
Resume replays the journal to the exact pending state before another model
call. GPU 0 collects text followed by multimodal with a 32,400-second ceiling;
GPU 1 collects visual with an 18,000-second ceiling. Their completion hooks
independently replay their correction sets on CPU. After both hooks pass, the
final CPU job reconstructs all three 512-record aggregation memberships and
publishes compact iteration-one evidence.

```bash
source ~/cd_vlaplan && python scripts/run_expanded_dagger_collection.py prepare
source ~/cd_vlaplan && python scripts/run_expanded_study.py launch --job configs/experiments/expanded-study/dagger-collection-0-job.json
source ~/cd_vlaplan && python scripts/run_expanded_study.py launch --job configs/experiments/expanded-study/dagger-collection-1-job.json
source ~/cd_vlaplan && python scripts/run_expanded_study.py launch --job configs/experiments/expanded-study/dagger-collection-final-job.json
```

The final job is launched only after both GPU jobs and their hooks finish.
Goal 5 performs no parameter update. Issues #80–#83 remain open until Goal 6
uses the verified iteration-one data, collects iteration two from the updated
DAgger policies, and verifies the complete two-iteration coverage.

## Goal 6 execution and result

Goal 6 followed the frozen alternating order. The first training round consumed
the verified iteration-one aggregations and the unchanged original-SFT control
membership. Iteration-two collection then loaded each modality's DAgger
iteration-one final adapter. The final training round loaded the matching
DAgger or continued-SFT iteration-one adapter with a new optimizer and scheduler.
All twelve training cells used 512 records, seed 17, one epoch and 16 optimizer
updates; independent hooks verified every final checkpoint and its lineage.

Iteration two collected 128 expert corrections per modality from training tasks
only. Text used 307 student decisions, visual used 357, and multimodal used 290.
Each cell retained 129 invalid student operations, including the final rejection
after correction-quota exhaustion. Independent replay verified all 384 new
corrections and 37 completed episodes. Deduplication across both genuine
on-policy rounds left 201 cumulative text corrections, 203 visual corrections
and 181 multimodal corrections in the three final 512-record DAgger
aggregations. No quota was transferred or filled.

Evaluation used only the final iteration-two checkpoints. The fixed comparison
contains five arms on all three modalities over the same three development and
24 unseen tasks, for 405 episodes and 81 whole-problem modality-task rows.
Original process SFT, random-valid and exact-reference records were reused and
verified under the same contracts. Both the scheduled completion hook and a
standalone audit independently replayed all 405 episodes.

The result does not support a DAgger advantage. On the 72 unseen
modality-task rows, DAgger and exposure-matched continued SFT each achieved one
invariant-valid success, with one paired DAgger win, one paired loss and 70
ties. Original SFT achieved zero successes, random-valid achieved 45, and exact
reference achieved 72. DAgger made 71 invalid operations in 225 decisions
(31.56%); continued SFT made 71 in 406 (17.49%). Development results were 3/9
for DAgger, 2/9 for continued SFT, 1/9 for original SFT, 6/9 for random-valid,
and 9/9 for exact reference. These are single-training-seed results and do not
estimate training-seed variance.

The branch consumed 10.909219 GPU-hours of its unchanged 48-GPU-hour cap:
2.220535 for qualification and iteration-one collection, 3.197716 for training,
2.898848 for iteration-two collection, and 2.592120 for evaluation. This total
includes 0.316394 GPU-hours from retained technical failures. The evaluation
retry repaired missing expanded-view persistence fields in `a0b8d53` and resumed
the frozen completed episodes and pending journals; it did not replace or select
outcomes.

The tracked comparison is `dagger-comparison.json`, including every paired row,
separate validity/search, expert-query and compute fields. The complete
requirements, artifact digests, scheduler attempts and replay results are in
`goal6-completion-audit.json`.
