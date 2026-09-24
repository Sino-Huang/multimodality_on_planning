# #142 feasibility note: identity audit on LLM-First Search

Written 2026-09-25, before the protocol and before any GPU launch or audit episode. It answers
the #142 pre-registration requirement "feasibility and cost estimate first".

## Why #137 left this interface out

In the #137 survey (row 6, `issue-137-survey.md`), LLM-First Search (LFS; Herr, Rocktäschel,
Raileanu, arXiv 2506.05213) is interface type C: the model scores candidates, and a search
orders them. It was the only candidate predicted to **saturate**. It was dropped at the
"CPU feasible under the paper's own budget, unchanged" step, because the budget is an LLM-token
cap and a control that spends no tokens never exhausts it (#137 closeout, Limitations). That
test asked whether the controls alone could run on CPU. Here the reference arm is the
published controller, so it needs a model. The question for this note is whether the model can
run locally without a paid API.

## Sources (fetched 2026-09-25)

- Paper: https://arxiv.org/abs/2506.05213 (v1 PDF). Algorithm 1; Sec. 5.2-5.3; App. C-D; Table 2.
- Code: https://github.com/NathanHerr/LLM-First-Search @ `3025bdaa3add6f41388c1d5a6d354522489d312e`
  (2025-06-09, Apache-2.0). Cloned untracked at `outputs/external-audit/v2/upstream/LLM-First-Search`.
  Nothing is vendored: the runner imports it.

## What the paper runs

| item | paper / README value |
|---|---|
| tasks | Countdown difficulty 3, 5, 7 (`data/countdown/val_{3,5,7}.json`); Sudoku 4x4 (2x2 boxes, `hard`) and 6x6 (2x3 boxes, `medium`) |
| games | README "Reproducing Paper Results": `--num-batches 20 --batch-size 1`, so games 0-19 of each file |
| runs | n = 5 per game at temperature 0.0 (Sec. 5.3.1) |
| budget | token cap per game (Alg. 1, "while Token limit not exhausted"). README: Countdown 1,000,000; Sudoku 4x4 100,000; Sudoku 6x6 500,000 |
| model settings | GPT-4o (and o3-mini) through the OpenAI API; temperature 0.0, `max_tokens` 16,384, timeout 300 s, no reasoning module for GPT-4o (App. D) |
| LFS GPT-4o WinRate (Table 2) | Countdown 100.00 / 63.16 / 47.37 (diff 3/5/7); Sudoku 96.84 (4x4) / 2.22 (6x6) |

The #137 survey said the cap "used for Table 2 is not reported". The README reproduction table
does report it (above). The protocol uses these values.

## Controllers

- **random_valid needs no LLM calls.** The runner replaces the agent's `ask` with a
  uniformly random valid answer: `explore` is a fair coin, and every value is an independent
  U(0, 1) draw. The argmax child and the popped frontier node are therefore uniform among the
  valid options. It spends zero tokens and runs on CPU.
- **reference needs the model.** It is the published LFS controller (`run_countdown` /
  `run_sudoku`, unchanged), and every explore, value and child-value query goes to an LLM.

## Paid API: not needed; declared model substitution

Running GPT-4o as in the paper would be a paid API. One pass over the audited tasks is at most
~42M tokens (next section). At GPT-4o list prices ($2.50 per M input, $10 per M output,
assuming ~20% output), that is about $170 per pass, and about $840 for the paper's n = 5. The
ticket forbids paid API spend. The reference therefore runs a **local open-weight substitute**:

- `Qwen/Qwen3-30B-A3B-Instruct-2507`, revision `0d7cf23991f47feeb3a57ecb4c9cee8ea4a17bfe`
  (Apache-2.0). It is a 30.5B-parameter MoE with 3.3B active parameters, a non-thinking
  instruct model, the analogue of GPT-4o without the reasoning module. The bf16 weights (57 GB)
  fit on one A100 80GB.
- Served by vLLM 0.11.0 (torch 2.8.0+cu128; driver 570 supports CUDA 12.8), OpenAI-compatible,
  on **GPU 1** (`CUDA_VISIBLE_DEVICES=1`). Port **18850** serves HTTP, `VLLM_PORT=18851` is
  vLLM's internal port, and `MASTER_PORT=18852` is the torch rendezvous port. Upstream settings
  are kept: temperature 0.0, `max_tokens` 16384, timeout 300 s.

This substitution is a declared deviation. The reference success rates are this model's, not
GPT-4o's, and the published GPT-4o numbers are quoted beside them.

## CPU probe of the random_valid arm (games 20-24, never audited)

The probe ran `scripts/run_external_audit_v2_lfs.py random --set probe`. It used 5 non-audited
games per configuration, the five #137 seeds, and a 200,000-expansion guard.

| config | episodes | won | median expansions | max | CPU s (sum) |
|---|---|---|---|---|---|
| Countdown-3 | 25 | 25 | 10 | 38 | <1 |
| Sudoku 4x4 hard | 25 | 25 | 174 | 5,815 | 5 |
| Countdown-5 | 25 | 25 | 3,067 | 17,661 | 4 |
| Countdown-7 | 25 | 25 | 11,199 | 115,459 | 48 |

(An earlier probe with a 20,000-expansion guard stopped 10 of the 25 Countdown-7 episodes.
The protocol therefore sets the guard at 500,000.)

Engineering finding: the unpatched upstream loop cannot run a zero-token chooser to completion
on Countdown-5/7. `Explorer.frontier_nodes` is a full-tree BFS that is called about ten times
per step. `calculate_and_check_token_usage` re-sums the whole token list for every frontier
node inside the explore loop, so the cost grows roughly cubically with the number of
expansions. The unpatched loop had not finished `cd5-20` seed 17 after more than 10 minutes;
that episode takes 10,558 expansions and 0.37 s with the replacement. For random_valid only,
the runner swaps in an incremental frontier (`FastFrontier`: a lazy max-heap, cached counters
and a running token sum). Its episode logs must be byte-identical to the unpatched loop's. The
`fast-equivalence` command ran every probe episode of at most 1,200 expansions both ways:
**57/57 byte-identical** (cd3 25, su4 24, cd5 5, cd7 3; 43 longer episodes skipped;
`outputs/external-audit/v2/lfs-probe/fast-equivalence.json`). The reference arm always runs the
unpatched loop.

## GPU-h estimate (reference arm only) against the 12 GPU-h cap

- Token volume for one reference run per audited game (the protocol audits Countdown 3/5/7 and
  Sudoku 4x4, 20 games each). An upper bound assumes every hard game exhausts its cap:
  Countdown-3 ~20 x 10k (the paper's LFS uses about 5-9k per game) + Countdown-5 20 x 1M +
  Countdown-7 20 x 1M + Sudoku 4x4 20 x 100k, which is at most ~42M tokens processed.
- Throughput on one A100 with 3.3B active parameters, 32 concurrent episodes and prefix caching
  of the long shared system prompts (assumed, not yet measured): at least ~1.5k output tok/s and
  at least ~10k prompt tok/s. With ~20-25% of the tokens as completions, the run needs at most
  ~2 h of decode and at most ~1 h of prefill.
- Estimate: **~2-4 GPU-h** including model load and the smoke run, with an upper bound of
  ~6 GPU-h, under the **12 GPU-h** cap. The protocol stops launching new reference episodes at
  10 GPU-h.
- The random_valid arm, the replays and the analysis use CPU only (0 GPU-h).

Conclusion: the audit is feasible without paid APIs. It needs one declared deviation, the model
substitution, plus the design choices frozen in `issue-142-protocol.md`.
