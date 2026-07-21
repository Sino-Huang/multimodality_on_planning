# Phase 3 Graphplan Safe Replay Boundary

Date: 2026-07-15

## Scope

Todo 5 separates nonvisual Graphplan planning-graph semantics from concrete replay candidates. It does not alter Graphplan solving, Planimation rendering/cache behavior, source roots, or later cardinality/render gates.

## Implementation

- `scripts/phase3/trace_contracts.py` preserves proposition layers, action layers, mutex, and extraction as `planner_semantics`. Semantic payloads reject state, asset, frame, and render-eligibility fields. Extraction cannot supply forged replay-parent linkage.
- `scripts/phase3/graphplan_replay.py` consumes only the extraction event's validated `selected_plan`. It normalizes and grounds every action, checks applicability from PDDL init, requires the final PDDL goal, then emits the full replay chain atomically.
- `scripts/phase3/traversal_state_types.py` introduces the shared candidate boundary. Graphplan states use `state_source="extracted_plan_replay"`, retain frozen provenance, expose `extraction_event_id` and step index, and parent each successor to the preceding replay event.
- Semantic Graphplan records become controlled exclusions in the candidate report. Invalid extraction plans produce one controlled exclusion and zero candidates, so they cannot advance to a render job.

## Verification Commands

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_planimation_pairing.py tests/phase3/test_traversal_trace_contracts.py tests/phase3/test_traversal_state_projection.py -q
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright scripts/phase3/trace_contracts.py scripts/phase3/traversal_state_types.py scripts/phase3/graphplan_replay.py scripts/phase3/traversal_states.py scripts/phase3/traversal_state_projection_cli.py tests/phase3/test_traversal_trace_contracts.py tests/phase3/test_traversal_state_projection.py
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3/trace_contracts.py scripts/phase3/traversal_state_types.py scripts/phase3/graphplan_replay.py scripts/phase3/traversal_states.py scripts/phase3/traversal_state_projection_cli.py tests/phase3/test_traversal_trace_contracts.py tests/phase3/test_traversal_state_projection.py
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.trace_contracts --fixtures tests/phase3/fixtures/traversal_trace_contract_cases.json --report tmp/phase3_task5_trace_event_report.json
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.traversal_state_projection_cli --fixtures tests/phase3/fixtures/traversal_state_projection_cases.json --domain tests/phase3/fixtures/traversal_state_domain.pddl --problem tests/phase3/fixtures/traversal_state_problem.pddl --report tmp/phase3_task5_graphplan_replay_report.json
```

Observed results: RED began at `4 failed, 15 passed`. The final focused regression passed `40 passed in 0.38s`; basedpyright reported `0 errors, 0 warnings, 0 notes`; compilation exited zero. The trace-event CLI projected three Graphplan semantic events, while the replay CLI emitted exactly two linked `extracted_plan_replay` candidates and excluded the proposition/action layers. A fake-renderer smoke injected forged raw Graphplan replay atoms and observed the validated extracted pre-action state instead.
