# F2 Rollout JSON Contract Remediation

## Scope

Phase 3 JSONL ingress now accepts object rows only. Rollout selection validates every persisted pairing row with `validate_pair_record` before eligibility filtering, counting, or writing a selection receipt.

## Adversarial Results

- `plan_length=true` was rejected with `pair plan_length must be an integer`; no `rollout_selection.json` was written.
- `planner="bfs"` was rejected with `pair planner is unsupported`; no `rollout_selection.json` was written.
- A JSONL array row was rejected with `JSONL row must be an object`; no `rollout_selection.json` was written.
- Facade render and VLM workflows each executed monkeypatched `_source_jsonl_rows` and `_source_root_snapshot` exactly once.

## Commands And Results

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_rollout_gates.py::test_prepare_selection_rejects_invalid_persisted_pairs_without_receipt tests/phase3/test_rollout_gates.py::test_prepare_selection_rejects_non_object_jsonl_rows_without_receipt tests/phase3/test_planimation_pairing.py::test_pairing_facade_forwards_source_index_hooks_to_render_and_vlm_workflows -q
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_rollout_gates.py tests/phase3/test_planimation_pairing.py tests/phase3/test_verify_planimation_vlm.py tests/phase3/test_render_semantics.py -q
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright scripts/phase3/io_utils.py scripts/phase3/rollout_gates.py tests/phase3/test_rollout_gates.py tests/phase3/test_planimation_pairing.py
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3/io_utils.py scripts/phase3/rollout_gates.py tests/phase3/test_rollout_gates.py tests/phase3/test_planimation_pairing.py
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/verify_planimation_vlm.py --output-root tmp/f1_search_traversal_release_surface --mode release
git diff --check
```

Results: adversarial and facade regression `4 passed in 0.28s`; focused suite `67 passed in 6.99s`; basedpyright `0 errors, 0 warnings, 0 notes`; compileall exit `0`; release verification reconciled one pair, four state renders, one full record, one step record, and two search-traversal records; diff check passed.

## Structural Follow-Up

The documented pure-LOC command reported `263` for the original `rollout_gates.py`, exceeding the F2 ceiling. The module was split without changing its public imports or CLI:

- `rollout_gates.py`: `32` pure LOC, compatibility facade and CLI.
- `rollout_gate_contracts.py`: `31` pure LOC, stages and promotion decision contract.
- `rollout_gate_selection.py`: `134` pure LOC, strict pair validation and deterministic selection.
- `rollout_gate_promotion.py`: `144` pure LOC, frozen-selection, prior-receipt, release, and promotion validation.

The facade forwards its module-level `verify_output` to promotion assessment, preserving the existing test monkeypatch seam and direct `python scripts/phase3/rollout_gates.py` behavior.

```bash
awk '!/^[[:space:]]*$/ && !/^[[:space:]]*(#|"""|\047\047\047)/' scripts/phase3/rollout_gates.py | wc -l
awk '!/^[[:space:]]*$/ && !/^[[:space:]]*(#|"""|\047\047\047)/' scripts/phase3/rollout_gate_contracts.py | wc -l
awk '!/^[[:space:]]*$/ && !/^[[:space:]]*(#|"""|\047\047\047)/' scripts/phase3/rollout_gate_selection.py | wc -l
awk '!/^[[:space:]]*$/ && !/^[[:space:]]*(#|"""|\047\047\047)/' scripts/phase3/rollout_gate_promotion.py | wc -l
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_rollout_gates.py tests/phase3/test_planimation_pairing.py tests/phase3/test_verify_planimation_vlm.py tests/phase3/test_render_semantics.py -q
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright scripts/phase3/rollout_gates.py scripts/phase3/rollout_gate_contracts.py scripts/phase3/rollout_gate_selection.py scripts/phase3/rollout_gate_promotion.py tests/phase3/test_rollout_gates.py tests/phase3/test_planimation_pairing.py
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3/rollout_gates.py scripts/phase3/rollout_gate_contracts.py scripts/phase3/rollout_gate_selection.py scripts/phase3/rollout_gate_promotion.py tests/phase3/test_rollout_gates.py tests/phase3/test_planimation_pairing.py
git diff --check
```

Results: all rollout modules are below 250 pure LOC; focused suite `67 passed in 6.82s`; basedpyright `0 errors, 0 warnings, 0 notes`; compileall exit `0`; diff check passed.
