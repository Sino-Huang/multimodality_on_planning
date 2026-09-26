# Abstract drafts v3

Title (fixed): *Can Vision-Language Models Learn to Execute Classical Search Algorithms?*

Storyline: author decisions of 2026-09-26, including Main's update that asks for all four supporting results (a)–(d). This storyline supersedes the framing in `CONTEXT.md` and the current `iclr2026_conference_abstract.tex`, which this round leaves unchanged.
Word counts are whitespace-delimited tokens. `$h_{\mathrm{add}}$`, `Qwen3-VL-8B`, and `(InternVL3.5-8B)` each count as one token. Limit: 280.

---

## Abstract A

Findings 1 and 2, then (a)–(d) in two compact sentences, with a short caveat clause.

> Language models fine-tuned for classical planning almost always learn the returned plan, not the search behind it. What a model learns from traces of different search algorithms remains open. As embodied agents develop, we study this for vision-language models (VLMs) with text, image, or combined observations. We fine-tune Qwen3-VL-8B with LoRA on traces of blind breadth-first search (BFS), width-based BFWS, and greedy and weighted-A* best-first search with $h_{\mathrm{add}}$ in 12 PDDL domains. The model must issue every search step itself, each valid under the declared algorithm, and reach the goal. All four algorithms are learnable, at very different data costs. With 512 records and one shared recipe, the model executes both $h_{\mathrm{add}}$ variants to the goal in 125 of 144 episodes. BFS and BFWS, whose steps must also report visited-set or novelty bookkeeping, solve no task at that budget. In separate runs with over ten times more data, both succeed on development tasks: BFS at 1.0 with about 13k records, BFWS at 0.933 with 47,780. Text carries the learned execution: on frozen checkpoints, shuffling text lowers success by up to 0.94, blanking images by at most 0.11. The pattern holds on a second VLM (InternVL3.5-8B) and 25 semantics-preserving task variants, and FOLIO, GSM8K, and HumanEval accuracy shows no detectable change. Asked to choose which frontier state to expand from rendered scenes, the model beats random choice but stays far below exact search. For planning, this is a controlled test of search-trace training across algorithms and modalities. In this development-stage evidence, which supports no general planning claim, trace supervision works, its data cost rises with the bookkeeping an algorithm reports, and images add little when search memory is text.

**Word count: 278.** Per sentence: 17, 12, 17, 26, 18, 10, 21, 18, 26, 22, 23, 22, 14, 32.
Caveat clause: "which supports no general planning claim", together with "development-stage".

### Claim-to-evidence table (A)

