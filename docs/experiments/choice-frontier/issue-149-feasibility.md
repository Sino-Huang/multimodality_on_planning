# #149 feasibility note: node choice beyond imitating h_add

Written 2026-10-01, before any protocol, panel, label, training or GPU launch. It answers the #149
rule "A GPU estimate comes first". No number here is an outcome. Every figure comes from a
throwaway CPU probe of the frozen #146 runtime (`node_choice.py`, `node_choice_views.py`), the frozen
#135 seed-substitution generator (`expanded_candidates.generate`), or from closed #146 ledgers. The
probes are not evidence for any claim and are not committed.

## Facts the design rests on

### Training range (the #136 corpus, 236 tasks)

- **Objects** are fixed per generator profile (all 12 generators take object counts as arguments).
  The corpus spans 4–17 objects: compact / expanded = 15puzzle 17/17, blocksworld 4/5, depot 8/9,
  driverlog 9–10/14, elevators 4/6, ferry 4/5, grid 11/14, gripper 7/8, logistics 8/10, storage
  10/13, towers_of_hanoi 6/7, visitall 9/9.
- **Optimal plan length C\*** (Fast Downward A\*(LM-cut), all 236 tasks solved, < 1 s each): 2–15
  over the corpus; per-domain maxima 15puzzle 8, blocksworld 12, depot 10, driverlog 15, elevators 8,
  ferry 8, grid 9, gripper 10, logistics 10, storage 11, towers_of_hanoi 7, visitall 9.
