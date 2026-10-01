# Node choice for all four algorithms × text / visual / multimodal — issue #146 closeout

The run followed `docs/experiments/choice-frontier/issue-146-protocol.md`. Commit order:

1. Feasibility note and author decision: `7765e34`.
2. Protocol: `e115238`. Committed before any derivation.
3. Runtime, views, runner, analyzer, tests, frozen `panels.json` and `membership.json`: `641b6b3`. Committed before any control episode or training.
4. Schedule and job files: `bbdef23`. Committed before the first launch.
5. Zero-shot token-count fix: `9ce2cfb`. Relaunch job files: `71ec023` (see Deviations).

No frozen #132–#141 file was modified. The held-out manifest and `data/curriculum_pddl/*/dev/` were never read.

## Answer

**Does learned node choice beat random-valid on held-out tasks?** It does for the three informed
algorithms, but not under every observation type:

- **Greedy h_add and w3 h_add:** POSITIVE under text, visual and multimodal.
- **BFWS:** POSITIVE under text and multimodal; INCONCLUSIVE under visual.
- **BFS:** INCONCLUSIVE under all three.

Every POSITIVE cell also passes Holm over the 12 cells.

The BFS null is a ceiling, not a learning failure. Random-valid choice already reaches M1 0.76 within 2·R_t, because R_t for uninformed FIFO search is large. κ-head agreement minus chance is ≈ 0.00 for every BFS cell. The adapter did not learn to identify the FIFO head from the state alone. Under the pre-registered state-only observation, κ_BFS is not identifiable.

**Does the text/image split reappear?** Yes, in one direction:

- Text and multimodal beat scene-only. Pooled over algorithms, D3(text) − D3(visual) = +0.250 [+0.189, +0.308] and D3(multimodal) − D3(visual) = +0.242 [+0.179, +0.302], both SEPARATED_ABOVE.
- Adding scenes to text adds nothing: text − multimodal = +0.008 [−0.030, +0.050], NOT_SEPARATED.
- Per algorithm, the split holds for greedy, w3 and BFWS and is absent for BFS.
- The text cells close most of the gap to exact on BFWS (learned − exact = −0.060 [−0.163, +0.034]). On the additive pair they close about two thirds of the random→exact gap.

## Gates (CPU, before any GPU outcome)

| gate | result |
|---|---|
| Native-prefix: node-choice κ order reproduces the native runtime | PASS on 26/26 panel and smoke tasks and on all 216 corpus teacher episodes. BFS equals `exact_fifo_bfs`; native BFWS is a prefix of the node-choice sequence; additive R_t equals the #139 values. |
| Corpus `audit-prepare` | PASS: bit-exact re-derivation, token gate, images resolve, membership re-hash, teacher-label binding, no overlap with P2/P2u, augmentation last-label check (all four algorithms within ±0.16 pp of chance). |
| Identity gate | `CHOICE_SENSITIVE` for all four algorithms. Random-valid diverges from exact on 23/23 non-trivial tasks in every observation type. |
| Additive × visual reuse | The v7 controls equal the #139 zoo on 276/276 episodes, so reusing the #136/#138 adapters and #139 episodes is valid. |
| Smoke (10 new cells, seed 17) | PASS in all 10 cells, accepted-call rate 1.000 in each. |

## Corpus

- 2,048 training and 16 diagnostic records per algorithm, ×2 menu-order augmentation, sample order pinned to `order:17`. Membership sha256 `807361bd…be65`.
- **BFS:** 55 tasks of the #136 pool. **BFWS:** 108 tasks. No derivation timeouts or render drops. No eligible decision overflowed in multimodal.
- **Additive text and multimodal:** the frozen #136 membership. 0 records were dropped for multimodal overflow.
- Maximum training input: 14,341 tokens (BFS multimodal).
- Mean menu size: BFS 20.9, BFWS 16.5, greedy 10.1, w3 10.1.

## Primary: test 1, pooled P2 ∪ P2u (23 tasks)

D3 = mean over seeds of M1(learned) − M1(random-valid). Intervals are 95 % task-cluster bootstrap (`Random(133)`, 10,000 draws).

