# Phase 3 F1 Search Traversal Remediation

## Delivered

- The Planimation pairing pipeline now converts only strict, concrete FF, GBFS, and IW traversal candidates into `search_traversal_<split>.jsonl` records.
- `plan_replay` remains in the existing full and step record families. Traversal records preserve distinct candidate event IDs while reusing a state cache only by validated state content.
- The new record family has a persisted closed schema and is required, type-checked, artifact-checked, counted, and coverage-reconciled by release verification.
- FF successors without recorded `state_atoms` are excluded. PDDL reconstruction remains limited to GBFS and IW.
- Graphplan proposition/action/mutex layers remain nonvisual. They never emit `search_traversal` records.
- Pairing rejects output roots that equal or are nested below selected immutable source roots before any output write.

## Fixture Boundary

The release evidence uses temporary strict-v1 fixtures only. The active corpus is still blocked because its frozen source rows lack `phase3_traversal_trace_v1`; this remediation neither modifies those roots nor claims canary or corpus promotion.

## Verification Commands

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_planimation_pairing.py tests/phase3/test_planimation_search_traversal.py tests/phase3/test_traversal_state_projection.py tests/phase3/test_verify_planimation_vlm.py tests/phase3/test_rollout_gates.py -q
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright scripts/phase3/planimation_pairing.py scripts/phase3/traversal_states.py scripts/phase3/verify_planimation_vlm.py scripts/phase3/rollout_gates.py tests/phase3/test_planimation_pairing.py tests/phase3/test_planimation_search_traversal.py tests/phase3/test_traversal_state_projection.py tests/phase3/test_verify_planimation_vlm.py tests/phase3/test_rollout_gates.py
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3/planimation_pairing.py scripts/phase3/traversal_states.py scripts/phase3/verify_planimation_vlm.py scripts/phase3/rollout_gates.py tests/phase3/test_planimation_pairing.py tests/phase3/test_planimation_search_traversal.py tests/phase3/test_traversal_state_projection.py tests/phase3/test_verify_planimation_vlm.py tests/phase3/test_rollout_gates.py
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/verify_planimation_vlm.py --output-root tmp/f1_search_traversal_release_surface --mode release
```

Observed results: 66 tests passed in 6.29 seconds, basedpyright returned zero findings, compilation exited zero, and release reconciliation reported one pair, four state-render rows, one train full record, one train step record, and two train search-traversal records.
