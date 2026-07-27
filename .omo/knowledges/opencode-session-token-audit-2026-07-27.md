# OpenCode Session Token Audit - 2026-07-27

## Scope

- Audited active OpenCode session `ses_09964dc0cfferuEvG3FH5an6BT`.
- The active process uses repository-local state through `env.sh`:
  `XDG_DATA_HOME=$PWD/.cache/xdg`.
- Authoritative database: `.cache/xdg/opencode/opencode.db`.

## Findings

- Session tree: 123 sessions total, 122 descendants, maximum depth 2.
- Estimated local cost: 205.274379 total; root session: 156.108333; descendants: 49.166046.
- Token counters for the full tree: 34,452,749 input; 1,213,388 output; 560,868 reasoning; 270,436,096 cache reads.
- The root session alone recorded 17,133,034 input tokens and 174,362,880 cache-read tokens.
- The tree contains 2,681 assistant messages, 316 user messages, 8,614 tool parts, and 28 compaction parts.
- Logs recorded 78 direct child-agent launches, 25 root compactions, and 30 stopped parent-wake retries across the retained log files.

## Cause

- `oh-my-openagent@latest` is enabled in the user OpenCode configuration.
- Its configuration permits `background_task.maxDescendants: 300` and enables team mode.
- This session used broad agent fan-out: 80 direct `explore` sessions, 21 nested `explore` sessions, and several planning, review, oracle, librarian, and multimodal sessions.

## Interpretation

- The high token/cost figure is real; it is not only a UI counter issue.
- Cache-read tokens are tracked separately from uncached input and may be charged at a reduced provider rate. The local estimated cost already distinguishes this, but quota treatment depends on the provider plan.
- The primary cause is long-lived context plus automated multi-agent orchestration. The parent-wake retries may add overhead, but the audit cannot establish that every retry produced a billable model response.
