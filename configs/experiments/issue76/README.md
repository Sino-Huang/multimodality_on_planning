# Multimodal feasibility experiment (#76)

**Completed:** all four adapters and 48 episodes, independently replayed, in 64.92 minutes.
The retained outcome is VALID_STOP: all four learned settings fail the performance
gate. See [completion evidence](../../../docs/experiments/issue76/completion.md) and
[the #77 NO_GO decision](../../../docs/experiments/issue77/decision.md). No rerun is
part of the deadline study; commands below are retained for reproduction.

This four-hour run uses 512 declared source training records per algorithm,
one epoch (16 optimizer updates), seed 17, and the existing three-domain pilot
panel: storage, blocksworld and ferry, four algorithms, 48 condition episodes.
The exact record/task membership remains in `../issue75/pilot-plan-v1.json`.
Source corpora, images, goals, planning traces and Search Memory are reused.

This is a **within-multimodal feasibility comparison** of pretrained base, SFT,
random-valid and exact-reference controls. The completed #75 visual v5 run used
43,876 records and two epochs. Its training schedule is not matched to this pilot;
do not infer a controlled modality effect from their difference. #77 decides
whether the available evidence justifies further work under the remaining caps.
No visual retraining or multi-day multimodal replication is required here.

```bash
source ~/cd_vlaplan
python scripts/run_multimodal_issue76.py all --dry-run
python -u scripts/run_multimodal_issue76.py all
```

The run directory is `outputs/multimodal_development/issue76-feasibility-v1/attempt-001`.
The shared runner's workers carry the explicit #76 config even though their
internal command uses `run_visual_issue75.py`. GPUs 0 and 1 use MASTER_PORT 18675
and 18676, one model per GPU. The renderer uses existing localhost ports
18092–18095. Output streams progress and 20-second heartbeats and saves worker
logs under `launches/`. New calls stop at 3h45m; owned workers stop at 4h.
Incomplete coverage stays incomplete. Do not automatically restart a terminal
run or extend its budget.

Fresh qualification uses the actual multimodal processor/model inputs, the
largest and smallest selected inputs per algorithm, scalar/mixed/repeated batch
semantics, full 384-token timing, and disposable training probes. It does not
reuse visual hardware qualification. Trained adapters repeat the mixed-input
and base-isolation checks before evaluation. Each episode stores its modality;
read-only replay reconstructs that modality's complete token/page binding.

Worker reports retain elapsed time and training/evaluation peak allocated and
reserved GPU memory. The final report distinguishes complete pilot execution,
performance-gate outcome, and full-matrix scientific completion. Evaluation is
development evidence; no held-out or training-seed-variance claim is supported.

After the runner has a terminal `result.json`, independently verify the retained
experiment without model calls or changes to its original outputs:

```bash
source ~/cd_vlaplan
python scripts/verify_modality_experiment.py \
  --config configs/experiments/issue76/experiment.json \
  --output docs/experiments/issue76/completion-verification.json
```

The verifier checks every retained episode through the trusted runtime, exact
task/algorithm/condition/seed membership, final adapters, aggregate reports and
the performance gate. It records `PARTIAL` and exits with code 2 if terminal
coverage is incomplete; it never certifies a live run as complete. A complete
negative performance result can pass verification while its original gate stays
`VALID_STOP`. Point metrics are recomputed from replayed outcomes; bootstrap
statistics remain separately recorded in the original adjudication report.
