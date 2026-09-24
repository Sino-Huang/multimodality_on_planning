# #142 protocol: per-decision identity audit on LLM-First Search (frozen before any audit episode)

Answers review 20 finding 69c (#131). Before this protocol only the feasibility note
(`issue-142-feasibility.md`) and CPU-only random_valid runs on non-audited games (20-24) existed:
the probe and the `fast-equivalence` check. No GPU had been launched and no audit episode had
been run.

## Interface and upstream

- Herr, Rocktäschel, Raileanu, *LLM-First Search: Self-Guided Exploration of the Solution Space*,
  arXiv 2506.05213 (fetched 2026-09-25). Interface type **C** in the #137 survey: the model scores
  candidates (explore flag, state values, child values), and the search takes the argmax child
  or pops the highest-valued frontier node. Every unexpanded alternative stays in the frontier.
- Code: https://github.com/NathanHerr/LLM-First-Search @ `3025bdaa3add6f41388c1d5a6d354522489d312e`
  (Apache-2.0), cloned untracked at `outputs/external-audit/v2/upstream/LLM-First-Search`. The
  runner asserts that the checkout is at this commit and unmodified. Upstream code runs in the
  venv `outputs/external-audit/v2/venv-lfs` (upstream `requirements.txt`, Python 3.12.12).
- Runner: `scripts/run_external_audit_v2_lfs.py`. Analyzer:
  `scripts/analyze_external_audit_v2_lfs.py`. Both are committed before the first audit outcome.

## Tasks (selection rule)

The paper's task configurations are Countdown difficulty 3/5/7 and Sudoku 4x4 (`hard`) and 6x6
(`medium`). The fixed rule audits **every configuration on which the paper's LFS-GPT-4o WinRate
(Table 2) exceeds 10%**. The saturation threshold is 0.9 x reference success. At the floor
(Sudoku 6x6: 2.22%), any control meets it trivially, and the reference there is the most
expensive run (500k-token cap). The audited configurations are:

| config | upstream file | token cap (README) | LFS-GPT-4o WinRate |
|---|---|---|---|
| cd3 | `data/countdown/val_3.json` | 1,000,000 | 100.00 |
| su4 | `data/sudoku/sudoku_diff_hard_w_2_h_2.pkl` | 100,000 | 96.84 |
| cd5 | `data/countdown/val_5.json` | 1,000,000 | 63.16 |
| cd7 | `data/countdown/val_7.json` | 1,000,000 | 47.37 |

Games: **0-19 of each file**, the README reproduction set (`--num-batches 20 --batch-size 1`).
That gives **80 tasks** (`cd3-00` … `cd7-19`), the task clusters of the analysis.

## Budget

- The paper's own per-game token cap (table above), applied by the unchanged upstream check
  `calculate_and_check_token_usage`. Other upstream settings: temperature 0.0, `max_tokens`
  16384, timeout 300 s, `reasoning 0`, `num_its 1`, `batch_size 1`.
- An episode ends as upstream ends it: win, frontier exhausted, or token cap.
- A safety guard of **500,000 expansions** per episode applies. Hitting it ends the episode as a
  loss (`terminated = "expansion_cap"`) and is reported, never hidden. The probe's largest
  Countdown-7 episode used 115,459 expansions.
- An upstream exception (for example an agent query that fails all 5 upstream retries, which
  the upstream loop does not survive) ends the episode as a loss (`terminated = "upstream_error"`)
  and is reported.

## Arms

- `reference`: the published LFS controller, `run_countdown` / `run_sudoku` unchanged, with
  every agent query sent to the substitute model (Deviation 1). **One run per task**
  (Deviation 2).
- `random_valid`: the same upstream loop. The agent's `ask` returns a uniformly random valid
  answer: `explore` is `rng.random() < 0.5`, and each requested value (state value, every child
  value) is an independent `rng.random()`. Because upstream takes the argmax, the chosen child and
  the popped frontier node are uniform among the valid options. The arm spends zero tokens and
  makes no model call. Seeds **17, 5077, 6131, 7409, 8527** (the #137 seeds), with per-episode RNG
  `random.Random(int(sha256(f"{seed}|{task}")[:16], 16))`.

## What a decision is

A decision is one node expansion after the root (the search commits to that node). It is
recorded by wrapping `PathNode.expand` and identified by its child-index path from the root
(`"4.0.17"`). An episode's decision sequence is its ordered list of expansions. The winning
leaf's expansion is the last decision of a won episode. The logs also store the action
description and the number of sibling options at every decision.

## Serving the reference model (GPU 1 only)

```
CUDA_VISIBLE_DEVICES=1 VLLM_PORT=18851 MASTER_PORT=18852 HF_HOME=<repo>/.cache/hf \
outputs/external-audit/v2/venv-vllm/bin/vllm serve Qwen/Qwen3-30B-A3B-Instruct-2507 \
  --revision 0d7cf23991f47feeb3a57ecb4c9cee8ea4a17bfe --served-model-name Qwen/Qwen3-30B-A3B-Instruct-2507 \
  --host 127.0.0.1 --port 18850 --max-model-len 40960 --gpu-memory-utilization 0.90 \
  --max-num-seqs 64 --seed 0 --dtype bfloat16
```

Frozen launch spec: `configs/experiments/external-audit-v2/lfs-reference-server.json`. vLLM 0.11.0, torch 2.8.0+cu128, separate venv `outputs/external-audit/v2/venv-vllm`. The server is
started through the hub process tool. Port mapping: 18850 HTTP, 18851 vLLM internal, 18852 torch
rendezvous. The runner asserts that the served model id matches. Episodes run in parallel
(`--concurrency 32` processes). Each call's request sha256, response text, finish reason and
token usage are logged.

## Order of execution

1. Commit and push this protocol.
2. `fast-equivalence` on the probe set (games 20-24, not audited), **already run before this
   protocol: 57/57 byte-identical**. Every random_valid probe episode of at most 1,200 expansions
   was run through the unpatched upstream loop and through `FastFrontier`
   (`outputs/external-audit/v2/lfs-probe/fast-equivalence.json`). `FastFrontier` asserts its two
   invariants in every episode: each frontier node is valued, and the maximum has no tie. An
   assertion failure in an audit episode would be an `upstream_error`, and a dated amendment
   would switch that arm to the unpatched loop before any analysis.
3. Start the server (ledger opens). Smoke on games 20-21 of every configuration (not audited):
   reference, random_valid and replay into `outputs/external-audit/v2/lfs-smoke/`. The smoke
   checks plumbing only; its outcomes are not analysed.
4. Audit reference run (80 tasks), then stop the server (ledger closes). Audit random_valid run
   (400 episodes, CPU).
5. Replay (below). The analysis runs only after replay reports 0 missing and 0 mismatch in both
   arms.
6. Analysis, closeout, ticket comments.

## Replay / validation

- **reference, every episode.** The episode is re-executed through the unchanged upstream loop
  with a client that returns the logged responses in order and asserts each request is identical
  (sha256) to the logged request. Decisions, labels, options, outcome, token counts, API-call
  count, backtracks, attempts, termination and the metrics-log hash must all match, and every
  logged call must be consumed.
- **random_valid, every episode.** Each episode is re-run in a fresh process, and its log must be
  byte-identical to the stored one.
- Result: `outputs/external-audit/v2/lfs/replay.json`. The analyzer refuses to run unless both
  arms have 0 missing and 0 mismatch.

## Endpoints (`outputs/external-audit/v2/lfs/identity-audit.json`, schema `external_identity_audit_v2`)

- Pair = (task, random_valid seed) against the reference on the same task, so
  `pairs_checked = 80 x 5 = 400`. A pair is **identical** iff the two decision sequences are equal
  and the win flags are equal; otherwise it is divergent. Reported: `pairs_identical`,
  `pairs_divergent`, and `first_divergence_index` (lower median, min, max over divergent pairs, and
  the count diverging at index 0; if one sequence is a prefix of the other, the index is the
  shorter length).
- Success = win rate over the 80 tasks: `reference`, `random_valid_per_seed`, `random_valid_mean`.
  Two budget readings are reported:
  - **`paper_budget` (primary):** each arm's win under the paper's token cap.
  - **`matched_decision_budget` (co-reported):** a random_valid episode counts as a win only if
    it wins within the reference's own number of expansions on that task. This asks the identity
    question at equal decision counts.
- `saturation = random_valid_mean >= 0.9 x reference` for each reading.
- The same quantities per configuration (`per_config`).
- Published comparison: the GPT-4o LFS WinRate averaged over the audited configurations
  (100.00, 96.84, 63.16, 47.37, giving 0.7684) and `random_fraction_of_published`.

## Verdict rule (the #137 rule, per reading)

`IDENTICAL` if `pairs_identical == pairs_checked`; otherwise `SATURATED` if `saturation`;
otherwise `CHOICE_REGISTERED`. The headline `verdict` is the `paper_budget` verdict. The
`matched_decision_budget` verdict is reported beside it.

## Statistics (descriptive, the #138/#139 conventions)

For each reading, the per-task difference is d_t = reference win − mean random_valid win over
the five seeds. Reported:

- the mean of d_t with a task-cluster percentile bootstrap 95% interval (seed 133, 10,000 draws);
- the random/reference success ratio with its bootstrap interval;
- an equivalence flag (interval inside ±0.05);
- the **exact two-sided sign-flip permutation p-value** of the mean of d_t (review 20
  small-cluster request). It is computed exactly by convolution over all 2^80 sign vectors,
  since d_t lies on a 0.2 grid.

These do not enter the verdict. Also reported, descriptively: a random_valid
success-versus-decision-budget curve at m x the reference's expansions, m in
{1, 1.25, 1.5, 1.75, 2}, with its normalized trapezoidal AUC.

## Pre-registered prediction

- `pairs_identical = 0` (the first random expansion matches the reference's argmax child with
  probability 1/B, where B is the root branching of 12-84 on Countdown), with first divergence
  mostly at index 0.
- **`paper_budget`: SATURATED.** This is the #137 survey prediction. The frontier keeps every
  alternative and a zero-token chooser is never stopped by the cap, so random_valid is a complete
  randomized search. The probe won 100/100 non-audited episodes within the guard.
- **`matched_decision_budget`: CHOICE_REGISTERED.** At the reference's own number of decisions,
  random_valid should win far less often on cd5/cd7/su4 (probe median expansions to a win: 3,067
  on cd5 and 11,199 on cd7). The reference is expected to use hundreds of expansions within 1M
  tokens.

## Consequence mapping for #131 (fixed now)

- paper_budget `SATURATED` with pairs divergent. A published evaluation exists whose success
  metric does not register choice under its own budget. The mechanism is budget denomination
  (tokens bind only the model) plus a complete frontier, not per-decision identity. The
  value-anchor sentence should say that the per-decision identity failure is still shown only
  on our runtime, and that a published type-C interface (LFS) shows the outcome-level
  counterpart: under its token budget a zero-token random chooser matches or beats the model.
  If `matched_decision_budget` is `CHOICE_REGISTERED`, the sentence adds that at equal decision
  counts the model's choices do matter.
- paper_budget `CHOICE_REGISTERED`: the survey conclusion stands and is strengthened (the one
  interface predicted to saturate does not). The sentence stays, with LFS added as a second
  audited published interface.
- `IDENTICAL`: a published-practice instance of the per-decision identity failure. The
  sentence "shown only on our runtime" must be withdrawn.

## Declared deviations

1. **Model substitution.** GPT-4o (paid API) is replaced by the local open-weight
   `Qwen/Qwen3-30B-A3B-Instruct-2507` @ `0d7cf239`, non-thinking, served on GPU 1. Reference
   success is this model's. GPT-4o numbers are quoted from Table 2 and never mixed into the
   verdict inputs.
2. **One reference run per task**, instead of the paper's n = 5 at temperature 0.0 (as in #137).
   Win = the single run's outcome, not the paper's "WinRate > 0.5" per game.
3. **Sudoku 6x6 excluded** by the rule above.
4. **`FastFrontier` for random_valid only.** This is a performance replacement for upstream's
   full-tree frontier scans, and it must produce byte-identical logs (step 2). The reference
   always runs the unpatched loop.
5. **Result capture.** Upstream's per-game pickle of the whole search tree is replaced by keeping
   the same result dictionary in memory. Nothing that upstream computes changes.

## Compute ledger

`outputs/external-audit/v2/budget.json`, independent of every other ledger. The cap is
**12 GPU-h** (GPU 1). Every second the vLLM server holds GPU 1 is counted, including load, smoke,
idle time and failures. No new reference episode is launched once the running total reaches
10 GPU-h. Tasks without a reference episode are then excluded from both arms and disclosed.
Paid API spend: $0.

## Amendment A1 (2026-09-25 02:55 AEST, before any audit episode)

The smoke started at 02:45 AEST on games 20-21. Its cd3 episodes completed after 38 s and 53 s
(8,035 and 11,160 tokens, 5 and 7 calls). At the observed ~7 s per call, a Countdown-5/7
episode that uses its 1M-token cap needs about 600 sequential calls, roughly 1-1.5 h. Holding the
audit until the four cd5/cd7 smoke episodes finish would leave GPU 1 mostly idle for that time,
and all of it would count against the ledger. Change to step 3/4 order: **the audit reference run
starts once the smoke's cd3 and su4 reference episodes have completed and replay with 0
mismatch**. The cd5/cd7 smoke episodes continue concurrently. They are replayed after they
finish and before the audit analysis. Smoke outcomes remain unanalysed. The audit reference run
uses `--concurrency 64` (the server's `--max-num-seqs`), so every audit episode runs at once. The
estimands, verdict rule, prediction, tasks, seeds, budget and analysis are unchanged.
