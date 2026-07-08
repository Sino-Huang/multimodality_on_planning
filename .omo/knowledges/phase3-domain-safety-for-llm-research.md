# Phase 3 Domain Safety for LLM Research

## Recommendation

For LLM planning-trace research with the current local Phase 3 planners, prefer medium/easy subsets from `blocksworld`, `elevators`, `ferry`, `gripper`, `logistics`, `towers_of_hanoi`, and `visitall`. Treat `15puzzle` as easy-only or exclude it if the research needs broad algorithm coverage. Do not use hard domains as a broad full-trace corpus without trace compression, and keep the Phase 3 timeout defaults enabled.

## Evidence

- Medium one-domain probe evidence recorded in `doc/detailed_implementation_summary/phase3_medium_trace_generation_fix.md` reports all-four local planner success for `blocksworld`, `elevators`, `ferry`, `gripper`, `logistics`, `towers_of_hanoi`, and `visitall`.
- The same medium note says `15puzzle`, `depot`, `driverlog`, `freecell`, `grid`, and `storage` still need lifted planning, domain heuristics, or stronger search to avoid broad timeouts.
- `snake` and `sokoban` remain unsupported by the current local parser: `snake` needs negative preconditions, and `sokoban` needs equality/quantifiers.
- Hard one-per-domain safe-batch evidence in `.omo/knowledges/phase3-hard-one-per-domain-config-investigation.md` found only two hard successes out of 60 planner attempts: Graphplan for `elevators-dev-hard-0000` and Graphplan for `towers_of_hanoi-dev-hard-0000`.
- Hard failure classes were unsupported PDDL (`snake`, `sokoban`), grounding explosion (`depot`, `freecell`, `grid`, `logistics`, `storage`), and search/runtime explosion (`15puzzle`, `blocksworld`, `driverlog`, `elevators`, `ferry`, `gripper`, `towers_of_hanoi`, `visitall`).
- LLM context-window risk is real even for successful medium traces. `README.md` records that `blocksworld-train-medium-0011` has a 10-action final plan but raw traces can be much larger: GBFS remains frontier-heavy, FF-style is about 32k-37k estimated tokens, Graphplan about 461k-527k, and IW(3) about 2.57M-2.93M.

## Domain Categories

- Recommended core: `blocksworld`, `elevators`, `ferry`, `gripper`, `logistics`, `towers_of_hanoi`, `visitall` on easy/medium subsets, with trace-size filtering.
- Conditional/easy-only: `15puzzle`; first-ten easy evidence exists, but medium/hard attempts can occupy workers for a long time and are not safe for most search algorithms.
- Diagnostic only unless backend improves: `depot`, `driverlog`, `freecell`, `grid`, `storage`.
- Exclude for current local traces: `snake`, `sokoban` until parser support is extended.
- Avoid as broad full-trace corpus: all hard buckets under the current local helper.

## Operational Guidance

- Keep the implemented timeout defaults enabled for broad generation: `--planner-attempt-timeout-seconds 1200` and `--domain-timeout-seconds 3600`.
- Timed-out attempts are recorded as `failed_planner_timeout` with `resource_gate: planner_attempt_timeout`; after a domain accumulates the budget, later same-domain attempts are `skipped_resource_limit` with `resource_gate: domain_timeout_budget`.
- The parallel runner reserves in-flight timeout budget before launching worker processes, so increasing `--jobs` should improve throughput without allowing a single risky domain to exceed the configured accumulated timeout budget. Reservation saturation defers same-domain jobs; actual accumulated timeouts, not reservations, trigger domain skips.
- Timed-out attempt workers are killed as a process group, so planner subprocesses launched inside the attempt are also terminated instead of continuing to consume CPU after the parent records the timeout.
- External planner subprocesses are also launched in a process group and group-killed on their own `planner_timeout`. If the parent attempt timeout fires first, the worker SIGTERM cleanup kills the active external planner process group before exiting.
- Even with timeouts, avoid running all easy+medium all-four planners unattended on risky domains unless the output is explicitly a stress-test; `15puzzle` medium and `visitall` can still consume the full timeout budget.
- If `15puzzle` is not central to the research question, exclude it from the broad corpus and keep it only as a stress-test appendix.
- For LLM training/evaluation, filter by trace size or summarize traces with external memory/retrieval rather than feeding raw IW/Graphplan traces directly.
