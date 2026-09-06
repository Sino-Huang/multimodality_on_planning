# Matched three-modality development episode (#70)

This is a small infrastructure test using the exact candidate reference and
`best_first_add_greedy`. It executes three independent controllers over the same
three-room task, with the text-state, visual-state, and multimodal-state inputs
from #69. The reference reads only the declared model-facing candidate memory.
It does not load model weights or test learned visual reasoning.

The committed contract, gate, and authorization cover only this development test.
The user request to implement and test #70 is the authorization basis. #71 must
freeze and authorize the production modality matrix separately. The input-size
bins here describe this fixture; they are not representative throughput evidence.

The live localhost run on 2026-09-06 passed in approximately 25 seconds:

| Modality | Goal reached | Decisions | Expansions | Invalid operations | Input tokens |
| --- | --- | --- | --- | --- | --- |
| text-state | yes | 3 | 2 | 0 | 361–459 |
| visual-state | yes | 3 | 2 | 0 | 3281–3379 |
| multimodal-state | yes | 3 | 2 | 0 | 3439–3537 |

The observations include a successor returning to the closed initial state,
so exact duplicate membership is exercised. All three operation sequences and
runtime results align. The pinned Qwen processor counts chat-template and image
tokens without loading model weights. The full JSON evidence is retained at
`docs/experiments/issue70/live-report.json`; generated PNGs/VFG and the original
report remain in `outputs/modality_phase/issue70-v1/` in the execution workspace.
Offline replay uses the embedded PDDL, operations, frame bindings, relation
drawing commands, and Search Memory. It neither calls a policy nor renders or
compares artifact contents. The visual condition retains #69's labelled relation
panels; this is not certification of arbitrary unannotated profile geometry.

## Inspect or replay the completed result

```bash
source ~/cd_vlaplan
python scripts/run_matched_modality_issue70.py --dry-run
python scripts/run_matched_modality_issue70.py --replay docs/experiments/issue70/live-report.json
```

The dry-run verifies receipt bindings and supplied-path progression without HTTP,
tokenization, policy calls, or output writes. Offline replay validates every
position, goal semantics, exact memory membership, charged invalid operations,
budgets, state-frame associations, and the terminal result. It performs no hash,
checksum, artifact-integrity, or regeneration comparison.

## Run on a fresh checkout

The active Conda environment supplies the project/Pillow/transformers dependencies.
The frozen Qwen processor must already be in the Hugging Face cache. The backend
clone is inspected/imported read-only. Start its localhost WSGI service in one
terminal (the in-memory database and disabled bytecode avoid writes to the clone):

```bash
source ~/cd_vlaplan
python -m venv --system-site-packages .cache/issue70-backend-venv
.cache/issue70-backend-venv/bin/python -m pip install -r configs/experiments/issue70/backend-requirements.txt
.cache/issue70-backend-venv/bin/python scripts/serve_issue70_planimation.py
```

Then, in another terminal:

```bash
source ~/cd_vlaplan
python scripts/run_matched_modality_issue70.py
```

Progress logs show render start/completion, processor loading, every decision,
per-modality completion, semantic replay, elapsed time, and the final outcome.
Stop the backend with Ctrl-C afterwards. No GPU or concurrent torch job is used.

The current workspace already contains the completed attempt; use `--replay` here.
For a new live attempt, create successor contract/gate/authorization files with
matching new attempt/output bindings and pass `--config`, `--gate`, and
`--authorization`. Existing attempt outputs are preserved.

## Harness boundary and outcomes

Tests and the CLI call `search_episode.run_matched_modality_episode`; retained
evidence goes through `search_episode.replay_matched_modality_episode`. Each policy
receives only prompt/image messages, never replay metadata or another arm's output.
An invalid operation is charged and recorded without repair. Mismatched observations,
operation order, or completion claims cannot become a PASS.

Missing/mismatched authorization gives INVALID before execution. VALID_STOP and
ANCESTOR_STOP gates return a gated-not-run receipt without execution. Exhausted
executions retain their partial episode records and a gated-not-run receipt for
downstream work. INVALID never claims scientific completion. `execution_started`
distinguishes an attempted run from a pre-execution stop. A PASS here completes
this infrastructure demonstration only; it is not a learned-policy efficacy result.