| # | Claim or number in A | Brief source | Repository evidence (read-only check) |
|---|---|---|---|
| 1 | Plan-level training is the norm | Storyline, Background | `iclr2026_conference_related_work.tex` ¶1 ("typically supervised on plans, not on the search behind them") |
| 2 | Four algorithms: BFS, BFWS, greedy and weighted-A* with $h_{\mathrm{add}}$ | What we did | `content_brief.md` L22 (active algorithm matrix) |
| 3 | 12 PDDL domains | What we did | `content_brief.md` L23 ("24 tasks from 12 domains") |
| 4 | Qwen3-VL-8B, LoRA | What we did | `iclr2026_conference_experimental_design.tex` L93; `iclr2026_conference_appendix.tex` L224 |
| 5 | 512 records, one shared recipe | Finding 1 | `appendix.tex` L224 (one epoch on 512 records per expanded-baseline cell) |
| 6 | 125 of 144 episodes, both $h_{\mathrm{add}}$ variants | Finding 1 (24 tasks × 2 algorithms × 3 observations) | `content_brief.md` L23: process SFT 125/288 over all cells, all successes in additive cells. 144 = 24 × 2 × 3 is the additive subset (derived). Introduction and Results print 125/288. |
| 7 | BFS and BFWS solve no task at 512 records | Finding 1 (0/24 per cell) | `content_brief.md` L23 ("0/24 in every modality"); Table `tab:results-primary-matrix` |
| 8 | "over ten times more data" | Finding 1 ("more than an order of magnitude") | Derived: 12,994 / 512 = 25.4×; 47,780 / 512 = 93.3× |
| 9 | "In separate runs" | Added for accuracy | `appendix.tex` L224: these recipes "describe different development-stage interventions rather than a matched-size comparison" (the BFWS run trains two epochs) |
| 10 | BFS 1.0 with about 13k records | Finding 1 | `appendix.tex` L210 (12,994 train rows, v6 BFS corpus); `CONTEXT.md` L65 and `writing_design_tree.md` L9 (15-task v8 development panel, success 1.0) |
| 11 | BFWS 0.933 with 47,780 records | Finding 1 | `appendix.tex` L218, L224; `results.tex` L61 (`docs/issue-59-bfws-structural-gate.md` L250–255) |
| 12 | Text shuffling lowers success by up to 0.94 | Finding 2 | `appendix.tex` Table `tab:results-corruption`: text-shuffled, text-state arm −0.944 (multimodal arm −0.722); frozen checkpoints, k = 9 tasks (L877) |
| 13 | Image blanking costs at most 0.11 | Finding 2 | Same table: visual-blank, multimodal arm −0.111 (visual arm −0.056); every visual interval includes zero |
| 14 | Pattern holds on InternVL3.5-8B | (a) | `appendix.tex` L830, L833: BFS 0/36, greedy 31/36 (numbers not printed in A) |
| 15 | 25 semantics-preserving task variants | (b) | `appendix.tex` L751: learned 128/150, base 0/150, shifted-init 19/30 (numbers not printed in A) |
| 16 | No detectable change on FOLIO, GSM8K, HumanEval | (c) | `appendix.tex` L415, L794: 0 of 36 McNemar comparisons survive Holm correction, minimum adjusted p 0.8156 |
| 17 | Frontier choice beats random, far below exact search | (d) | `iclr2026_conference_abstract.tex` L10: `outputs/choice-frontier/v4/panels/metrics/analysis.json` arms.p135 m1 = 0.021 / 0.306 / 0.875; L28: `v4/seeds` primary.D3 +0.285 (POSITIVE) |
| 18 | Development-stage, no general planning claim | Claim boundary | `abstract.tex` L31; `CONTEXT.md` L65, L67 |

---

## Abstract B

Findings 1 and 2, (d) promoted to a full third finding, and (a)–(c) as one closing clause of support. No caveat.

> Language models fine-tuned for classical planning almost always learn the returned plan, not the search behind it. What a model learns from traces of different search algorithms remains open. As embodied agents develop, we study this for vision-language models (VLMs) with text, image, or combined observations. We fine-tune Qwen3-VL-8B with LoRA on traces of blind breadth-first search (BFS), width-based BFWS, and greedy and weighted-A* best-first search with $h_{\mathrm{add}}$ in 12 PDDL domains. The model must issue every search step itself, each valid under the declared algorithm, and reach the goal. All four algorithms are learnable, at very different data costs. With 512 records and one shared recipe, the model executes both $h_{\mathrm{add}}$ variants to the goal in 125 of 144 episodes. BFS and BFWS, whose steps must also report visited-set or novelty bookkeeping, solve no task at that budget. In separate runs with over ten times more data, both succeed on development tasks: BFS at 1.0 with about 13k records, BFWS at 0.933 with 47,780. Text carries the learned execution: on frozen checkpoints, shuffling text lowers success by up to 0.94, blanking images by at most 0.11. Frontier choice is learned only in part. When the model must pick which frontier state to expand from rendered scenes, its area under the solve-versus-budget curve on validation tasks is 0.306, against 0.021 for random choice and 0.875 for exact search. Consistent across a second VLM (InternVL3.5-8B) and 25 semantics-preserving task variants, and with no detectable change on FOLIO, GSM8K, or HumanEval, these results give planning a controlled answer: trace supervision works, its data cost rises with the bookkeeping an algorithm reports, and images add little when search memory is text.

**Word count: 278.** Per sentence: 17, 12, 17, 26, 18, 10, 21, 18, 26, 22, 7, 34, 50.

### Claim-to-evidence table (B)

Rows 1–13 and 16 of table A apply unchanged. B differs in these rows:

