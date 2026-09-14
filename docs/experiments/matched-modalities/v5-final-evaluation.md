# V5 final evaluation execution

The user explicitly authorizes the final v5 evaluation. All twelve checkpoints
and the existing CONTINUE decision were revalidated before launch. The original
v2 ledger records zero evaluation spending at launch; the three modalities share
21,600 seconds, including loading and failed attempts. No reset or extension is
permitted. Unrelated GPU processes remain running.

`scripts/run_matched_evaluation_chain.sh` runs text-state, visual-state and
multimodal-state serially with study-v5.json, GPUs 0/1, MASTER_PORT 18775/18776
and supported resume. The EXIT hook writes automatic-evaluation/completion.json;
per-modality logs retain stage progress and heartbeats. The final verify stage
independently replays all 144 declared logical episode bindings (72 model
episodes). Every worker also replays each completed episode before writing it.

Inputs, fixed tasks, seed, algorithms, base/SFT/reference/random conditions,
checkpoints and inference settings are unchanged. Each completed episode records
per-call input tokens, generated sequence tokens (including stopping tokens),
call wall time and episode wall time. Evaluation calls are scalar, so the raw
generated length has no batch-padding ambiguity. This instrumentation does not
alter generation or policy decisions. Source visual images remain unlabelled
128px scenes; semantic parity with text is not claimed.

All three dry-runs passed. The focused execution/input/replay suite passed 32
tests; the updated real-processor generation receipt regression also passed.
Execution and independent verification are complete. See [machine-readable evidence](v5-final-evaluation.json) for every episode binding, outcome, checkpoint and measured cost.

The automatic chain exited successfully at 2026-09-14 07:43:06 UTC. All three
modalities completed 48 logical bindings apiece: 24 model episodes and 24
reference episodes. There are 144 bindings and 72 model episodes overall. No
physical reference reuse was used. No task, representation, checkpoint, seed,
inference setting or episode budget changed after seeing outcomes.

The independent CLI verification passed, and a separate post-run audit replayed
all 144 episodes again, revalidated all twelve checkpoints and checked worker
coverage, per-call token/timing receipts, termination results and shared-ledger
accounting. There is no missing execution or infrastructure failure in this run.
Model-invalid operations and reference expansion-budget exhaustion are observed
terminal outcomes and remain included.

| Modality | Base successes | SFT successes | Random-valid successes | Exact successes |
| --- | ---: | ---: | ---: | ---: |
| Text | 0/12 | 5/12 | 10/12 | 12/12 |
| Visual | 0/12 | 6/12 | 10/12 | 12/12 |
| Multimodal | 0/12 | 6/12 | 10/12 | 12/12 |

These are invariant-valid success counts over four algorithms and three
problems, not twelve independent problem instances. The high random-control
success and tiny panel preclude claiming a learned advantage from these counts.
Unlabelled 128px images can lose identities; equal semantic information with
text is not established. Trace-based analysis belongs to #97/#109.

Cumulative evaluation spending is 1,221.82 seconds (20.36 minutes) of 21,600,
with one launch per modality and no failed attempt or budget reset. The full
six-hour allowance was a maximum, not a required duration; many model episodes
terminated early on invalid operations. Worker wall duration is reported
separately from stage wall time and is not a GPU-utilization measurement.

Reproduce the read-only verification using:

```bash
source ~/cd_vlaplan
python -u scripts/run_matched_modalities.py verify --study configs/experiments/matched-modalities/study-v5.json --workers 4
```

Episode records and worker receipts remain under
`outputs/matched_modalities/v5/evaluation/`; launch evidence remains in the
shared ledger and v5 launches directory. The original scenes, traces, training
artifacts and historical feasibility results are preserved.
