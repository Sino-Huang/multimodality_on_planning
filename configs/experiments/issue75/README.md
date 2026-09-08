# Visual development matrix (#75)

The runner is implemented and dry-run tested. **Attempt 001 stopped during GPU
qualification with `VALID_STOP`; #75 is not scientifically complete.** Both
workers completed 4 of 31 qualification probes before the one-hour limit. No
references, training or evaluation ran. See
`docs/experiments/issue75/attempt-001-verification.json` for the verification.

Preparation passed the full repository suite (1,002 tests, 13 skipped), followed
by 18 focused tests after review fixes, plus formatting, lint and type checks.
All 31 selected teacher snapshots replayed on CPU with zero
model calls. The retained preparation summary is in
`docs/experiments/issue75/development-summary.json`; these checks do not establish
GPU readiness or replace the actual qualification stage.

## Operator commands

From the repository:

These are the original attempt commands. Attempt 001 now has an immutable final
receipt, so neither a fresh launch nor `--resume` can restart it. Address the
qualification runtime and prepare a separately authorized successor before
another actual run.

```bash
source ~/cd_vlaplan
python scripts/run_visual_issue75.py all --dry-run
python -u scripts/run_visual_issue75.py all
```

The actual command uses GPUs **0 and 1**, one model process per GPU, with distinct
`MASTER_PORT` values **18575 and 18576**. Four isolated localhost renderer ports
are **18092–18095**. The reference workers each own one backend endpoint. GPU
training jobs queue sequentially on each GPU, so two adapters train concurrently
and four train in total. The exact child commands and environment mappings are
printed by the dry-run and retained under the attempt's `launches/` directory.

Those renderer ports were reachable during development. If the backend is no
longer running, start it in another terminal before the actual matrix command:

```bash
source ~/cd_vlaplan
.cache/issue70-backend-venv/bin/python scripts/serve_issue70_planimation.py \
  --port 18092 --workers 4
```

Every stage flushes JSON progress with completed/total, elapsed time and ETA.
The parent and worker emit heartbeats every **20 seconds** during blocking model
loads, generation, diagnostics, and replay. Child output is streamed to the
terminal and retained in `launches/<stage>/worker-*.log`. A failed worker stops
its siblings and queued work; it does not leave unrelated training jobs running.

The final outcome is written to:

```text
outputs/visual_development/issue75-32k-v1/attempt-001/result.json
```

After an interruption **without** a final result, resume with:

```bash
python -u scripts/run_visual_issue75.py all --resume
```

The original monotonic clock is retained, including downtime; wall-clock
adjustments cannot extend the allowance. Completed episodes are
semantically replayed and reused; completed training cells use their retained
final adapter, and interrupted training resumes its latest checkpoint. A
completed PASS, VALID_STOP or INVALID attempt is immutable. A later attempt or
changed scientific setting requires a successor experiment and matching
`authorization.json`; `--resume` cannot reset the time budget.

## Scope and budgets

This successor consumes the completed #74 matched corpus, retaining the #72/#73
32K scope, source splits, source-goal semantics and common Search Memory.
It runs **visual-state only** for BFS, unpruned BFWS, additive w3 and additive
greedy. The four conditions are exact-reference, oracle-assisted random-valid,
pretrained base, and process SFT. It does not run #76's multimodal conditions or
claim a learned text/visual comparison.

The full development scope has **97 task groups / 120 algorithm episodes**.
There are 120 exact references and five evaluation seeds for each other
condition, producing **1,920 logical episodes**. Seeds are 17, 29, 43, 71 and 101;
they are rollout/reference seeds, not independent training replicates.

Each algorithm has exactly one seed-17, two-epoch LoRA training run:

| Algorithm | Training rows | Optimizer steps |
| --- | ---: | ---: |
| BFS | 11,911 | 746 |
| BFWS | 14,225 | 890 |
| Additive w3 | 9,398 | 588 |
| Additive greedy | 8,342 | 522 |

The language-model linear layers use rank-64 LoRA (alpha 128, dropout 0.05),
with the vision backbone frozen. Training uses bf16, SDPA, a global batch of 32,
AdamW at 1e-4, cosine scheduling, and sequential staged curriculum order.
Instruction and image tokens are masked from the loss; only the assistant
teacher target is supervised. Intermediate checkpoints receive teacher-forced
dev-loss diagnostics at approximately one-third and two-thirds of the updates.
Only the final adapter is used for rollout; no dev-success checkpoint selection
or reuse of a historical text adapter occurs.

