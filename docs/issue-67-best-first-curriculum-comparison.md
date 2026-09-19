# Issue 67: best-first curriculum and replacement comparison

Issue #67 uses the compact issue-64 v3 corpus and the completed issue-65 and
issue-66 development results. The active curriculum experiment is the cheaper
`best_first_add_greedy` representative cell. This is permitted by the parent
specification's requirement for curriculum controls in representative cells.

The three cells contain exactly the same 8,342 training examples and 6,696
validation examples. Only their fixed order differs:

- `staged`: easy, then medium, then hard;
- `shuffled`: the released seed-64 permutation;
- `mixed_order`: released difficulty round-robin order.

Every cell has one two-epoch LoRA training run with seed 17. ms-swift data-loader
shuffling remains disabled so the declared order reaches the trainer. With the
default two-GPU launch, staged and shuffled train together on devices 0 and 1;
mixed-order then trains on device 0. Their explicit `MASTER_PORT` values are
29670, 29671, and 29672.

## Frozen evaluation and conclusions

Evaluation uses rollout seeds 17, 29, 43, 71, and 101 against exact-reference,
random-valid, pretrained-base, and all three final curriculum checkpoints. One
backbone is loaded per evaluation GPU and the three LoRA adapters are switched
within deterministic batched rounds.

Qualification prices the complete 23-task panel first. If four physical model
conditions cannot fit the 15-hour rollout certificate, it selects the frozen
outcome-blind fallback: the cheapest whole issue-64 task in each of the 12
domains. It never selects tasks using model success. Each episode retains the
separate two-times-exact decision-call limit and exact expansion limit.

Curriculum success differences use 10,000 paired bootstrap resamples with seed
1729, 95% two-sided intervals, and the whole problem instance as the unit. A
pair is practically equivalent when its complete interval lies within the
frozen +/-0.05 success margin. An advantage requires both an interval excluding
zero and an absolute difference of at least 0.05. Invalid-operation rate and
budget usage are reported separately.

The abandoned h-max versus landmark-count experiment cannot support a heuristic
representation conclusion: its governed predecessor stopped, while both
replacement algorithms use `h_add`. The retained gated-not-run receipt records
that `ANCESTOR_STOP`. The valid replacement comparison is explicitly narrower:
`best_first_add_w3` versus `best_first_add_greedy` varies scalar priority and
closed-node reopening. A 10% reduction in model decisions is the frozen
material-efficiency threshold; the report also retains expansions and solution
cost without claiming optimality.

`PASS` means the selected curriculum product completed and every retained
episode passed semantic replay. `VALID_STOP` and `ANCESTOR_STOP` write a
gated-not-run receipt and are not scientific completion. A semantic replay or
coverage contradiction is `INVALID` and is never scientific completion.

The active path uses no hashes, checksums, fingerprints, artifact comparisons,
regeneration comparisons, or check mode.

## Operator command

```bash
source ~/cd_vlaplan
cd /data/scratch/projects/punim0478/sukaih/multimodality_on_planning

python scripts/run_best_first_issue67.py all \
  --devices cuda:0 cuda:1 \
  --training-devices 0 1 \
  --master-ports 29670 29671 29672 \
  --reference-workers 8
```

The command prints qualification batches, corpus rows, reference episodes,
training steps, rollout batches/logical calls, elapsed time, and ETA. Blocking
model loads and generation batches emit a heartbeat every 30 seconds. Resume an
interrupted pre-cutoff run with the same command plus `--resume`.

Before the long run, the complete no-write launch can be inspected with:

```bash
python scripts/run_best_first_issue67.py all --dry-run
```

## Completed result

The authorized run completed with scientific `PASS` on the frozen
cheapest-whole-task-per-domain panel. Outcome-blind qualification selected 12
tasks, projected the four-condition rollout at 19,949.97 seconds, and retained
a lower-95% throughput of 0.287157 calls per second.

Staged and shuffled resumed their interrupted first attempts from step 260;
both completed 522/522 steps in attempt 2. Mixed-order completed 522/522 steps
in attempt 1. These are one logical seed-17 training run per curriculum cell,
not independent training replicates.

The terminal product contains 72 reference episodes and 240 model episodes.
All 312 were reconstructed through semantic replay. Exact-reference,
random-valid, staged, shuffled, and mixed-order achieved complete
invariant-valid success with zero invalid operations. The pretrained base
achieved 0/60 and every output was invalid. All three curriculum pairwise
success differences and 95% intervals were exactly zero, establishing
practical equivalence under the frozen +/-0.05 margin on this selected panel.

The replacement setting comparison remains bounded: greedy used 6,696 versus
7,095 model decisions and 1,188 versus 1,351 expansions, but its 5.62% decision
reduction had a paired 95% interval from -4.77% to 16.97% and did not satisfy
the frozen 10% material threshold. Aggregate solution cost was 485 for greedy
versus 454 for weighted best-first. The original h-max versus landmark-count
heuristic-representation estimand remains `ANCESTOR_STOP`; the two replacements
share `h_add` and do not identify that effect.

The compact terminal result is retained at
`data/best_first_paired_phase_v3/issue67-terminal/result.json`.
