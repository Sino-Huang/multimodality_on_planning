# Phase 3 Pilot Rendering Verification — 2026-08-11 Regression Replays

## Outcome

Classification: **RED — repository-side remote compatibility delta proven.** Four separately
authorized, single-attempt, zero-delay replay requests ran against
`https://planimation.planning.domains/upload/pddl` on 2026-08-11 using the staged harness
(`tmp/cgas-phase3-planimation-regression-replays-20260811/harness/replay_planimation_client.py`).
Replay 1 (exact July-22 known-good problem) and replay 3 (same pilot semantics with canonical
`b1..bN` naming and July formatting) succeeded; replay 2 (exact actually-transmitted smoke-v2
problem) and replay 4 (12-object empty-goal probe) failed.

This refutes a blanket upstream regression/outage: replay 1 currently succeeds, so the hosted
backend accepts the July-22 bundle today. It proves a repository-side remote compatibility delta:
replay 2 fails while replay 3 succeeds with semantic init/goal preserved. Because the compound
probe changed BOTH object naming and formatting, the evidence does NOT isolate which one alone is
causal. Replay 4 does NOT prove 12-object incompatibility — its empty-goal handling failed later at
stage generation (`Failed to generate stages \n\n 'init'`); 12-object compatibility remains
unproven.

Production rendering (16,822 states) and replay alignment (790 rows) remain unstarted. The
operator command is NOT authorized to resume until the writer patch and both required smokes pass.

## Authoritative outcomes (read directly from each `result.json`)

All four replays used domain SHA `2eed94c5a8fdfe2ac608c45cdf8a68274d69c1920bb4f831529f7bfaaaf79d81`,
profile SHA `9ded071f7ae255de719d753a815bf56ed6756393e14a6065a331e7d5297a8d32`, the exact URL
`https://planimation.planning.domains/upload/pddl`, one request, `--timeout-seconds 30`,
`--max-attempts 1`, `--request-delay-seconds 0`, and a unique new output root.

| Replay | Output root | Status | Problem SHA-256 | Trace SHA-256 | Trace bytes |
|---|---|---|---|---|---|
| 1 — July-22 known-good verbatim | `outputs/image_frames/cgas-phase3-planimation-regression-replay-01-20260811` | success | `0e7f043f2033bb6419c86bdba8ab1a0f53fdf38fe7ec8adaaa3e5fb172763fd1` | `8c3b2eafb14a39a2cb4c4b820d05bb281874793a6ee12e7327f648faaa54da00` | 72261 |
| 2 — smoke-v2 actually-transmitted verbatim | `outputs/image_frames/cgas-phase3-planimation-regression-replay-02-20260811` | failed | `f5e8e79e7c594b2ffa83906825016d7c368893abb3b1009dea277d367b81daa9` | — | — |
| 3 — canonicalized pilot delta | `outputs/image_frames/cgas-phase3-planimation-regression-replay-03-20260811` | success | `8a27cbb59978e68e9a48a1770d7852d0ad91b33e5af98643dea578c210244549` | `337b988571ba3127c4d8a63fc99e2ea2fb77938d6e30bef95bf0199350dc1c64` | 20655 |
| 4 — 12-object empty goal | `outputs/image_frames/cgas-phase3-planimation-regression-replay-04-20260811` | failed | `a4376855d9f032efbdcb6db2bbf13505b39fa741e30ab0290f5d2a963a48bb64` | — | — |

### Replay 1 — exact July-22 known-good (success)

- Problem: exact-byte copy of the July-22 derived problem at cache key
  `e02d4b71c070add447b722ecda732979` (`blocksworld-train-medium-0034`), SHA
  `0e7f043f…763fd1`.
- Trace: `8c3b2eafb14a39a2cb4c4b820d05bb281874793a6ee12e7327f648faaa54da00`, 72,261 bytes,
  persisted at `…/replay-01-20260811/trace.vfg.json`.
- Interpretation: the exact bundle that rendered successfully on 2026-07-22 renders successfully
  today. There is no blanket upstream regression or outage.

### Replay 2 — exact actually-transmitted smoke-v2 (failed)

- Problem: exact-byte copy of the problem actually POSTed by the 2026-08-11 mapping-bound smoke
  (`outputs/image_frames/cgas-phase3-pilot-planimation-adapter-smoke-v2/state_cache/blocksworld/
  0322c69e…/341bb4e2…/problem.pddl`), SHA `f5e8e79e…81daa9`. This is NOT the `df2f5c26…`
  candidate problem, which is retained in the bundle under `reference/` and labeled
  NOT-TRANSMITTED.
