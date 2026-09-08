# Readable-view panel with a 32K ceiling

The user authorized whole-instance exclusions when the readable inputs exceed
32K. `views-panel-32k-v2.json` records the measured successor to the original
241-task panel. `views-contract-v2.json` binds its selected counts to the page
contract. Original scenes, source traces, corpus releases, v1 contracts and
receipts remain available.

The completed selection measured all **241 tasks / 78,230 decisions** in
337.4 seconds with four workers. It retains **238 tasks, 49,274 states and
76,217 decisions**. The largest retained input is **23,379 tokens**.

The excluded tasks are all three BFWS hard Visitall tasks in the parent panel:

| Instance | Source split | Maximum input tokens |
| --- | --- | ---: |
| visitall-train-hard-0007 | dev | 49,847 |
| visitall-train-hard-0013 | train | 49,963 |
| visitall-train-hard-0047 | train | 49,896 |

The selected dry-run passes all 238 task groups. All parent BFS tasks and
additive pairs remain selected; BFWS loses its hard Visitall stratum. See
`docs/experiments/issue72/views-32k-selection-summary.json` for retained evidence.

A task stays only if **every decision in all three modalities** uses at most
**32,384 input tokens** (32,768 total minus the existing 384 output-token reserve).
One overflowing decision excludes the complete task in text-state, visual-state
and multimodal-state. Both additive settings enter and leave as a pair. The
rule uses processor input size, with no model outcomes or training results.

The selector measures every parent decision with the frozen Qwen processor and
existing family chat builders. It stores per-decision page/token bindings and
records every exclusion as `VALID_STOP`. It produces no annotation previews or
scene copies and makes no model inference calls. This token-selection stage
alone does not establish readability or goal-checker qualification.

## Alignment with BFS and BFWS

The source BFS and BFWS releases both use semantic whole-instance splits,
16 accepted Search Memory deltas, and 384 output tokens. BFS has an 8,192 total
context; BFWS has 7,808 input plus 384 output tokens. The new readable views can
need a larger context, while preserving the source task identity, original
train/dev assignment, complete trace order, teacher operations, candidate
information and bounded Search Memory.

The selected rows are unchanged rows from the #71 source panel. No task is
reassigned between train and dev; no decisions are removed from retained tasks.
BFS and BFWS retain their own source task sets. The new text/visual/multimodal
comparison uses the same retained task set within each algorithm. Historical
8K training results describe their original releases; matched successor runs
must use this panel for the text baseline as well.

The panel reports selected/excluded strata by algorithm, split, domain and
difficulty, together with decision counts and exact overflow measurements.
This makes any loss of hard-task coverage explicit.

## Retained qualification and materialization commands

```bash
source ~/cd_vlaplan
python scripts/prepare_modality_views.py --dry-run --workers 4 \
  --panel configs/experiments/issue72/views-panel-32k-v2.json
python scripts/prepare_modality_views.py --qualify --workers 4 \
  --panel configs/experiments/issue72/views-panel-32k-v2.json \
  --output outputs/modality_views/qualify-32k-v2-001
```

The full qualification and materialization passed for all retained states and
decisions. `views-approval-v2.json` records the explicit human readability,
32K-context and materialization approval. The final read-only check also passed;
#72 is closed. The commands above are retained for provenance, not a request to
overwrite these completed attempts.

The completed materialization used the matching qualification and human approval:

```bash
python scripts/prepare_modality_views.py --materialize --workers 4 \
  --panel configs/experiments/issue72/views-panel-32k-v2.json \
  --qualification outputs/modality_views/qualify-32k-v2-001/report.json \
  --approval configs/experiments/issue72/views-approval-v2.json \
  --output outputs/modality_views/materialize-32k-v2-001
python scripts/prepare_modality_views.py --check --workers 4 \
  --panel configs/experiments/issue72/views-panel-32k-v2.json \
  --qualification outputs/modality_views/qualify-32k-v2-001/report.json \
  --approval configs/experiments/issue72/views-approval-v2.json \
  --output outputs/modality_views/materialize-32k-v2-001
```

Interrupted materialization can resume with the same arguments and `--resume`.
The panel's measured counts govern completeness in qualification,
materialization, checks and `ModalityViewStore`. Omitting `--panel` retains the
original v1 behavior. #73/#74 own corpus releases; training and GPU throughput
qualification remain separate downstream prerequisites.

## Reproduce the selection in a fresh attempt

```bash
python scripts/select_modality_view_panel.py --workers 4 \
  --output outputs/modality_views/select-32k-002 \
  --panel-output outputs/modality_views/select-32k-002/panel.json
```

The existing tracked panel does not change automatically. Selection errors or
incomplete parent/modality/decision coverage cannot produce a complete panel.