| # | Claim or number in B | Brief source | Repository evidence (read-only check) |
|---|---|---|---|
| B1 | Frontier choice learned only in part | (d) | `abstract.tex` L27–28: `v4/seeds/metrics/analysis.json` primary.D3 = +0.285, verdict POSITIVE, interval [+0.140, +0.433] (L29) |
| B2 | 0.306 (trained adapter, area under solve-versus-budget curve) | (d), Main update | `abstract.tex` L10: `outputs/choice-frontier/v4/panels/metrics/analysis.json` arms.p135.learned_adapter_seed_mean.m1 (three-seed mean, validation panel) |
| B3 | 0.021 (random choice) | (d) | Same file, arms.p135.random_valid.m1 |
| B4 | 0.875 (exact search) | (d) | Same file, arms.p135.exact_reference.m1 |
| B5 | "on validation tasks" | Main update ("validation panel") | Same key p135 = issue #135 validation panel (`CONTEXT.md` L67) |
| B6 | Consistent on InternVL3.5-8B | (a) | `appendix.tex` L830, L833: BFS 0/36, greedy 31/36 (numbers not printed in B) |
| B7 | 25 semantics-preserving task variants | (b) | `appendix.tex` L751: 128/150, base 0/150, shifted-init 19/30 (numbers not printed in B) |

Unchecked arithmetic: 0.306 − 0.021 = 0.285, which matches primary.D3. The gain is not printed in B.

---

## Alternative endings

Each ending replaces the last two sentences of Abstract A (sentences 13–14, 46 words). Sentences 1–12 of A total 232 words. To keep A's caveat, insert "on development tasks" (+3) where marked [c].

**(i) What the community learns (41 words).**
> Planning work has mostly trained models on plans. This study shows what a VLM learns from search traces instead: [c] trace supervision works, its data cost rises with the bookkeeping an algorithm reports, and images add little while search memory is text.

A + (i): 273 words, or 276 with [c].

**(ii) Design lesson for planning-oriented foundation models (44 words).**
> For planning-oriented foundation models, trace data should be budgeted by algorithm: 512 records sufficed for heuristic best-first search, while BFS and BFWS needed over ten times more. Visual benefit needs testing with search memory removed from the text, since text carried the learned execution.

A + (ii): 276 words. With a caveat ("On development tasks, 512 records sufficed …") it is 279.

**(iii) Trace supervision as a research direction (40 words).**
> These results make search traces a supervision target for planning research, alongside plans. Trace supervision works [c] for all four algorithms, and two measured gaps set the next problems: the data cost of history bookkeeping, and frontier choice from rendered scenes.

A + (iii): 272 words, or 275 with [c].

---

## Evidence notes (for the author, not abstract text)

1. **Denominators.** The abstracts say 125/144, while the Introduction and Results say 125/288. The two agree (the 144 additive entries are a subset of the 288), but a reader who compares them will see a mismatch.
2. **What "success" means in Finding 1.** The manuscript's current framing is that on the additive cells any valid step succeeds (Section 5.1). So 125/144 shows valid execution, not good choice. Finding (d) covers choice. On the BFS 1.0 development panel, the uniform control also scores 1.0 (`CONTEXT.md` L65). Per the brief, the abstracts mention neither point.
3. **Data-cost comparison.** The ~13k and 47,780 runs differ from the 512-record recipe in more than data size (for example, BFWS trains two epochs). "In separate runs" keeps the abstract from implying a matched comparison. "Rises with the bookkeeping" describes an association between two algorithm groups, not a mechanism.
4. **Finding 2 wording.** The 0.94 drop comes from the text-state arm. In the multimodal arm the drop is 0.72, and the paired text-minus-visual contrast is −0.694 [−0.889, −0.472]. The brief's lead phrase "under multimodal training" was therefore dropped, so that 0.94 is not read as the multimodal-arm number.
5. **Image-only arms.** The appendix image-only native arms remove textual search memory and solve 18/18, with saturated controls. This limits "images add little when search memory is text" to the declared adapters. It is also relevant to ending (ii)'s recommendation, part of which the appendix already runs.
