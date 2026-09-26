# Figure spec for storyline v2 (FigureDesign, read-only review)

Paths: E/ is the evidence repo and M/ is the manuscript. Every number below was read from an E/ file during this review. Values marked **[computed]** are my own counts from the episode files; the generating script must recompute and assert them.

## 0. Verdict up front
- **Keep the contract's a/b/c teaser.** Intro L12, L22, L35 and Results L105 already cite Fig. 1a, 1b and 1c, so the order is fixed.
- Two panels need changes:
  - **(a)** should show a real trace, not a generic schematic.
  - **(b)** must not look like a learning curve, and must not suggest the comparison is matched.
- **One claim-level problem, severity high.** At 512 records, all 72 BFWS failures are *malformed first operations*, not bookkeeping errors. The "bookkeeping" reading only fits BFS. See §4, risk R1. Figures Q2 and fig:contracts must show this truthfully.
- **fig:contracts:** drop the choice-frontier panel. Replace it with a three-column "what one valid step contains" panel (BFS / BFWS / additive) on the same ferry task used in Fig. 1a. Draw it at true size, 5.5×2.35 in. That saves about 0.8 in of height against the current 3.15 in.
- **Qualitative figures:** use one running task, `blocksworld-expanded-911101`. It is the task nominated in issue #145, and the unused `fig_enumeration_example.py` already uses it. Make three appendix figures: solved / failures / corruption.
- **`sec:results-qualitative`:** don't add a subsection. Replace one sentence in Results L85 instead (§2.4).

---
## 1. Teaser Fig. 1 (`fig:teaser`, 5.5 × 1.85 in at true size; with a caption of 55 words it takes about 0.28 page)

**Purpose.** In one glance: we supervise the search trace rather than the plan; BFS and BFWS cost far more data than the additive variants; and the learned controllers read the text channel.

**Layout (inches, figure coordinates).**
- **(a)** x 0.05–2.20.
- **(b)** x 2.30–4.15. Two inset axes with a broken x-axis.
- **(c)** x 4.25–5.45. Row labels take 4.25–4.62; the plot takes 4.62–5.45.
- Plot areas span y 0.38–1.45.
- Panel headers sit at y 1.80: letter plus title in 7.5 pt bold, subheader in 6.2 pt muted. The minimum font size anywhere is 6 pt.
- Style: keep the `_style.py` conventions. Add an `ALGO_STYLE` dict with Okabe–Ito colours: bfs #0072B2, best_first_width #009E73, best_first_add_w3 #E69F00, best_first_add_greedy #D55E00. Random-valid stays `ARM_STYLE["random_valid"]`, a hollow grey circle.

### (a) "Trace, not plan". Subheader: "one operation per model call"

**Data source**
- Episode: `E/outputs/expanded-study/v1/baseline/episodes/text-state/expanded-final__ferry-compact-915000/best_first_add_greedy-exact_reference.json.gz`, fields `events[].raw_output` and `events[].input.{current.{state_id,h},successor_candidates.rows}`.
- This task is in the test split (manifest `split`). Never call its trace "training data".

**Drawing**
- **Left: the scene.** Draw `E/outputs/expanded-study/v1/panel-v2/views/ferry-compact-915000/unlabelled/state-000000.png` at 0.55 in with nearest-neighbour scaling. This is the scene the policy sees; the recipe is `scene-only-128-unlabelled-v1`.
  - Add vector labels l0 / l1 / l2 *under* the image. Place them at the three purple column spans detected in the PNG, and assert exactly three spans.
  - Add the vector text "goal: at(c0,l1)".
  - Do not use `scenes/frames/state-000000.png`. That frame has baked-in labels and is not what the policy sees.
- **Right: a vertical spine.**
  - The spine is the plan path s0 → s2 → s3 → s5 → goal. Put each node's h_add beside it: 3, 3, 2, 1, 0.
  - Plan edges are bold, labelled with the action and its trace number:
    - 2 sail(l1,l2)
    - 3 board(c0,l2)
    - 8 sail(l2,l1)
    - 9 debark(c0,l1)
  - The other operations are grey stubs, two per level:
    - s0: 1 sail(l1,l0)
    - s2: 4 sail(l2,l0), 5 sail(l2,l1)
    - s3: 6 debark(c0,l2), 7 sail(l2,l0)
    - s5: 10 sail(l1,l0), 11 sail(l1,l2)
  - Draw the numbers inside small circle patches. Don't rely on circled-digit glyphs.