Inputs use 32,768 total tokens with 384 reserved for output. Inference uses
float32, at most eight requests per batch and 48,000 padded input tokens. The
scheduler permits at most one request from an active episode per round. Every
logical episode has its own allowance of twice its matching exact-reference
**decision count**, with the reference expansion count enforced separately.
There is no cross-episode or cross-adapter output cache; KV caching lasts only
for the current generation call.

One attempt clock covers qualification, references, training, rollout and
adjudication: 20 hours total; no new calls after 18 hours; rollout certification
must fit 15 hours. Stages cannot start without matching authorization and their
completed scoped predecessors. The old #71 8K phase and earlier experiment
receipts are not rewritten or silently reused at 32K.

## What the actual command does

1. **Qualification.** On both GPUs, load the frozen Qwen revision and test every
   occupied algorithm/difficulty/input-size bin. Use scalar, mixed-length batch,
   repeated-batch and runtime-semantic probes across all three modality inputs.
   Time full 384-token generations conservatively. A disposable, zero-learning-
   rate adapter measures training memory and timing; it produces no learned
   checkpoint. These measurements do not inspect model success for selection.
2. **Selection.** Estimate the full visual workload, including training and the
   two teacher-forced diagnostic passes. If it cannot fit, try the predefined
   cheapest complete task per domain/family; the two additive settings stay
   paired. This fallback contains 42 task groups. The selected task IDs are
   recorded for subsequent matched-modality experiments. No tasks are selected
   using model outcomes, and training rows remain the complete frozen train set.
   If neither panel fits, write `VALID_STOP` before starting training.
3. **References and training.** Execute/replay complete exact and random-valid
   references, then train the four visual adapters under the original clock.
4. **Evaluation.** Before scientific rollout, check the actual trained adapters
   for scalar/batch/repeated semantics and base/adapter isolation. Run base and
   final-adapter episodes in deterministic rounds and retain complete evidence.
5. **Adjudication.** Independently reconstruct every episode, including exact
   model-facing page bindings and trusted runtime effects. Require the entire
   selected task/algorithm/condition/seed product. Report success, invalid
   operations, budget usage and learned-minus-best-control gain separately,
   with paired whole-instance bootstrap bounds and per-seed success summaries.

Qualification is deliberately conservative: it uses maximum measured call and
microstep costs plus a 1.2 safety margin. A dry-run validates command/configuration
readiness; it does **not** certify CUDA memory, throughput or scientific success.
The real qualification can therefore end in a governed resource stop.

## Live visual observations and evidence

Every model call receives the complete ordered task-context, current-state and
partial-goal page set, using the same shared projection as the released corpus.
The state-page cache is shared across corpus and live views and bounded to
64 MiB per process. Existing 128×128 scenes are referenced directly.

If an accepted operation reaches a state outside the expert catalog, the runner
replays its parent Action Sequence through localhost Planimation and retains the
new scene, VFG provenance and readable page recipe. It never sends an earlier
input the image of its future successor. The PDDL runtime remains authoritative;
there is no hosted endpoint, solver fallback, invented solved-goal scene, or
state-dependent goal-satisfaction annotation. Replay checks existing bindings
without rendering missing images.

The new visual BFS controller accepts any applicable unvisited successor that
preserves FIFO updates. Canonical teacher targets stay unchanged. This implements
the parent specification's evaluation tie policy without changing the older
BFS text runner or retrospectively reinterpreting its results. The visual BFWS
session also preserves the source corpus's explicit empty novelty partitions;
this adds no novelty facts and leaves the older BFWS runner unchanged. Invalid policy
operations are charged and never repaired; deterministic invalid operations
terminate the episode unsuccessfully.

Completed episode files contain the authoritative input, emitted operation,
acceptance status, current page binding, post-operation successor binding and
terminal metrics. Completed episodes are saved immediately, including episodes
finishing in the last allowed batch. Incomplete coverage cannot satisfy the gate.
No hashes, checksums, integrity machinery or regeneration comparisons are used.

## Outcomes

`PASS` requires complete selected coverage and the frozen competence thresholds:
exact success 1.0, learned success at least 0.8 and learned invalid-operation
rate at most 0.05 in every setting. Learned superiority is a separate claim:
a positive paired gain bound over the best control is reported explicitly.
Saturating the oracle-assisted random-valid control does not establish an
advantage.

Ordinary resource/threshold failures are `VALID_STOP`; stopped predecessors
produce `ANCESTOR_STOP`; semantic, scope, provenance or permission defects are
`INVALID`. Governed stops produce `gated-not-run` receipts; `INVALID` never means
scientific completion. Keep #75 open until its actual execution criteria have
been adjudicated from the retained experiment evidence.
