# Phase 3 F2 Controlled Cardinality Failure Contract

## Change

`render_replay_states` retains its controlled malformed-plan diagnostic, and the persisted contract now recognizes `failure_kind=render_cardinality_invalid` as an exact compact failed-state variant. The variant deliberately carries no invented transition, state hash, cache, renderer, or artifact metadata because transition construction did not occur.

Release validates that row successfully, then rejects the incomplete artifact at render coverage reconciliation. This preserves fail-closed release behavior while ensuring emitted rows satisfy their own persisted contract.

## Verification

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_planimation_pairing.py::test_invalid_plan_cardinality_emits_a_controlled_failed_state_row tests/phase3/test_verify_planimation_vlm.py::test_release_handles_a_valid_controlled_failed_state_row tests/phase3/test_verify_planimation_vlm.py::test_release_rejects_mixed_state_render_variants -q
```

Result: `3 passed in 0.84s`.

## Scope

This evidence covers only the self-invalid failed-state finding. Pairing/release module decomposition and complete JSON-boundary remediation remain separate required F2 work.
