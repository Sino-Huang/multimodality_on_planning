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
Execution is pending terminal evidence. No ticket is closed merely for launching.