- **Bottom legend, 6 pt:** "bold: plan target (4 actions) · all 11 numbered steps: trace target".

**Script must assert**
- Result: goal_reached; decision_count 11; expansion_count 4.
- Manifest `reference_costs.best_first_add_greedy == {decisions: 11, expansions: 4}` and `task_context.canonical_goal == ["atom","at",["c0","l1"]]`.
- Backtrack the plan from the goal through source_state_id and candidate target ids, and assert it equals `scenes/catalog.json.gz path_bindings[1].supplied_actions` = (sail l1 l2)(board c0 l2)(sail l2 l1)(debark c0 l1).
- Assert the 0-based plan indices in the trace are [1, 2, 7, 8] and the h sequence of expanded states is [3, 3, 2, 1].
- The scene is 128×128. The visual-state episode's events[0].view has `state_representation == "scene-only-128-unlabelled-v1"` and includes the page ['current-state', 0, 0].
- Optional, and only if the caption says "the trained adapter reproduces it": assert that the greedy `process_sft` raw outputs equal the exact-reference outputs in all three observation types. **[computed: True for text, visual and multimodal.]**

### (b) "Data cost". Subheader, one 6 pt line: "filled: 512-record grid · hollow: development runs · ○ random-valid"

**Encoding**
- **Broken x-axis.** Draw break marks (//) between the two blocks, and put no connecting lines between points. Lines would imply a learning curve on one panel.
- **Left block, ax_b1 (x 2.50–3.00):** a categorical column with tick "512" and header "main grid · 24 tasks". The four algorithms are dodged horizontally in fixed slots (BFS, BFWS, WA*, GBF), each labelled under the axis in 6 pt.
- **Right block, ax_b2 (x 3.07–4.10):** log x from 9k to 60k, ticks 10k / 20k / 50k, header "development runs · own panels".
- **Shared y:** "success rate", from 0 to 1.05, ticks 0 / 0.5 / 1.
- **Trained adapters are squares** (ARM_STYLE adapter marker), coloured by algorithm. Main grid = filled; development run = hollow; the visual development run uses a hollow triangle so it can be told apart from the text run it overlaps at y = 1.
- Every point gets a random-valid ring at the same x.
- Direct labels:
  - "BFS text 13.0k / visual 11.9k" above the BFS pair
  - "BFWS text 47.8k" and "BFWS visual 14.2k" beside those points

**Series.** Main grid source: `E/docs/experiments/expanded-study/synthesis-v1/baseline-summary.csv`, columns `successes` and `episodes`. Pooled over the three observation types, with min–max whiskers across them.

| point | x (records) | y (SFT) | whisker | ring (random-valid) | source |
|---|---|---|---|---|---|
| BFS grid | 512 | 0/72 = 0.000 | 0–0 | 15/24 = 0.625 | baseline-summary.csv `process_sft`, `random_valid` |
| BFWS grid | 512 | 0/72 = 0.000 | 0–0 | 17/24 = 0.708 | same |
| WA* grid | 512 | 60/72 = 0.833 (20/18/22) | 0.750–0.917 | 1.000 | same |
| GBF grid | 512 | 65/72 = 0.903 (22/22/21) | 0.875–0.917 | 1.000 | same |
| BFS text dev | 12,994 | 1.000 | – | 1.000 | x: `E/data/bfs_pilot_v6/ms-swift-process/manifest.json` counts.train; y and ring: `E/docs/experiments/deadline-study/prior-evidence.json` historical_bfs_stages[stage=="v8"].metrics.{process_sft,random_valid}_invariant_valid_success; selected_tasks 15 |
| BFWS text dev | 47,780 | 0.933 | – | 0.467 | x: `E/data/bfws_phase_v1/corpus-release/training/manifest.json` counts.train; y and ring: `E/data/bfws_phase_v1/issue59-distributed-terminal/adjudication-report.json` {process_sft,random_valid}_invariant_valid_success; len(coverage.task_ids) 15; outcome PASS |
| BFS visual dev | 11,911 | 1.000 | – | 0.707 | x: `E/outputs/visual_development/issue75-32k-v5/attempt-001/training.json` training_runs[bfs].train_records; y and ring: prior-evidence.json issue75.metrics.bfs.invariant_valid_success.{process_sft,random_valid} |
| BFWS visual dev | 14,225 | 0.667 | – | 0.520 | same files, best_first_width |

**Deliberately left out of the figure; state this in the script comment.**
- The additive points from run #75: 9,398 and 8,342 records, each 1.0 with random-valid 1.0. They are saturated, they say nothing about the BFS/BFWS data cost, and they would crowd the BFS pair. They stay in `tab:results-main`.
- The text runs #65/#66: no record count is stated, so there is no x value.
- InternVL.

**Script must assert**
- All 48 rows of baseline-summary.csv match contract table §4. Pooled values and whiskers match at 3 dp.
- Every development value above matches at 3 dp. The record counts match exactly.
- min(dev records)/512 > 10. The derived ratio is 23.3.
- The episode counts behind each development point: 15 tasks for BFS text, 15 tasks for BFWS text, and 75 episodes for each #75 point (15 tasks × 5 evaluation seeds).

### (c) "Which channel is read". Footnote, 6 pt: "additive adapters · 9 tasks × 2 algorithms · 95% intervals"

**Encoding.** A forest plot. The x-axis is "change in success", from −1.05 to +0.05, ticks −1 / −0.5 / 0, with a dashed zero line. Ink-coloured filled circles with horizontal CI lines. Four rows under two bold group headers.

**Source:** `E/outputs/expanded-study/v1/modality-stress/analysis.json` → `contrasts.degradation_by_family_modality[group].{mean_degradation, degradation_interval_95.low, .high}`

| group header | row label | group key(s) | Δ | 95% interval |
|---|---|---|---|---|
| shuffled text | text | text-shuffled__text-state | −0.944 | [−1.000, −0.833] |
| shuffled text | multimodal | text-shuffled__multimodal-state | −0.722 | [−0.889, −0.500] |
| blanked or degraded images | visual | visual-blank__visual-state ≡ visual-degraded__visual-state | −0.056 | [−0.167, 0.000] |
| blanked or degraded images | multimodal | visual-blank__multimodal-state ≡ visual-degraded__multimodal-state | −0.111 | [−0.278, 0.000] |

- **Merging blank and degraded is exact.** Outcomes are identical in all 36 of 36 paired cells **[computed; the script asserts it from `cells[]`]**.
- **Text masking is not plotted.** It destroys the output format; see `tab:results-corruption`. The channel claim rests on shuffling.

**Script must assert**
- tasks == 9, cells == 18, and descriptive_only False for every plotted group.
- The four Δ values and eight interval endpoints match at 3 dp.
- Every image-corruption interval has high == 0.0.
- max |Δ| over image rows == 0.111, and |Δ| for text-shuffled text == 0.944. These are the abstract's "up to 0.94" and "at most 0.11".

### Caption draft (55 words)
`\textbf{Learning to execute search from traces.} (a)~On this ferry task the plan has 4 actions (bold); greedy best-first search takes 11 operations, and we train on such operations, one step per record. (b)~Hollow markers are larger development runs on their own panels, not a matched comparison. (c)~Change in success under test-time corruption, with 95\% intervals.`

Evidence comments must cite every path listed above. **Appendix owner:** the scene-provenance paragraph at `appendix.tex` L503 still describes the old choice-frontier teaser scenes and must be rewritten.

### Alternatives considered
- **A two-panel teaser without (a):** rejected. Intro L12 cites Fig. 1a for "rather than on their plans", and plan-vs-trace is the hook for ICAPS readers.
- **A continuous log axis for (b)** with the 512 points dodged: rejected. The broken axis does a better job of stopping readers from interpolating a curve.
- **Fallback, if the author feels any shared y-axis implies comparability:** make (b) four bars of 512-record success, with random-valid ticks, plus two text callouts: "BFS 1.00 / BFWS 0.93 with 13.0k / 47.8k records on 15-task development panels (random-valid 1.00 / 0.47)". This is more honest still, but it loses the visual sense of the order of magnitude.

---
## 2. Qualitative figures (appendix `app:qualitative`): new `qualitative_figures.tex`

**Running task:** `expanded-final/blocksworld-expanded-911101`, five blocks, goal on(b2,b4) ∧ on(b3,b5) ∧ on(b4,b3).

**Selection rule to state in the tex comment:**
- The task is the one nominated in issue #145 (see the `fig_enumeration_example.py` docstring).
- Each figure shows the complete set of arms and observation types for that task, and the first decision at which the behaviour of interest occurs.
- I inspected outcomes during this review, so do *not* call the selection pre-registered. Call it illustrative, and back it with the aggregate counts below.

**Scenes:** cached policy PNGs from `E/outputs/expanded-study/v1/panel-v2/views/blocksworld-expanded-911101/unlabelled/state-{idx:06d}.png`. Take idx from `events[i].view.input_pages` ['current-state', idx, 0] and assert that `scenes/catalog.json.gz states[idx].atoms` match the event's state. Enlarge with nearest-neighbour scaling and never re-render. That avoids the re-render checks the old filmstrips needed.

**Label and file names must not collide** with the old figures, which keep `fig:qualitative-{success,decision,failure}` and `fig_qualitative_*.pdf` in `qualitative_figures_choice_frontier.tex`. New names:
- `fig:qual-trace-solved` / `fig_qual_trace_solved.{py,pdf}`
- `fig:qual-trace-failures` / `fig_qual_trace_failures`
- `fig:qual-trace-corruption` / `fig_qual_trace_corruption`

Q1 subsumes panel A of `fig_enumeration_example.{py,png,svg,pdf}`, so delete those files after cutover. Its panel B, the base emitting `h_add("s1")` as its first output, can become an optional footnote strip in Q1.

### Q1 `fig:qual-trace-solved` (5.5 × 2.6 in)

**Purpose.** Show what a learned heuristic best-first step looks like: the adapter sees a rendered scene plus textual candidate rows whose h_add values are computed by the runtime, submits every candidate, and the runtime's heap does the ordering.

**Episode:** `E/outputs/expanded-study/v1/baseline/episodes/visual-state/expanded-final__blocksworld-expanded-911101/best_first_add_greedy-process_sft.json.gz`, checkpoint `outputs/matched_modalities/v5/training/visual-state/best_first_add_greedy/final`.

**Drawing**
- **Top: a filmstrip** of the expanded states s0, s1, s3, s6, s9, s11 and the goal s13, labelled with h_add 8, 8, 5, 5, 2, 1, 0. Values come from `events[].input.current.h`; the goal's 0 is its candidate row.
- **Bottom-left:** the s6 scene, catalog idx 8.
- **Bottom-middle:** the candidate rows at events[8], verbatim in their columns:
  - putdown(b4): g 4, h 4, priority 4, s7
  - stack(b4,b1): 4, 4, 4, s8
  - stack(b4,b2): 5, closed/pruned, s3
  - stack(b4,b3): 4, 2, 2, s9
- **Bottom-right:** the four emitted operations, events[8..11] raw_output verbatim, then "runtime heap expands s9 (h_add 2) next".

**Assert**
- goal_reached; decisions 18; expansions 6.
- raw outputs == `best_first_add_greedy-exact_reference.json.gz` raw outputs. **[computed True for visual and text; multimodal solves with a different valid submission order, so don't claim it for multimodal.]**
- The expanded h sequence and the rows above; events[12].input.current.state_id == "s9".

**Caption (56 words):** `\textbf{A trained greedy best-first adapter reproduces the reference search on a five-block task.} Top: the six states the runtime expanded, with their $h_{\mathrm{add}}$, and the goal. Bottom: one expansion as the visual-observation adapter sees it, a rendered scene plus textual candidate rows with runtime-computed values, and the four operations it emits. Illustrative, not an efficacy estimate.`

### Q2 `fig:qual-trace-failures` (5.5 × 2.4 in; two columns)

**Purpose.** Show *how* the 512-record BFS and BFWS adapters fail.

**Left, BFS**
- Source: `…/{text,visual,multimodal}-state/expanded-final__blocksworld-expanded-911101/bfs-process_sft.json.gz` events[2], compared with `bfs-exact_reference.json.gz` events[2]. Events 0–1 were accepted.
- Show:
  - the head scene, `unlabelled/state-000001.png` (b1 held)
  - frontier_size 2
  - the candidates: putdown(b1) unvisited, stack(b1,b3) unvisited, stack(b1,b4) visited
  - the adapter's emission: putdown(b1), retire_source **false**, target_position **2**
  - the reference: putdown(b1), retire_source **true**, target_position **1**
- Put the differing fields in orange. Note that the emission is identical in all three observation types.
- Context line: on this task the exact reference solves in 143 decisions, and random-valid runs out of budget at 145.

**Right, BFWS**
- Source: `best_first_width-process_sft.json.gz` events[0] in each observation type, compared with the exact reference events[0].
- Show:
  - the candidate's `eval.frontier = {retire_source: true, target_position: 0}`, which only needed copying
  - the reference record {action unstack(b1,b4), evaluate_target true, frontier_intent{true,0}, source_state_id "$", visit_target true}
  - three adapter records, all naming unstack(b1,b4):
    - text: the key set {action, evaluate_target, frontier_exhausted, exact_bfws_goal_count_priority_successor, exact_bfws_successor, retire_source, source_state_id}. frontier_intent and visit_target are missing.
    - visual: {action, frontier_target_state_id, retire_source_state}
    - multimodal: a 1,712-character runaway output of invented keys. Truncate it and print the length.

**Assert**
- The per-episode facts above: termination `deterministic_invalid_operation` and the decision indices.
- The aggregate, for the tex paragraph and not the caption, recomputed over all 24×3 main-grid episodes:
  - BFS: 68/72 first rejections are successor operations with wrong retire/position fields (67 name a listed unvisited successor, 1 a visited one), and 4/72 are premature `retire_frontier`.
  - BFWS: 72/72 fail at decision 0 (32 unparseable, 40 parseable with invented schema, 17 of them naming the reference action). **[computed]**
- Cross-check against `E/docs/experiments/expanded-study/failure-mechanism-tables/failures-by-cell.csv`:
  - `process_sft` BFWS is 24 `malformed_output` per observation type.
  - BFS is `other_invariant_violation` plus `invalid_frontier_operation`.
  - The BFS strata there count 27 episodes, not 24. Assumption, not verified: the extra 3 per observation type are the DAgger development `original_process_sft` episodes.

**Caption (57 words):** `\textbf{At 512 records, BFS fails on queue bookkeeping and BFWS on the operation format.} Left: the BFS adapter names a valid successor but misstates whether the head is retired and the queue position (differences in orange); all three observation types give this error. Right: the BFWS adapter names the reference action but writes a malformed operation.`

### Q3 `fig:qual-trace-corruption` (optional but cheap; 5.5 × 1.4 in, one outcome strip)

**Purpose.** Make F2 concrete on the same task with the *same* main-grid greedy adapters. The episode checkpoints equal the baseline checkpoints; assert this.

**Episodes:** `E/outputs/expanded-study/v1/modality-stress/episodes/{text-state,multimodal-state,visual-state}/expanded-final__blocksworld-expanded-911101/best_first_add_greedy-{text-shuffled,visual-blank,visual-degraded}-learned_adapter.json.gz`
- Shuffled text:
  - text arm: rejected at events[1] (the 2nd decision) for resubmitting unstack(b1,b4) from s0 after it had already been submitted. Only unstack(b3,b5) remained.
  - multimodal arm: rejected at events[2] for resubmitting unstack(b1,b4) from s0 while the runtime was expanding s1.
- Blanked or degraded images: the visual and multimodal arms solve in 18 decisions.

**Images**
- Clean: `unlabelled/state-000000.png`.
- Blank: regenerate as `Image.new(mode, (128,128), (128,128,128))`.
- Degraded: `resize((16,16), BILINEAR).resize((128,128), NEAREST)` of the cached scene.
- Both follow `E/examples/planning_benchmark_slice/expanded_modality_stress.py` `_corrupt_image`.
- Do **not** print a "shuffled text" excerpt unless it is regenerated exactly through `StressTaskViews` with the protocol's master seed (default 42613; assert it). Otherwise describe the corruption in words.

**Caption (about 55 words):** `\textbf{The same greedy adapters fail when their text is shuffled and solve with blanked or degraded images.} With shuffled text, the text and multimodal adapters resubmit an operation they already submitted and are rejected at decisions 2 and 3. With blanked or degraded images, the visual and multimodal adapters solve the task in 18 decisions.`

### 2.4 A main-text `sec:results-qualitative`?
**No separate subsection.** It costs about 0.15 page, which the main text doesn't have.

Instead, the Results owner should replace the second sentence of L85 ("Consistent with this reading, most learned failures are well-formed operations…") with something like:

"At 512 records, every BFS failure is a well-formed step that names a valid successor but misstates the queue bookkeeping, whereas every BFWS failure is a first operation that does not follow the operation format (Figure~\ref{fig:qual-trace-failures})."

That is about 40 words and fixes risk R1. Drop the `sec:results-qualitative` label from the contract; no file references it.

---
## 3. `fig:contracts` revision (5.5 × 2.35 in at true size; the current figure is 6.55×3.75 scaled down to 5.5×3.15)

**Purpose.** Support the per-algorithm paragraphs in Section 3 (L30, L42) with what one valid step contains under BFS, BFWS and the additive variants, and which fields the policy must derive itself.

**Remove panel (b), choice-frontier, entirely.** It is appendix-only now; the choice-frontier qualitative figures and `app:cf-contract` cover it.

**Top strip (y 1.75–2.35).** Keep the loop, but relabel it to Section 3's vocabulary:
- Chain: Observation (text / visual / multimodal; a 0.4 in thumbnail of the ferry `unlabelled/state-000000.png`) → Search Process Policy (Qwen3-VL-8B + LoRA) → Typed Search Operation → Trusted Search Runtime ("check → apply, or reject and end episode") → Search Memory (frontier · visited · novelty tables) → back to the observation.
- Add a tag under the observation: "candidate rows stay text in every observation type". This supports F2's scope.
- **Switch the source.** The current source is a demoted native-arms `visual-seq-state` episode. Use `E/outputs/expanded-study/v1/baseline/episodes/visual-state/expanded-final__ferry-compact-915000/best_first_add_greedy-process_sft.json.gz` events[0] instead. Assert its raw_output equals `{"action":{"args":["l1","l0"],"name":"sail"},"source_state_id":"s0"}` and that it was accepted.

**Bottom, three equal columns (1.78 in each; headers coloured with ALGO_STYLE).** Each column shows the step-1 observation rows ("observation supplies") and the emissions at steps 1 and 2 ("policy emits") as key: value lines.
- Grey means copied verbatim from the observation. Orange means the policy must derive it.
- Abbreviate state ids ("head").
- Sources: `…/baseline/episodes/text-state/expanded-final__ferry-compact-915000/{bfs,best_first_width,best_first_add_greedy}-exact_reference.json.gz` events[0:2].

**BFS column**
- Observation at step 1: frontier_size 1; candidates sail(l1,l0) unvisited, sail(l1,l2) unvisited.
- Step 1 emits sail(l1,l0), source = head, retire_source = true, target_position = 0, visit_target = true, evaluate_target = false. **retire_source and target_position are orange.**
- Step 2: frontier_size is still 1 and sail(l1,l0) is now visited. Emits sail(l1,l2), retire_source = false, target_position = 1, both orange.
- Footer: "queue fields derived from frontier size and the step's place in the expansion".
- Assert: target_position == frontier_size − retire on both steps; source == `search_memory.frontier_head` at step 1.

**BFWS column**
- Candidates carry integer argument indices, e.g. sail [2,1]. Show dup false, novelty 1, partition (unachieved goals) 1, and `eval.frontier {retire_source: true, target_position: 0}`.
- Step 1 emits sail(l1,l0) with the args orange (translated from indices through `task_context.objects`), frontier_intent {true, 0} in grey (copied from the candidate's eval), source "$", visit_target / evaluate_target = true.
- Step 2: the first candidate is now dup true with eval null. Emits sail(l1,l2), frontier_intent {false, 1}, copied.
- Footer: "frontier position supplied in the candidate's evaluation; copied".
- Assert: the emitted frontier_intent == eval.frontier of the matching candidate; index→name mapping == the emitted args.

**Additive column (greedy best-first; weighted A* is identical except priority g+3h)**
- Rows: sail(l1,l0) g 1, h 4, priority 4 → s1; sail(l1,l2) g 1, h 3, priority 3 → s2.
- Step 1 emits {action sail(l1,l0), source_state_id s0}. Step 2 emits sail(l1,l2). Everything is grey.
- Footer: "runtime keeps the heap and computes every value".
- Assert: the emitted key set == {action, source_state_id}; the rows match.

**Optional:** a third one-liner in the BFS and BFWS columns for step 3, which emits `retire_frontier` (events[2]). This shows the retire step that the additive variants don't have.

**Caption (59 words):** `\textbf{What one valid step contains under each algorithm.} Top: the policy reads an observation and emits one typed operation; the runtime checks and applies it, and the first invalid operation ends the episode. Bottom: the first two steps on the ferry task of Figure~\ref{fig:teaser}a. Grey fields are copied from the observation; orange fields must be derived by the policy.`

---
## 4. Risks to the new storyline at the figure level

- **R1 (high): the BFWS "bookkeeping" explanation is not what the 512-record failures show.**
  - failures-by-cell.csv has BFWS `process_sft` = `malformed_output` in 24/24 episodes for each observation type. Every failure is at decision 0, and 17 of them name the correct action **[computed]**.
  - fig:contracts, which follows the code and Section 3 L30, also shows that BFWS *copies* its frontier fields.
  - These two sentences overstate it for BFWS: Results L85 ("most learned failures are well-formed operations … rejected for breaking the algorithm's invariant") and Discussion L5 ("history bookkeeping, the visited set or the novelty tables").
  - Fix: say BFS fails on queue bookkeeping, and BFWS fails to learn its larger operation and observation format (indexed arguments, bitmask atoms). Keep the hypothesis hedged.
- **R2: the minimum data needed is unknown.** We observe failure at 512 (and with DAgger's roughly 200 added corrections) and success at ≥11,911. Nothing in between was tested. No figure may draw a curve or a threshold, and the body should say this once next to "require over an order of magnitude".
- **R3: the (b) development points look stronger than they are without the random-valid ring.** The BFS text panel has random-valid 1.000. Keep the rings.
- **R4: Fig. 1a could be read as Searchformer-style whole-trace generation.** The subheader "one operation per model call" and the caption's "one step per record" prevent that.
- **R5: (c) could be read as "images are useless".** The fig:contracts top-strip tag and the Results L114 scope sentence carry the boundary. Adding a word to the teaser caption would push it over 60 words.
- **R6: vocabulary.** The frozen abstract says "text, image, and combined"; the tables and (c) use text / visual / multimodal. Keep the table vocabulary in the figures. Main should decide whether Section 3 maps the terms once.

## 5. Discrepancies found
- **D1.** The 12,994 figure is `E/data/bfs_pilot_v6/ms-swift-process/manifest.json` counts.train (dev 12,115). Intro L29, Discussion L7 and Results L28 cite `process-release/manifests/bfs-text-corpus.json` as "12,994 train rows", but that file only has counts.process_records 25,109 and split_assignments 90.
- **D2.** The BFS v8 development run has five training seeds (per_seed 17/29/43/71/101, each 1.0). Check this against the Design and Limitations wording "single training seed except two three-seed cells", which is scoped to the main grid.
- **D3.** The old `fig:contracts` evidence comment cites `outputs/native-arms/v1/...`, a demoted arm. The new source is the main-grid baseline episode.
- **D4.** Appendix L503 describes the old teaser and filmstrip scene provenance. It becomes stale after this cutover.