- Exact exception: `Failed to submit PDDL bundle. Attempts: https://planimation.planning.domains/upload/pddl -> API error: The process ends with an exception \n\n Unexpected status from the server`.
- Interpretation: the repository's smoke-v2 problem-writer output still fails at the remote
  planner boundary.

### Replay 3 — canonicalized pilot delta (success)

- Problem: same semantic init (12 atoms) and goal (5 atoms) as replay 2, with the bijective rename
  `b00..b07 → b1..b8` and July-compatible formatting (two leading blank lines; `(define` at column
  1; `(:objects b1 … b8 )`; two-space init atoms; goal atoms at column 1; two trailing blank
  lines), SHA `8a27cbb5…4549`.
- Trace: `337b988571ba3127c4d8a63fc99e2ea2fb77938d6e30bef95bf0199350dc1c64`, 20,655 bytes,
  persisted at `…/replay-03-20260811/trace.vfg.json`.
- Interpretation: with semantic init/goal preserved and only naming/formatting changed, the same
  state renders successfully. This proves a repository-side remote compatibility delta: the
  difference between replay 2 (fail) and replay 3 (success) is exactly the compound change of
  object naming and problem formatting. The probe changed BOTH together, so which one alone is
  causal is NOT established.

### Replay 4 — 12-object empty goal (failed)

- Problem: 12-object problem (`b00..b11`) with the 16 ordered init atoms of representative state
  `0002870c7b4fc6cd2c137f636c641655ec1f9addf7679404671df53f7d02ea51` (candidate
  `ca6fb5aa595c065744e0172f1b50d4e237bd4c851d094de684127a240cd3e85d`, row
  `cgas-pilot-expansion-347abc61e3ddea26d65eed27`, source_record_sha256 `eb8d5b84…7073`) and goal
  exactly `(:goal (and))`, SHA `a4376855…bb64`.
- Exact exception: `Failed to submit PDDL bundle. Attempts: https://planimation.planning.domains/upload/pddl -> API error: Failed to generate stages \n\n 'init'`.
- Interpretation: this does NOT prove 12-object incompatibility. The failure occurred later, at
  stage generation, and names `'init'` — consistent with the empty goal, not with object count.
  12-object compatibility remains unproven either way.

## Classification

- **Blanket upstream regression/outage: REFUTED.** Replay 1 succeeds today with the exact July-22
  bundle.
- **Repository-side remote compatibility delta: PROVEN.** Replay 2 fails and replay 3 succeeds with
  semantic init/goal preserved. The delta is the compound change of `b00..b07 → b1..b8` naming and
  July-compatible formatting. Causality of naming vs formatting alone is NOT claimed — both were
  changed together.
- **12-object incompatibility: NOT PROVEN.** Replay 4's empty-goal probe failed later at
  `Failed to generate stages / 'init'`; object count is not isolated.

## Required next implementation (not started)

- Patch the adapter/problem writer to emit canonical `b1..bN` object naming and July-compatible
  problem formatting under RED→GREEN tests, then independent code review and the focused /
  regression / Ruff / basedpyright gates. This is the next implementation step; it is NOT done in
  this session and no code was changed.
- Before any production render: require a canonicalized mapping-bound 8-object smoke AND a
  12-object smoke with a NON-EMPTY locally solvable representative goal, each passing full
  VFG→PNG→semantic/digest/provenance validation.
- Production 16,822-state rendering and the 790-row replay alignment remain unstarted. The
  operator command must NOT be authorized/resumed until the writer patch plus both valid smokes.

## Evidence

- Staging root (immutable inputs): `tmp/cgas-phase3-planimation-regression-replays-20260811/`
  (27-file `SHA256SUMS` verified; four bundle directories with `bundle.json`, `command.txt`,
  verbatim inputs, and `expected/`).
- Result roots (authoritative outcomes): `outputs/image_frames/cgas-phase3-planimation-regression-replay-01..04-20260811/result.json`.
- Trace outputs: `…/replay-01-20260811/trace.vfg.json`, `…/replay-03-20260811/trace.vfg.json`.
- Handoff: `.handoff/2026-08-11-cgas-phase3-planimation-replay-classification.md`.
