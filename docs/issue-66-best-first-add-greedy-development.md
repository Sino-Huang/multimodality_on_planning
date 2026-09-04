# Issue 66: additive greedy best-first development run

Issue #66 uses the completed issue-64 v3 corpus and only the
`best_first_add_greedy` condition (`h_add`, canonical generation-serial
tie-breaking, no closed-node reopening). It is cell-for-cell matched to issue
#65 on the same 23 development tasks and four conditions. The greedy product
contains 6,696 exact decisions, and no trace is larger than 923 decisions. The
largest separate 2x episode allowance is therefore 1,846 calls.

The active contract is
`issue-66-best-first-add-greedy-development-v1`. It authorizes one two-epoch
LoRA training run with seed 17. Base and learned evaluation use rollout seeds
17/29/43/71/101; random-valid uses the same five seeds and exact-reference
runs once per task. Whole problem instances are the uncertainty unit. No fresh
test task is opened.

The workflow uses scientific semantic replay only. It creates no hashes,
checksums, artifact comparisons, regeneration comparisons, or follow-up check
mode.

## Recommended command

```bash
source ~/cd_vlaplan
cd /data/scratch/projects/punim0478/sukaih/multimodality_on_planning

python scripts/run_best_first_issue66.py all \
  --devices cuda:0 cuda:1 \
  --reference-workers 8 \
  --training-device 1 \
  --master-port 29660
```

The outcome-blind hardware qualification runs before training. If the complete
23-task product does not fit the frozen 15-hour rollout qualification budget,
the command records `VALID_STOP`, adjudicates that stop, and does not train or
roll out the model.

Every long stage writes progress to the terminal. Model loads and blocking
generation batches emit a heartbeat every 30 seconds; corpus preparation,
references, training, rollout, and replay print completed work, elapsed time,
and estimated remaining time.

## Stage-by-stage commands

```bash
python scripts/run_best_first_issue66.py preflight
python scripts/run_best_first_issue66.py qualify --devices cuda:0 cuda:1
```

Inspect `outputs/best_first_phase/issue66-v1/qualification/qualification.json`.
If its coverage outcome is `VALID_STOP`, finish with:

```bash
python scripts/run_best_first_issue66.py adjudicate
```

If qualification passes, continue:

```bash
python scripts/run_best_first_issue66.py prepare
python scripts/run_best_first_issue66.py references --reference-workers 8
python scripts/run_best_first_issue66.py train --training-device 1 --master-port 29660
python scripts/run_best_first_issue66.py evaluate --devices cuda:0 cuda:1
python scripts/run_best_first_issue66.py adjudicate
```

The training command streams ms-swift output and reports progress against 522
optimizer steps. Evaluation uses one float32 Qwen backbone per GPU, switches
the single seed-17 adapter in place, and balances tasks by the frozen exact
decision cost.

If training, references, or rollout are interrupted before their cutoff, rerun
the corresponding command with `--resume`. Completed episode files are
semantically replayed and reused; missing episodes alone are generated.

## Interpretation

`PASS` means the complete authorized development product was collected and
semantically replayed. It does not by itself assert that process SFT is better
than either control. The report keeps invariant-valid success,
invalid-operation rate, budget usage, learned-versus-best-control gain, and
the whole-instance bootstrap bound separate. A qualification or wall-clock
resource stop is `VALID_STOP`; a semantic replay failure is `INVALID`.