- P2/P2u (#139) use the `expanded` profile and C\* 8–15, so they lie inside the training range.

### h\* is cheap on these tasks

- Fast Downward 24.06+ (`up_fast_downward` 0.5.2 wheel, GPL-3.0, called as a subprocess; not
  vendored) solves A\*(LM-cut) from a corpus state in 0.23–0.77 s wall, translator included.
- On 72 corpus menu states (6 per domain), FD h\* equals exact breadth-first distance on all 72.
- The #136 corpus has 4,128 records with 41,751 menu-state occurrences and **4,769 unique
  (task, state) pairs**. Labelling all of them takes ≈ 25 CPU-min on one core.
- Dead ends (FD exit "unsolvable") need an explicit label; none occurred in the probe.

### Larger profiles (two levels beyond training, seeds 965000–965002, an unused range)

Level arguments are scaled-up versions of the frozen strata; gripper / towers_of_hanoi keep the
legal initial-state walk, 15puzzle the goal walk.

| domain | L1 | L2 | objects L1 / L2 | C\* L1 / L2 | R_t greedy L1 / L2 | max menu greedy L2 |
|---|---|---|---|---|---|---|
| 15puzzle | `-n 3`, walk 12 | `-n 4`, walk 10 | 17 / 31 | 12 / 10 | 15–40 / 12–28 | 43 |
| blocksworld | 6 blocks | 7 blocks | 6 / 7 | 8–16 / 16–20 | 19–65 / 43–127 | 177 |
| depot | `-p3 -h2 -c3` | `-p3 -h3 -c4` | 11 / 13 | 6–12 / 12–16 | 6–26 / 18–59 | 130 |
| driverlog | `5 1 3 1` | `6 2 4 1` | 17–18 / 21–24 | 12–16 / 13–17 | 12–19 / 29–140 | 514 |
| elevators | `-f5 -p3` | `-f6 -p4` | 8 / 10 | 10–11 / 13 | 10–11 / 15–20 | 40 |
| ferry | `-l4 -c3` | `-l5 -c4` | 7 / 9 | 7–8 / 10–12 | 8–10 / 19–27 | 29 |
| grid | `4 4`, 1 key | `5 4`, 2 keys | 18 / 23 | 9–13 / 12–14 | 9–19 / 14–20 | 35 |
| gripper | `-n 6` | `-n 8` | 10 / 12 | 12–16 / 19–20 | 16–22 / 26–27 | 136 |
| logistics | `-s2 -p2` | `-c3 -s2 -p3 -t3` | 11 / 16 | 6–9 / 7–18 | 6–15 / 7–26 | 134 |
| storage | `-c3 -s6` | `-c4 -n2 -s7` | 16 / 20 | 12–13 / 16 | 88–89 / 64–69 | 313 |
| towers_of_hanoi | `-n 5` | `-n 6` | 8 / 9 | 26–31 / 63 | 66–67 / 201 | 27 |
| visitall | `-n 4 -r 0.5` | `-n 5 -r 0.5` | 16 / 25 | 9–12 / 14–17 | 28–57 / 57–125 | 208 |

- 15puzzle L1 keeps 17 objects and extends only C\*. Every other domain-level exceeds the training
  object count. At L2 every domain exceeds its own training C\* maximum on at least one probe task,
  and 8/12 domains exceed the corpus-wide maximum of 15.
- Every probe task (72) is solved by exact GBFS(h_add) and WA\*(h_add, w = 3) without a cap.
- Planimation renders the new states through the frozen live-view path at 0.08–0.39 s per state
  (three P2/P2u tasks probed); rendering is CPU and not a bottleneck.

### The overflow rule bites at larger sizes

Exact and random-valid episodes with the #146 overflow rule (`count + 384 > 32768` ends the episode),
48 tasks × 2 additive algorithms, counted with `placeholder_counter`:

| level | obs | exact overflow (of 24 per algorithm) | random-valid overflow |
|---|---|---|---|
| L1 | visual | 0 | 0 |
| L1 | text | 2 (storage) | 2 |
| L2 | visual | 1 (greedy) / 3 (w3) | 4 / 6 |
| L2 | text | 3 / 3 | 6 / 7 |

Storage text facts overflow even for the exact head at L1. Size results will therefore mix a
planning limit with a context limit; overflow must be reported per stratum and arm (as #146 did),
and the learned-heuristic arms have no context limit at all.

## Rates used for the estimate (H100, measured)

| quantity | value | source |
|---|---|---|
| model-call wall time per 1k input tokens | visual 0.80 s, text 0.65 s | #146 learned episodes, 48,155 calls binned by input tokens |
| learned eval per cell on P2 ∪ P2u (23 tasks), additive | text 0.15–0.22, multimodal 0.40–0.62 GPU-h | #146 `call_measurements` |
| training per adapter cell (4,096 samples) | text 0.8, visual 1.6 GPU-h | #146 closeout |
| eval per cell on L1 + L2 (24 + 24 tasks), one algorithm | visual 5.6 expected / 7.5 at cap; text 3.9 / 5.2 | probe token totals × rates; expected = mean(exact, random-valid), cap = random-valid |

## Proposed scope and estimate

Strata: **S0** = P2 ∪ P2u (23 tasks, in range; #139/#146 learned episodes reused), **S1** and
**S2** = 24 tasks each (2 per domain per level). Reported both by level and by C\* bin
(≤ 15 = training range, > 15).

| block | cells | expected GPU-h | at the 2R cap |
|---|---:|---:|---:|
| D1 frozen h_add adapters (#138 visual, #146 text), {greedy, w3} × {visual, text} × seeds 17/29/71 on S1 + S2 | 12 | 56.8 | 75.7 |
| D1 zero-shot base + #141 extractor, {greedy, w3} × text, one realisation, S1 + S2 | 2 | 7.7 | 10.3 |
| D2a h\*-target adapters: train greedy × {visual, text} × 3 seeds | 6 | 7.2 | 7.2 |
| D2a eval on S0 + S1 + S2 | 6 | 30.2 | 39.7 |
| D2b expert iteration: rollouts of the 6 greedy h_add adapters on the 236 corpus tasks | 6 | 18.4 | 30.0 |
| D2b train (3 seeds × {visual, text}) + eval on S0 + S1 + S2 | 6 + 6 | 37.4 | 46.9 |
| D3 CNN / ViT regressors (h\*, h_add) and pairwise rankers, 3 seeds, + panel scoring | 18 models | 6.0 | 6.0 |
| smokes (4 new adapter cells), calibration, one relaunch allowance | – | 5.0 | 5.0 |
| **subtotal** | | **168.7** | **220.8** |
| + 15 % model-load / render / journal overhead | | 194 | 254 |
| **+ program margin × 1.25** | | **~243** | **~318** |

CPU (not charged): panel generation and C\*, all exact / random-valid / GBFS(goal-count) /
GBFS(h\*)-oracle / learned-heuristic episodes, h\* labels, renders, replay and analysis.

Cheaper variants:

- **GBFS only** (drop w3 from D1, since h\*/EI/D3 are GBFS-only anyway): −28 / −38 GPU-h → ~208 /
  ~270 with margin.
- **Seed 17 only for the new adapters** (D2a, D2b): −62 / −78 → ~165 / ~220 with margin.
- Both: ~130 / ~172 with margin.

**Hardware:** gpgpu170 (2 × H100 80GB, this node, both idle; Slurm job 31351502 has ~10 days left).
The full scope at the cap is ~6.6 days on two GPUs; expected ~5 days. #147 stays on gpgpu070.

## Design choices proposed for the protocol (author may override)

1. **Primary estimand (owned here; #159 adopts it).** Per task, restricted expansions-to-goal
   `E = min(preceding expansions at goal selection, 2·R_t)`, with unsolved, invalid and overflow
   episodes set to `2·R_t`. Estimand `Δ = mean_t (E_learned,t − R_t) / R_t` on the same tasks, where
   `R_t` is the uncapped GBFS(h_add) expansion count (adapter seeds averaged per task). Negative =
   fewer expansions than GBFS(h_add). Task-cluster bootstrap `Random(133)`, 10,000 draws.
   Equivalence margin ±0.10 (10 % of R_t) for any "matches h_add" claim. **Plan length** = actions
   on the trusted parent chain from s0 to the selected goal node (the #135 `inspect_episode`
   reconstruction), reported against C\* from FD A\*(LM-cut).
2. **h\* teacher** = the menu state with minimum FD h\*; ties by the frozen κ order (h_add, then
   serial). h\* is a function of the state and goal, so unlike BFS/BFWS κ (#146) it is identifiable
   from a state-only menu in principle.
3. **Expert iteration** = one iteration. Candidates per corpus task = the 3 greedy rollouts of the
   frozen h_add adapters of the same observation type (greedy decoding, cap 2·R_t). Keep, per task,
   the solved rollout with the fewest expansions; its menu ≥ 2 decisions are the records, labelled
   with the model's own choice; ×2 menu-order augmentation, the #136 recipe, fresh LoRA. The
   policy-gradient variant is not run (optional in the ticket).
4. **Learned-heuristic driver** (shared with #158): a `StateScorer` (states → scores) chooses the
   menu label of the minimum key (ŝ for GBFS, g + 3ŝ for WA\*, ties by generation serial) through the
   frozen `ChoiceFrontierController` runtime, menus and cap. Driver episodes replay through
   `replay_node_choice_episode`. GBFS(goal count) and the GBFS(h\*) oracle anchor use the same driver.
5. **Image regressors**: input = the 128 px state scene plus the task's goal page(s); ResNet-18
   (CNN) and ViT-S/16 (timm), ImageNet-pretrained, fine-tuned; targets h\* and h_add; pairwise ranker
   = same encoders, logistic loss on within-menu pairs ordered by h\*. Trained only on the #136
   corpus menu states; model selection on held-out corpus tasks.

## Decision needed before the protocol is frozen

The author sets the GPU cap and the scope (both algorithms or GBFS only for D1; three seeds or seed
17 for the new adapters). The protocol is then frozen against that cap.
