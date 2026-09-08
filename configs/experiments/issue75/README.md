# Visual development matrix (#75)

The runner performs visual-state qualification, references, training, rollout and
adjudication. Run it directly; no authorization or approval file is required.
The original v1 attempt remains preserved. It stopped after one hour during
qualification and produced no training or evaluation results.

## Run

```bash
source ~/cd_vlaplan
python scripts/run_visual_issue75.py all --dry-run
python -u scripts/run_visual_issue75.py all
```

The current configuration writes to a fresh directory:
`outputs/visual_development/issue75-32k-v2/attempt-001`.
Dry-run prints all child commands and writes no experiment outputs or model calls.

For another fresh run, choose a new output directory:

```bash
python -u scripts/run_visual_issue75.py all \
  --output outputs/visual_development/issue75-32k-v2/attempt-002
```

For an interrupted run that has no final `result.json`, use the same directory
and `--resume`. Resume retains its settings and original monotonic clock,
including downtime; it replays completed episodes and resumes training from the
latest checkpoint. A completed result is preserved; use a new directory to rerun.
Settings are ordinary JSON in `experiment.json`. Each run records a snapshot of
those settings. Changing them does not require a matching approval document.

The runner uses GPUs **0 and 1**, one model process per GPU, with distinct
`MASTER_PORT` values **18575 and 18576**. Four localhost renderer ports are
**18092–18095**. If the renderer is not running, start it in another terminal:

```bash
source ~/cd_vlaplan
.cache/issue70-backend-venv/bin/python scripts/serve_issue70_planimation.py \
  --port 18092 --workers 4
```

Worker output is streamed to the terminal and saved in
`launches/<stage>/worker-*.log`. Progress includes completed/total, elapsed time
and ETA; **20-second heartbeats** retain the latest activity and progress.
Qualification logs each scalar, mixed batch, repeated batch and timing operation.
Completed probe measurements are saved under
`qualification/worker-<n>-probes/` even if a later probe stops. These partial
measurements do not count as complete qualification.

## Qualification timeout fix

The original code scheduled **940 generation calls per GPU**: it tested three
modalities for this visual-only matrix and repeatedly generated scalar outputs
for identical entries in mixed batches. Model loading took about a minute,
whereas each of the first four complete probes took roughly 11–16 minutes.
A separate one-hour cutoff stopped the run after 4 of 31 probes.

The current visual qualification schedules **151 generation calls per GPU**,
an 84% reduction in calls, keeping all 31 selected probe records. It computes one
scalar result for each distinct input and compares every position in both the
mixed batch and repeated batch against that result. It retains full 384-token
generation timing, actual processor/context checks and the training hardware
probe. Trained-adapter qualification uses the same distinct-input comparison and
still checks base/adapter isolation. This does not cache scientific rollout
outputs. Text and multimodal generation qualification belongs to those runs;
this visual run does not certify them.

Qualification now uses the overall run deadline instead of a separate one-hour
limit. The **20-hour total budget**, **18-hour new-call cutoff** and **15-hour
rollout estimate limit** remain. Actual CUDA memory and throughput can still
produce a resource stop. The reduced call count is measured from the real
corpus; the revised full GPU runtime has not yet been measured.

## Data and execution

The input is the complete #74 matched corpus. All #72/#73 state/goal pages,
source splits, teacher targets and bounded Search Memory remain unchanged.
Each observation attaches its complete context, current-state and partial-goal
pages. Existing scenes are referenced directly. Newly accepted states outside
the expert catalog are rendered from their supplied Action Sequence through
localhost Planimation, after the producing operation. Replay never renders a
missing image. The state-page cache is shared and bounded to 64 MiB per process.

The four algorithms are BFS, BFWS, additive w3 and additive greedy. The full dev
scope contains **97 task groups / 120 algorithm episodes / 1,920 condition
episodes**, covering exact reference, random-valid, pretrained base and process
SFT. Evaluation seeds are 17, 29, 43, 71 and 101. Each algorithm trains exactly
one seed-17 adapter; these are not independent training-seed replicates.

| Algorithm | Training rows | Optimizer steps |
| --- | ---: | ---: |
| BFS | 11,911 | 746 |
| BFWS | 14,225 | 890 |
| Additive w3 | 9,398 | 588 |
| Additive greedy | 8,342 | 522 |

Training uses two epochs, bf16, SDPA, global batch 32 and language-model LoRA
rank 64 (alpha 128, dropout 0.05), with the vision backbone frozen. Only assistant
teacher targets receive loss. One-third and two-thirds checkpoints receive
teacher-forced dev-loss diagnostics; only the final adapter is evaluated in
rollout. Inference uses float32, 32,768 context tokens with 384 reserved for
output, and batches of at most eight requests / 48,000 padded input tokens.

The stages are qualification, cost-only panel selection, references, training,
model evaluation and independent replay/adjudication. If the full dev workload
cannot fit, selection tries the predeclared cheapest complete task per
domain/family (42 task groups), keeping additive settings paired. Selection never
uses model success and retains the complete training set. Later matched
modalities must use the same selected panel for a comparison.

Every episode has twice its exact-reference decision-call allowance and a
separate expansion limit. Deterministic rounds issue at most one request per
active episode. Invalid operations are charged and never repaired. BFS accepts
valid FIFO ties; BFWS preserves the teacher corpus's explicit empty novelty
partitions. Completed episodes are retained immediately and independently
replayed. Partial coverage cannot pass adjudication.

## Results

Read `<output>/result.json` for the final outcome. `PASS` requires complete
selected coverage and the configured competence thresholds: exact success 1.0,
learned success at least 0.8 and learned invalid-operation rate at most 0.05 in
each setting. Learned-versus-best-control gain and paired whole-instance
bootstrap bounds are reported separately; panel success alone is not an
advantage claim.

`VALID_STOP` records a resource or threshold stop; `ANCESTOR_STOP` records a
stopped prerequisite; `INVALID` records a configuration, semantic or execution
error. None implies a completed successful matrix. There are no approval
receipts in new runs. The old attempt's receipts and source data are preserved
as historical evidence. Keep #75 open until actual execution is adjudicated.
