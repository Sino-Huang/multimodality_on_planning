# Phase 3 Concrete Traversal State Projection

Date: 2026-07-15

## Scope

Todo 4 adds provenance-safe concrete traversal-state candidates for strict FF, GBFS, and IW traces. It does not render frames, alter cache/archive behavior, change Graphplan semantics, or mutate dataset outputs.

## Implementation

- `scripts/phase3/traversal_states.py` projects strict concrete events into candidates whose event IDs include frozen root, JSONL location, physical line, Todo 2 node ID, and candidate role. The content-addressed `state_asset_hash` is intentionally separate from the event ID.
- FF selected and recorded-successor states are retained only after their normalized action deterministically reproduces the recorded successor atoms. GBFS and IW selected states are recorded directly; their successor states are reconstructed from the validated parent state by normalized-action lookup, precondition checking, delete effects, then add effects.
- Unknown, malformed, inapplicable, atom-mismatched, unsupported-PDDL, non-concrete, and strict-contract-invalid sources are exclusion records, never candidates. Duplicate successor payloads are collapsed only when the entire payload is identical, so conflicting action records retain distinct graph semantics.
- `scripts/phase3/traversal_state_projection_cli.py` writes a deterministic fixture projection report without rendering or writing under `outputs/`.

## Verification Commands

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_traversal_state_projection.py tests/phase3/test_traversal_trace_contracts.py tests/phase3/test_planimation_pairing.py -q
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright scripts/phase3/traversal_states.py scripts/phase3/traversal_state_projection_cli.py tests/phase3/test_traversal_state_projection.py
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3/traversal_states.py scripts/phase3/traversal_state_projection_cli.py tests/phase3/test_traversal_state_projection.py
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.traversal_state_projection_cli --fixtures tests/phase3/fixtures/traversal_state_projection_cases.json --domain tests/phase3/fixtures/traversal_state_domain.pddl --problem tests/phase3/fixtures/traversal_state_problem.pddl --report tmp/phase3_task4_traversal_projection_report.json
```

Observed results: focused tests `31 passed in 0.33s`; basedpyright `0 errors, 0 warnings, 0 notes`; compilation exited `0`; the CLI projected two candidates each for nonzero-plan FF, GBFS, and IW fixtures with no exclusions.

## Frozen-Root Observation

A read-only smoke of one nonzero-plan FF, GBFS, and IW row from `outputs/phase3_curriculum_traces_15puzzle_easy_20260709_002417` yielded `missing_required_field: trace_contract_version` for each row. This is the expected Todo 2 controlled exclusion for legacy rows, so no compatibility alias or inferred state was added.

## Semantic Label Correction

Concrete parent events and successor records now require an explicit `event_kind` from `expansion`, `generation`, `revisit`, or `backtrack`. The strict adapter validates the field before state projection, and candidates copy successor semantics rather than inheriting the parent event kind. Missing or unsupported labels are controlled strict-contract exclusions. Local FF, GBFS, and IW emitters write the required labels without changing search behavior; IW prune events explicitly record `backtrack`.

The fixture case `gbfs_semantic_repeat` records valid PDDL transitions with equal successor state assets and reports `expansion`, `generation`, `revisit`, and `backtrack` as distinct candidate event kinds.

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_traversal_state_projection.py tests/phase3/test_traversal_trace_contracts.py tests/phase3/test_planimation_pairing.py tests/phase3/test_phase3_gbfs.py tests/phase3/test_phase3_local_trace_safety.py tests/phase3/test_phase3_pipeline_regressions.py -q
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright scripts/phase3/trace_contracts.py scripts/phase3/traversal_states.py scripts/phase3/traversal_state_projection_cli.py scripts/phase3/gbfs.py scripts/phase3/local_iw.py scripts/phase3/local_planners.py tests/phase3/test_traversal_state_projection.py tests/phase3/test_traversal_trace_contracts.py tests/phase3/test_planimation_pairing.py
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3/trace_contracts.py scripts/phase3/traversal_states.py scripts/phase3/traversal_state_projection_cli.py scripts/phase3/gbfs.py scripts/phase3/local_iw.py scripts/phase3/local_planners.py tests/phase3/test_traversal_state_projection.py tests/phase3/test_traversal_trace_contracts.py tests/phase3/test_planimation_pairing.py
```

Observed result: `58 passed in 1.10s`; basedpyright had `0 errors, 0 warnings, 0 notes`; compilation exited `0`.
