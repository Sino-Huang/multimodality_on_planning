# #146 feasibility note: node choice for all four algorithms × text / visual / multimodal

Written 2026-09-27, before any protocol, corpus, panel reference or GPU launch. It answers the
#146 rule "Needs a new GPU authorization window (not yet estimated)". No number here is an outcome.
Rates come from closed runs of the same engine (`visual_model.train_visual` / `VisualPolicy`,
Qwen3-VL-8B-Instruct rev `0c351dd0`, LoRA r 64 / alpha 128, global batch 32, HF greedy inference,
2 × A100 80GB). Reference expansions for BFS and BFWS come from a throwaway CPU probe of the proposed
node-choice runtime on the frozen #139 panels; the frozen runtime will recompute them.

## Measured rates used

| quantity | value | source |
|---|---|---|
| training GPU-h per cell, visual additive node choice (2,048 records × 2 augmentations = 4,096 samples, 128 updates) | 1.89–1.94 | `outputs/choice-frontier/v3/budget.json`, `outputs/choice-frontier/v4/budget.json` (#136/#138 train attempts) |
| evaluation s per model call, visual additive node choice (menus ≤ ~40 scenes) | 5.1 (4.3–5.5) | #139 panel jobs: 18,418 s / 3,584 calls (`outputs/choice-frontier/v4/budget.json`, `outputs/choice-frontier/v4/panels/*/evaluation/episodes`) |
| tokens per 128 px scene / per static or goal page (`PAGE_SIZE`) | 64 / 768 | `frozen_processor().image_tokens_for_size` |
| tokens per menu label `Page role: frontier-choice (label c123)` | 12 | Qwen3-VL tokenizer |
| tokens per state as a canonical atom list (panel tasks) | 18–93 | Qwen3-VL tokenizer on P2 initial states |

## Reference expansions on the frozen panels (CPU probe)

R = expansions of the uncapped exact node-choice episode (always select the κ_A head, goal test at
selection). Additive R is the frozen #139 value.

| panel | tasks | ΣR greedy | ΣR w3 | ΣR BFS | ΣR BFWS | max R BFS / BFWS | max menu BFS / BFWS |
|---|---:|---:|---:|---:|---:|---:|---:|
| P2 | 11 | 197 | 183 | 1,340 | 839 | 327 / 428 | 163 / 303 |
| P2u | 12 | 148 | 150 | 2,132 | 743 | 459 / 301 | 186 / 213 |

Every P2/P2u task is solved by exact BFS and exact BFWS. BFS needs 7.7× and BFWS 3.5× the additive
expansions, and their menus are up to ~10× longer. Evaluation, not training, dominates the cost.

## Contract questions the protocol must freeze

1. **Runtime.** One node-choice contract for all four algorithms. The runtime generates and admits
   every successor of the chosen node with the algorithm's own rules. BFS: FIFO key = generation
   serial, duplicates = generated set. BFWS: ⟨w, #g, g, σ⟩ computed at generation (novelty tables
   per #g, precision 2, unpruned). Additive: the frozen `ChoiceFrontierController`, unchanged.
   Goal test at selection for all four. This deviates from native BFWS, which tests at generation.
   Gate: the exact node-choice expansion sequence must have the native exact expansion sequence as a
   prefix on every task.
2. **What BFS and BFWS node choice means.** Proposed: every menu node carries only its state in
   every observation type (no depth, serial, score, novelty or history), as in #132. Then κ is not
   fully identifiable from the observation:

   | algorithm | key | identifiable from menu + initial state + goal |
   |---|---|---|
   | BFS | serial | no; depth is only approximately inferable from the state |
   | BFWS | ⟨w, #g, g, σ⟩ | #g yes; w depends on search history; g and σ no |
   | greedy | h_add | yes in principle |
   | w3 | g + 3 h_add | h_add yes, g no |

   The primary question stays well posed: does learned node choice beat random-valid on held-out
   tasks within 2 R? The alternative is to add each node's depth g to every observation type, which
   makes the BFS head nearly identifiable but also leaks a search value.
3. **Text encoding.** A node's canonical atom (+ fluent) list. The initial state, goal atoms and
   objects are given as text. Visual follows #132. Multimodal gives both.
4. **Overflow.** Long menus overflow 32K tokens in all three types. Examples: 303 scenes × 76 tokens
   plus pages, or 303 × ~95 text tokens on 15-puzzle BFWS. Proposed rule for all arms, controls
   included: an episode ends at the first decision whose observation would overflow under its
   observation type, and the task counts as unsolved from there. Control arms are then specific to
   the observation type, and overflow counts are reported.
5. **Reuse.** The additive × visual cells use the frozen `visual-choice-frontier-v1` contract, so
   the #136/#138 adapters (seeds 17/29/71), the #139 P2/P2u learned episodes and zoo, and the #141
   P2 zero-shot episodes are reused (0 GPU-h). This requires that no reused control episode meets
   the overflow rule, which will be checked.
6. **Panels.** The frozen P2 (11 tasks) and P2u (12) memberships are reused. The new algorithms get
   new R_t. "Screened" keeps meaning the #139 additive random-control screen; no new screen is run
   per algorithm.
7. **Corpus.** The #136 training-task pool (seeds 945000–945099, all disjoint from P2/P2u by the
   #139 exclusion rule) and the #136 walk, eligibility and x2 augmentation. BFS and BFWS scene
   catalogs are new renders (CPU, planimation backend). The additive text/multimodal cells reuse the
   #136 membership with new serializations.

## Estimate (GPU-h at A100 rates)

Evaluation is bounded by 2 R calls per episode. BFS/BFWS calls are costed at 7 s because their
menus are longer; this is an extrapolation, and the smoke gate calibrates it.

| block | cells | at the 2R cap | expected |
|---|---:|---:|---:|
| training: {BFS, BFWS} × 3 obs × 3 seeds + additive × {text, multimodal} × 3 seeds, 2.3 GPU-h each | 30 | 69 | 69 |
| learned eval, P2 + P2u: BFS 13.5, BFWS 6.2, greedy 1.0, w3 0.9 GPU-h per cell (visual additive reused) | 30 | 188 | ~122 (65 %) |
| zero-shot base (#141 extractor, 2R cap, one realisation), 4 algorithms × 3 obs | 12 | 65 | ~32 (50 %) |
| smokes, calibration, one relaunch allowance | – | 3 | 3 |
| **total** | | **~325** | **~227** |

- **Expected ~227 GPU-h, ~285 with the program's ×1.25 margin; ~406 with margin if every episode
  runs to the 2R cap.**
- Seed 17 only (the #136 precedent): ~98 expected, ~153 at the cap (before margin).
- CPU (not charged): exact / random-valid (5 seeds) / identity gate on every (task, algorithm, obs),
  corpus derivation and renders, independent replay, analysis.
- Storage: 30 fp32 adapters ≈ 20 GB (≈ 10 GB in bf16); `/data/scratch` had 144 TB free on
  2026-09-27.

## Hardware and schedule conflict

- #147 is running on `spartan-gpgpu137` (2 × A100, both busy). That Slurm allocation has
  ~1.5 days left, and #147 needs ~26 days.
- `spartan-gpgpu170` (2 × H100 80GB PCIe, idle) has ~13.9 days left.
- At the A100 rates above, #146 needs ~5–7 days on two GPUs, and H100s should be faster. It fits on
  gpgpu170 now, but it would then compete with a #147 relaunch there after gpgpu137 expires.

## Decision needed before the protocol is frozen

The author sets the cap, the scope (seeds, panels, zero-shot arm), the BFS/BFWS node-choice
definition (question 2) and where the work runs relative to #147. The protocol is then frozen
against that cap.

## Author decision (2026-09-27, before any protocol)

- **Cap 400 GPU-h. Full scope:** four algorithms × {text, visual, multimodal} × training seeds
  17/29/71 on P2 and P2u. Arms: learned, random-valid, exact and zero-shot base. The additive ×
  visual cells are reused from #136–#141.
- **Node choice observes the state only** (question 2, as #132). No depth, serial, score, novelty
  or history appears in any observation type.
- **Hardware:** run now on `spartan-gpgpu170` (2 × H100 80GB PCIe). #147 stays on its own node.
