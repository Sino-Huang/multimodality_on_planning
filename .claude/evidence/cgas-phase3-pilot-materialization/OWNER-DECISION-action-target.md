# Owner Decision Required: Off-Plan Action Targets

Status: unapproved

The verified pilot source index contains 31,171 expansion events. Of these, 30,381 are off-plan-only events. Each event preserves all trace successors/actions and an exact planner certificate, but an off-plan event can expose multiple valid successors and no approved artifact identifies one authoritative action target.

The current `planning_cgas_v1` and Qwen contracts require exactly one `action_target` per training row. Therefore, the source index must not be projected into those schemas until one policy is approved.

## Decision options

1. Emit one training row per valid successor action.
2. Approve a deterministic single-successor selection rule.
3. Restrict action-plus-certificate rows to the 790 replay-plan events and use the 30,381 off-plan-only events for certificate calibration without action supervision.

Recommendation: option 3 is the smallest policy change and retains replay-authoritative actions. Options 1 and 2 change the scientific target and need an explicit rationale plus new no-oracle tests.
