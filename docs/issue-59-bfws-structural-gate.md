# Issue 59 BFWS process-SFT and structural gate

Issue 59 consumes the complete issue-57 exact BFWS release and issue-58 process
projection under phase `issue-56-bfws-development-v1`. It never reads the
fresh 45-task held-out test manifest. This is a development structural gate,
not an efficacy-test run.

## Implemented contract

- Process-only LoRA SFT uses all 47,780 train and 21,239 dev records from the
  105 atomic ms-swift shards released by issue 58. The supervisor's issue-59
  budget override authorizes one two-epoch training run only: seed 17 on physical
  `cuda:1`. Its final checkpoint is the sole learned checkpoint. This does not
  estimate training-seed variance from the five seeds originally frozen by
  issue 56.
- Exact BFWS evidence is independently reopened from issue 57. Random-valid,
  pretrained-base, and process-SFT conditions use the same trusted BFWS session,
  bounded `bounded_bfws_search_memory_v1` input, 16 accepted deltas, 7,808/384
  token limits, matching exact expansion limit, and a separate model-call limit
  of twice the task's exact-reference decision count.
- GPU inference is deterministic float32 batching with one backbone per GPU,
  isolated adapter caches, at most one request per active episode per round,
  batch size 8, and 48,000 padded input tokens.
- Qualification uses six retained issue-57 input snapshots, observes no model
  outcomes, and requires scalar/batch byte parity plus repeated-batch parity.
  It tries all 35 dev tasks first. The preregistered exact-cost fallback is the
  cheapest exact-decision task in each of the 15 domains, selected by
  `(exact decisions, difficulty, instance ID)` before any model result. Its
  maximum unique scheduled-call budget is 9,076; full coverage is 84,956.
- The gate clock starts when qualification finishes. New model calls stop at
  18 hours and replay/adjudication must finish by 20 hours. Partial selected
  coverage cannot pass.
- Episode inputs, raw outputs, accepted operations, and results are retained as
  atomic gzip JSON evidence. Adjudication reconstructs every bounded input and
  trusted transition without model inference before computing metrics.
- CPU reference episodes run in a bounded process pool (eight workers by
  default, never more than the available CPU affinity). Completion order may
  vary, but the final manifest retains the frozen task/seed ordering.

## Dry-run verified by the agent

The following command validates every retained dependency and prints the exact
single training launch, qualification plan, two GPU rollout shards, and
adjudication inputs without running learning or model inference:

```bash
source ~/cd_vlaplan
python scripts/run_bfws_issue59.py all --dry-run
```

The installed ms-swift 4.2.2 launcher also resolved the generated seed-17 smoke
argument vector and exited successfully through its help path. No training,
random-reference generation, hardware qualification, or model rollout was run
by the implementation agent.

## Human execution

Run the full workflow on the two A100 GPUs:

```bash
source ~/cd_vlaplan
python scripts/run_bfws_issue59.py all --devices cuda:0 cuda:1
```

The command runs references, one seed-17 training on `cuda:1`, outcome-blind qualification,
both rollout shards, and adjudication in order. It prints live subprocess output
and JSON progress records containing completed work, total work, elapsed time,
and estimated remaining time. A qualification `VALID_STOP` skips rollout and
goes directly to a gated-not-run adjudication receipt.

For operational control, the same workflow can be run stage by stage:

```bash
python scripts/run_bfws_issue59.py preflight
python scripts/run_bfws_issue59.py references --resume
python scripts/run_bfws_issue59.py train --devices cuda:1 --resume
python scripts/run_bfws_issue59.py qualify --devices cuda:0 cuda:1
python scripts/run_bfws_issue59.py evaluate --devices cuda:0 cuda:1 --resume
python scripts/run_bfws_issue59.py adjudicate
```

Reference and rollout evidence resume within the same immutable launch.
Interrupted or failed training is preserved and the next invocation creates a
new numbered attempt that resumes the newest complete ms-swift checkpoint.
Training saves every half epoch (747 optimizer steps), so at most half an epoch
is lost to interruption. A one-step non-scientific smoke launch is available
with `train --smoke`; it never satisfies final-checkpoint discovery or resume.

If reference generation was interrupted, resume its retained atomic episodes
without regenerating them:

```bash
python scripts/run_bfws_issue59.py all \
  --devices cuda:0 cuda:1 \
  --reference-workers 8 \
  --resume
```

Every existing random-valid episode is reopened and independently replayed.
Only missing task/seed episodes are generated. Parallel completion cannot
change the deterministic final manifest order.

## Frozen adjudication

The selected process-SFT product must satisfy all of these predeclared checks:

- exact-reference invariant-valid success = 1.0;
- process-SFT invariant-valid success at least 0.8;
- process-SFT invalid-operation rate at most 0.05;
- absolute gain over the better of base and random-valid at least 0.1;
- paired 10,000-resample whole-instance bootstrap gain lower bound at least 0.

Uncertainty is over whole problem instances. The budget-limited contract makes
no claim about training-seed variance.

`PASS` requires complete replay-valid selected coverage and all thresholds.
Ordinary model, threshold, qualification, or resource failure is `VALID_STOP`.
A prerequisite stop is `ANCESTOR_STOP`. Any manifest, provenance, input parity,
or replay mismatch is `INVALID` and is never scientific completion.

## Terminal execution

The supervised run completed under contract
`issue-59-bfws-single-training-v2`. Seed 17 trained for the authorized two
epochs (2,988 optimizer steps) and produced complete checkpoints at steps 747,
1,494, 2,241, and 2,988. The training report outcome is `PASS`. The reference
manifest contains all 210 expected entries: 35 exact BFWS episodes and 175
random-valid episodes.

Outcome-blind hardware qualification measured a lower-95% throughput of
0.180490565 calls per second. The preregistered 15-domain exact-cost panel
required at most 9,076 scheduled calls and projected 60,424.319 seconds after
the frozen safety margin. This could not be certified within the frozen
15-hour rollout-certification budget, so qualification returned `VALID_STOP`
with no selected tasks and without observing model outcomes.

No learned, base, random-valid, or exact-reference rollout matrix was launched;
therefore this attempt contains no BFWS SFT performance result. Adjudication
correctly emitted a `VALID_STOP` gated-not-run receipt with
`scientific_completion: false`. This is a valid terminal resource outcome, not
an `INVALID` run and not evidence that the learned policy passed or failed the
structural thresholds. Any downstream scientific run requiring a `PASS`
ancestor must remain gated.

Compact tracked copies of the terminal records are retained at:

- `data/bfws_phase_v1/issue59-terminal/training-report.json`;
- `data/bfws_phase_v1/issue59-terminal/qualification.json`;
- `data/bfws_phase_v1/issue59-terminal/adjudication-report.json`;
- `data/bfws_phase_v1/issue59-terminal/gate-receipt.json`.

The 2 GB optimizer-bearing checkpoint and atomic reference evidence remain in
the ignored execution output tree and are intentionally not committed to Git.