| cell | learned M1 | random | exact | D3 [95 % CI] | seeds 17 / 29 / 71 | verdict | Holm |
|---|---:|---:|---:|---|---|---|---|
| bfs / text | 0.790 | 0.764 | 0.875 | +0.026 [−0.040, +0.087] | +0.035 / +0.029 / +0.013 | INCONCLUSIVE | no |
| bfs / visual | 0.784 | 0.767 | 0.875 | +0.017 [−0.040, +0.089] | +0.026 / +0.048 / −0.023 | INCONCLUSIVE | no |
| bfs / multimodal | 0.797 | 0.764 | 0.837 | +0.033 [−0.035, +0.113] | +0.122 / −0.030 / +0.008 | INCONCLUSIVE | no |
| best_first_width / text | 0.777 | 0.314 | 0.837 | +0.463 [+0.325, +0.600] | +0.430 / +0.452 / +0.507 | **POSITIVE** | yes |
| best_first_width / visual | 0.361 | 0.317 | 0.875 | +0.043 [−0.069, +0.162] | +0.090 / +0.041 / −0.002 | INCONCLUSIVE | no |
| best_first_width / multimodal | 0.774 | 0.314 | 0.799 | +0.459 [+0.331, +0.582] | +0.409 / +0.501 / +0.468 | **POSITIVE** | yes |
| best_first_add_greedy / text | 0.576 | 0.001 | 0.875 | +0.575 [+0.457, +0.687] | +0.597 / +0.477 / +0.651 | **POSITIVE** | yes |
| best_first_add_greedy / visual (reused #136/#138) | 0.248 | 0.001 | 0.875 | +0.247 [+0.131, +0.374] | +0.287 / +0.167 / +0.287 | **POSITIVE** | yes |
| best_first_add_greedy / multimodal | 0.556 | 0.001 | 0.875 | +0.555 [+0.424, +0.680] | +0.548 / +0.515 / +0.602 | **POSITIVE** | yes |
| best_first_add_w3 / text | 0.565 | 0.016 | 0.875 | +0.549 [+0.420, +0.674] | +0.554 / +0.565 / +0.527 | **POSITIVE** | yes |
| best_first_add_w3 / visual (reused #136/#138) | 0.322 | 0.016 | 0.875 | +0.306 [+0.175, +0.441] | +0.386 / +0.212 / +0.321 | **POSITIVE** | yes |
| best_first_add_w3 / multimodal | 0.549 | 0.016 | 0.875 | +0.533 [+0.400, +0.658] | +0.511 / +0.489 / +0.598 | **POSITIVE** | yes |

Solved within 2·R_t (learned / random / exact):

| algorithm | text | visual | multimodal |
|---|---|---|---|
| bfs | 0.83 / 0.83 / 1.00 | 0.84 / 0.84 / 1.00 | 0.86 / 0.83 / 0.96 |
| best_first_width | 0.93 / 0.44 / 0.96 | 0.54 / 0.45 / 1.00 | 0.86 / 0.44 / 0.91 |
| greedy | 0.87 / 0.01 / 1.00 | 0.42 / 0.01 / 1.00 | 0.83 / 0.01 / 1.00 |
| w3 | 0.78 / 0.04 / 1.00 | 0.46 / 0.04 / 1.00 | 0.78 / 0.04 / 1.00 |

The reused additive × visual cells reproduce #139 (P2 D3: greedy +0.364, w3 +0.468; their mean is 0.416, the #139 value).

## Test 2: per panel

The verdicts are the same on P2 (11 tasks, screened) and P2u (12 tasks, unscreened) in every cell.

- POSITIVE: all six additive cells, BFWS text, BFWS multimodal.
- INCONCLUSIVE: BFWS visual and all BFS cells.
- On P2u the additive scene-only cells are weakest (greedy +0.140 [+0.014, +0.311], w3 +0.158 [+0.029, +0.309]). This is the #139 pattern again.

## Test 3: text/image split

Learned 3-seed M1 contrast (the D3 contrast agrees within 0.004):

| algorithm | text − visual | multimodal − visual | text − multimodal |
|---|---|---|---|
| bfs | +0.005 [−0.056, +0.062] n.s. | +0.013 [−0.074, +0.100] n.s. | −0.007 [−0.069, +0.051] n.s. |
| best_first_width | +0.417 [+0.243, +0.576] **above** | +0.413 [+0.275, +0.551] **above** | +0.004 [−0.089, +0.107] n.s. |
| greedy | +0.328 [+0.237, +0.420] **above** | +0.308 [+0.192, +0.429] **above** | +0.020 [−0.058, +0.103] n.s. |
| w3 | +0.243 [+0.149, +0.348] **above** | +0.226 [+0.134, +0.330] **above** | +0.016 [−0.045, +0.074] n.s. |
| pooled (4 algorithms) | +0.248 [+0.185, +0.308] **above** | +0.240 [+0.176, +0.302] **above** | +0.008 [−0.030, +0.050] n.s. |

Comparison with the main grid (descriptive, as pre-registered). The only matched execution
contrast committed in this repo is matched-modalities v5
(`docs/experiments/matched-modalities/analysis-v5/README.md`). It has text 5/12, scene-only
visual 6/12 and multimodal 6/12 successes, on 3 problems with 1 seed, so it has no resolvable
split. I found no committed quantitative main-grid split to compare against. The node-choice result
is a resolved split favouring symbolic text over scene-only observations, with no gain from adding
scenes to text. Whether it matches the manuscript's main-grid wording is for the author to check.

## Secondary (descriptive)

- **κ-head agreement minus chance** (seeds 17 / 29 / 71, on-policy decisions with menu ≥ 2):
  - greedy text +0.29 / +0.27 / +0.24; w3 text +0.26 / +0.29 / +0.22;
  - additive visual +0.11 to +0.13;
  - BFWS text +0.09 to +0.11, BFWS multimodal +0.11 to +0.17, BFWS visual ≈ 0;
  - all BFS cells ≈ 0.
- **Zero-shot base** (with the #141 extractor), M1 and zero-shot − random:
  - greedy: text 0.40 (+0.40), multimodal 0.20, visual 0.05 (n.s.);
  - w3: text 0.34, multimodal 0.20, visual 0.03 (n.s.);
  - BFWS: text 0.78, multimodal 0.77, visual 0.45;
  - BFS: 0.88–0.96.
- **Learned − zero-shot:**
  - Positive for every additive cell. Examples: greedy multimodal +0.355 [+0.174, +0.511], greedy text +0.174 [+0.007, +0.322].
  - ≈ 0 for BFWS text and multimodal (+0.000 / +0.002). The zero-shot base already picks good BFWS nodes from text facts, so BFWS training adds no measurable gain over zero-shot.
  - Negative for BFS text (−0.167 [−0.283, −0.065]). The base model's "closest to the goal" heuristic beats FIFO imitation within 2·R_t.
- **Validity:** 1 invalid-output termination among 690 learned episodes (BFS text). Zero-shot had 0 invalid terminations after extraction.
- **Overflow (learned episodes):** BFS multimodal 8, BFWS text 4, BFWS multimodal 2, BFS text 2, BFS visual 2, BFWS visual 1, additive 0. Exact overflowed on 3 (task, algorithm) pairs (15-puzzle P2 955075 BFWS, P2u 955002 BFS / BFWS).
- **Sensitivity (exact-overflow pairs excluded):** every test-1 verdict and every test-3 verdict is unchanged. BFWS text rises to +0.494; BFWS visual becomes −0.004.

## Coverage and replay

| block | episodes | independently replayed | missing | mismatch |
|---|---:|---:|---:|---:|
| CPU controls (exact + 5 random-valid seeds × 12 cells × 23 tasks) | 1,656 | 1,656 | 0 | 0 |
| learned, 30 new cells × 23 tasks | 690 | 690 | 0 | 0 |
| zero-shot, 12 cells × 23 tasks | 276 | 276 | 0 | 0 |
| reused #139 additive × visual learned (3 seeds × 2 algorithms × 23 tasks) | 138 | replayed in #139 (0 mismatch) | 0 | — |

## Budget (ledger `outputs/choice-frontier/v7/budget.json`, cap 400 GPU-h)

| attempt | GPU | MASTER_PORT | status | GPU-h |
|---|---|---|---|---:|
| cfv7-worker-gpu0 #1 | 0 | 18870 | stopped by operator (SIGTERM; see Deviations) | 77.69 |
| cfv7-worker-gpu1 #1 | 1 | 18871 | stopped by operator (SIGTERM; see Deviations) | 77.69 |
| cfv7-worker-gpu0 #2 | 0 | 18870 | stopped by operator once its queue was empty | 12.70 |
| cfv7-worker-gpu1 #2 | 1 | 18871 | succeeded | 13.56 |
| **total** | | | | **181.64** |

- Of this, training was 40.6 GPU-h of wall time over 30 cells: text 0.8 h, visual 1.6 h and multimodal 2.4 h per BFS cell.
- Learned inference averaged 7.5 s per call over 48,155 calls.
- Pre-launch estimate: ~227 GPU-h expected, ~325 at the 2R cap. Hardware: 2 × H100 80GB on spartan-gpgpu170. Render backends ran on ports 18878, 18879 and 18880.
- Failed and superseded work is included in the total.

## Deviations

1. **Zero-shot token count (`9ce2cfb`).** The zero-shot arm appends the #141 format sentence to the system message. The first runner counted tokens without that sentence. The overflow rule (protocol §2, "complete input token count") and the single-input batch-cap switch therefore saw a count that was too low. On BFS multimodal driverlog-955002, a ~30k-token input crossed the 24,000 padded-batch cap undetected, and `VisualPolicy` refused the call (`VALID_STOP`).
   - Fix: the counter and the observation binding now include the system message the model actually receives.
   - Learned episodes were unaffected: their system message is the counted one, and 690/690 replay.
   - Both workers were stopped (SIGTERM, recorded as `failed`). The 67 pre-fix zero-shot episodes and the failure record were moved to `outputs/choice-frontier/v7/superseded/zeroshot-pre-fix/`. All 276 zero-shot episodes were rerun from scratch.
   - No outcome was inspected before the fix. The trigger was a runtime refusal, and no rule changed.
2. **Idle worker stopped.** Once only one slot remained, the GPU0 worker of attempt 2 was polling and charging idle time, so it was stopped (12.7 GPU-h recorded).

## Limitations

- **BFS under state-only observation measures a ceiling.** Within 2·R_t, random-valid choice already solves 83 % of BFS episodes. Because κ_BFS (the generation serial) is not in the observation, imitation learns nothing about the head (agreement ≈ chance). "Node choice is learnable for BFS" is therefore not tested in a way that could pass. A depth-annotated variant would be a different, leakier contract (feasibility note, question 2).
- **Scene-only BFWS fails where text succeeds.** The BFWS key ⟨w, #g, g, σ⟩ depends on #g, which the text facts expose directly. The 128 px scenes evidently do not convey it to the adapter, since κ-head agreement minus chance is ≈ 0 under visual.
- **One backbone (Qwen3-VL-8B).** The InternVL axis (#143) is not covered.
- **Panels.** P2/P2u keep their #139 additive screen. For BFS and BFWS, P2 is not "screened" in any algorithm-specific sense.
- **Zero-shot is one realisation** (seed 17), with the #141 extractor applied.

## Evidence index (sha256, first 16)

| file | sha256 |
|---|---|
| `configs/experiments/choice-frontier-v7/protocol.json` | `f33f29e9e7515db0` |
| `configs/experiments/choice-frontier-v7/panels.json` | `7fe5094228507bcb` |
| `configs/experiments/choice-frontier-v7/membership.json` | `5952b477a65e18c1` |
| `outputs/choice-frontier/v7/preparation/report.json` | `4d53331d30695e2b` |
| `outputs/choice-frontier/v7/preparation/audit.json` | `0efff86e31d1f66d` |
| `outputs/choice-frontier/v7/controls/receipt.json` | `a6e97b4b46315f4f` |
| `outputs/choice-frontier/v7/controls/identity-gate.json` | `155bded27a866293` |
| `outputs/choice-frontier/v7/evaluation-finalize.json` | `975528920bf37fb4` |
| `outputs/choice-frontier/v7/metrics/analysis.json` | `0b1c9722da829eca` |
| `outputs/choice-frontier/v7/budget.json` | `a7495b38716635c6` |

Run outputs under `outputs/` are git-ignored, as in #135–#141.

Reproduce the analysis with `source ~/cd_vlaplan && python scripts/analyze_choice_frontier_v7.py`. Replay with `python scripts/run_choice_frontier_v7.py finalize`.
