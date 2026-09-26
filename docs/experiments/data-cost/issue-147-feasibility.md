# #147 feasibility note: matched data-cost curves for executing BFS and BFWS

Written 2026-09-26, before any protocol, panel, corpus or GPU launch. It answers the #147 rule
"A GPU estimate comes first". No number here is an outcome; all rates are measured on earlier,
already-closed runs of the same engine (`visual_model.train_visual`, Qwen3-VL-8B-Instruct rev
`0c351dd0`, LoRA r 64 / alpha 128, global batch 32, HF greedy inference).

## Measured rates used

| quantity | value | source |
|---|---|---|
| training s/op, BFS text / visual / multimodal | 1.210 / 2.127 / 2.475 | `train_runtime` / 512, `outputs/matched_modalities/{v3/training/text-state,v5/training/visual-state,v5/training/multimodal-state}/bfs/training_state.json` |
| training s/op, BFWS text / visual / multimodal | 1.143 / 1.895 / 2.233 | same files, `best_first_width` |
| model load + save per cell | ~112 s | #119 receipts (`docs/experiments/expanded-study/curriculum-training.json`) |
| evaluation s per model call (scene-only 128, trained adapters) | 5.49 | #119 evaluation `compute`: 33,105.8 s / 6,030 calls (`docs/experiments/expanded-study/curriculum-evaluation.json`) |
| panel reference decisions per task, BFS / BFWS (mean) | 82.0 / 40.6 | 24-task panel `configs/experiments/expanded-study/final-panel.json` (sum 1,969 / 974) |
| InternVL3.5-8B slowdown vs Qwen, visual / multimodal | 2.7x / 2.8x | `outputs/expanded-study/v1/second-backbone-v2/training/*/report.json` (text ~1.0x) |
| adapter size on disk (fp32 safetensors) | 667 MB | `outputs/matched_modalities/v5/training/visual-state/bfs/final/` |

Episodes stop at the first deterministic invalid operation (`termination_reason:
deterministic_invalid_operation`), so failing cells are cheap; a succeeding episode costs about one
reference trajectory of calls, and the hard ceiling is the 2x cap.

## Size ladder arithmetic

Sizes 512 ... 32,768 sum to **65,024** operations per (algorithm, observation, seed) at one epoch.
The top size alone is 50.4 % of that.

## Estimate (GPU-h, one A100 80GB = 1 GPU-h per hour)

| block | cells | training | evaluation (all-succeed / 2x-cap bound) |
|---|---|---|---|
| main grid {BFS, BFWS} x {text, visual, multimodal} x 7 sizes x seeds 17/29/71, 1 epoch, 30-task panel | 126 | 604 | 353 / 707 |
| compute-matched control (2,048 ops x 16 epochs = 32,768 samples, BFS text, seed 17) | 1 | 11 | 4 / 8 |
| untrained base on the panel (both algorithms x 3 observations) | 6 | 0 | ~1 |
| exact reference, random-valid (5 seeds), replays, sufficiency check, analysis | - | 0 | 0 (CPU) |
| model-size axis Qwen3-VL-2B + 4B at 2,048 / 8,192 / 32,768, both algorithms x 3 observations, seed 17 (8B reused from the main grid) | 36 | 126 | 48 / 96 |
| InternVL3.5-8B at 8,192, both algorithms x 3 observations, seed 17 | 6 | 60 | 34 / 68 |
| smokes, calibration, one relaunch allowance | - | ~10 | - |
| **total** | 175 | **~811** | **~440 / ~880** |

- **Expected: ~1,250 GPU-h**; with the program's x1.25 margin **~1,560 GPU-h**; if every trained
  episode ran to the 2x cap, **~1,690 GPU-h** (~2,110 with margin).
- Wall-clock on the two local A100s: **~26 days** expected, **~33 days** with margin.
- Qwen3-VL-32B ("if affordable"): the 3-size axis costs ~4x the 8B-equivalent 132 GPU-h of
  training plus evaluation, **~700 GPU-h** more. Not included.
- Node-choice comparison point (#136/#138): reused evidence, 0 GPU-h.

Known upward risks: larger training sets need larger tasks, and BFS records carry the open list,
so s/op at 16k-32k can exceed the 512-op rate; the panel must include FreeCell, Snake and Sokoban,
whose reference lengths are not in the 24-task mean. Known lever not assumed: batched vLLM LoRA
inference could cut the evaluation block several-fold, at the cost of a new inference engine.

## Non-GPU prerequisites (CPU, all variants)

1. **BFS corpus is too small.** Existing distinct BFS training operations: 12,994
   (`data/bfs_pilot_v6/materialization-report.json`). The 32,768 rung needs new exact BFS traces on
   >=20k more operations of unseen tasks. BFWS has 47,780 (`docs/issue-59-bfws-structural-gate.md`).
2. **Renders.** The unlabelled recipe (`examples/planning_benchmark_slice/scene_only_views.py`,
   `scene-only-128-unlabelled-v1`) has been materialized only for 12 domains (no Depot, Snake,
   Sokoban; `configs/experiments/matched-modalities/membership.json`). Sokoban frames are blank
   white: `outputs/modality_phase/issue72-scenes128-v1/collect-004/task-000220/frames/state-000000.png`;
   the VFG is correct and the local compositor (`scripts/planimation_phase1_frames.py` L118-124)
   paints #ffffff-tinted opaque prefabs on a white canvas. No pixel-level decision-sufficiency
   check exists yet.
3. **Panel.** 30+ unseen tasks (>=2 per domain, 15 domains) with BFS and BFWS references.

## Storage (blocking at full scale)

`/data/scratch` is 99 % full (140 GB free on 2026-09-26). 175 fp32 adapters are ~117 GB; the 2B/4B
weights add ~13 GB and 32B another ~67 GB. The full design needs either freed space or adapters
stored in bf16 (~58 GB; a declared deviation from the fp32 adapters of #112-#141).

## Decision needed before the protocol is frozen

The ticket sets no GPU cap. The full design is ~4.6x the 336 GPU-h of the whole nine-day
expanded study. The author chooses the authorized budget and the corresponding scope; the protocol
is then frozen against that cap.

## Author decision (2026-09-26, before any protocol)

- **Cap 800 GPU-h.** Scope is the main grid without the 32,768 rung: {BFS, BFWS} x {text,
  visual, multimodal} x sizes 512, 1,024, 2,048, 4,096, 8,192, 16,384 x seeds 17/29/71
  (108 cells), the controls, and one compute-matched control. Recomputed with the rates above:
  training ~302 GPU-h and evaluation ~303 GPU-h (all-succeed; ~606 at the 2x cap), so ~615 GPU-h
  expected and ~770 with the x1.25 margin.
- **Dropped by the author:** the model-size axis (Qwen3-VL-2B/4B/32B), the InternVL3.5-8B cell
  and the 32,768 rung. N90 is right-censored at 16,384 where 90 % is not reached.
- **Adapters are saved in bf16.** This is a declared deviation from the fp32 adapters of #112-#141.
- **Resumability required** (author, 2026-09-26): the host may reboot. Every stage must resume
  from its last durable state with one command: training resumes from mid-cell checkpoints,
  evaluation from per-episode journals, and the cell queue is idempotent.
- The 12,994 + 12,115 BFS operations of the 90-task #74 source corpus (train + dev tasks, disjoint
  from any panel) cover 16,384, so no new BFS traces are needed.
