# Phase 3 F2 Pairing And Release Modularization

## Scope

The legacy pairing implementation was divided into focused modules while retaining `scripts/phase3/planimation_pairing.py` as the public compatibility facade. The release verifier now has a small CLI facade, orchestration module, and typed validation helper module.

## Design

- `planimation_pairing_implementation.py` remains the compatibility aggregator and forwards source-loader monkeypatch hooks to both the source and manifest boundaries before public operations.
- Source provenance, compact reasoning, JSON schema construction, rendering/cache validation, manifest construction, replay transition rendering, VLM record production, and output validation live in separate pairing modules.
- Release orchestration is in `planimation_release_verification.py`; JSONL/JSON loading, schema, artifact, and coverage checks are in `planimation_release_validation.py`.
- JSON payload annotations use `JSONValue`, replacing active pairing `Any` boundaries. Copy-extraction imports were removed so each split module only imports dependencies it uses.

## Verification

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3/planimation_pairing*.py scripts/phase3/planimation_release*.py
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright scripts/phase3/planimation_pairing*.py scripts/phase3/planimation_release*.py
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_planimation_pairing.py tests/phase3/test_verify_planimation_vlm.py -q
```

Results: compilation passed, basedpyright reported `0 errors, 0 warnings, 0 notes`, and the focused suite reported `53 passed in 8.20s`.

The release CLI was exercised against a generated complete fixture:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/verify_planimation_vlm.py --output-root <generated-fixture-root> --mode release
```

It returned exit code 0 with one pairing record, four rendered states, one train full record, one train step record, and two train search-traversal records. Temporary fixture artifacts were removed after the check.

All active pairing and release modules remain below 250 lines. `git diff --check` and LSP diagnostics for each changed module passed cleanly.

## Follow-Up: Rollout JSON Contracts

`scripts/phase3/io_utils.py` now has a narrow `JSONValue`/`JSONRecord` boundary. `read_jsonl` rejects any non-object row with a controlled path-and-line error, while `read_json_object` provides the same object contract for selection and promotion receipt files. `write_jsonl` and `write_json` accept only object records; `stable_hash` remains intentionally capable of hashing all JSON values.

`prepare_selection` validates every persisted pairing record through `validate_pair_record` before filtering eligibility, sorting, counting transitions, or writing `rollout_selection.json`. This rejects boolean integers and unsupported active planner identities such as legacy `bfs` at selection time, rather than leaving rejection to the release verifier. Selection arithmetic no longer calls `int(...)` on persisted values.

Direct facade tests monkeypatch `_source_jsonl_rows` and `_source_root_snapshot`, then run `render_replay_states` and `build_vlm_records` through `planimation_pairing`; each underlying workflow observes both forwarded hooks.

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_rollout_gates.py::test_prepare_selection_rejects_invalid_persisted_pairs_without_receipt tests/phase3/test_rollout_gates.py::test_prepare_selection_rejects_non_object_jsonl_rows_without_receipt tests/phase3/test_planimation_pairing.py::test_pairing_facade_forwards_source_index_hooks_to_render_and_vlm_workflows -q
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_rollout_gates.py tests/phase3/test_planimation_pairing.py tests/phase3/test_verify_planimation_vlm.py tests/phase3/test_render_semantics.py -q
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright scripts/phase3/io_utils.py scripts/phase3/rollout_gates.py tests/phase3/test_rollout_gates.py tests/phase3/test_planimation_pairing.py
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3/io_utils.py scripts/phase3/rollout_gates.py tests/phase3/test_rollout_gates.py tests/phase3/test_planimation_pairing.py
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/verify_planimation_vlm.py --output-root tmp/f1_search_traversal_release_surface --mode release
git diff --check
```

Results: adversarial and facade tests `4 passed in 0.28s`; focused suite `67 passed in 6.99s`; basedpyright `0 errors, 0 warnings, 0 notes`; compileall exit `0`; release verification exited `0` with one pairing record, four state-render records, one train full record, one train step record, and two train search-traversal records; diff check passed.

## Follow-Up: Rollout Gate Structural Compliance

The F2 pure-LOC measure reported `263` for `scripts/phase3/rollout_gates.py`, so the monolithic gate was split into a compatibility/CLI facade, shared immutable contracts, deterministic strict selection, and promotion/receipt validation. The facade retains `prepare_selection`, `assess_promotion`, `PromotionDecision`, `Stage`, `STAGES`, exact CLI commands/options/exit behavior, and the monkeypatchable `verify_output` seam used by focused tests.

Measured with:

```bash
awk '!/^[[:space:]]*$/ && !/^[[:space:]]*(#|"""|\047\047\047)/' scripts/phase3/rollout_gates.py | wc -l
awk '!/^[[:space:]]*$/ && !/^[[:space:]]*(#|"""|\047\047\047)/' scripts/phase3/rollout_gate_contracts.py | wc -l
awk '!/^[[:space:]]*$/ && !/^[[:space:]]*(#|"""|\047\047\047)/' scripts/phase3/rollout_gate_selection.py | wc -l
awk '!/^[[:space:]]*$/ && !/^[[:space:]]*(#|"""|\047\047\047)/' scripts/phase3/rollout_gate_promotion.py | wc -l
```

Final pure-LOC results are `32`, `31`, `134`, and `144`, respectively. All changed active rollout modules comply with the <=250 limit.

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_rollout_gates.py tests/phase3/test_planimation_pairing.py tests/phase3/test_verify_planimation_vlm.py tests/phase3/test_render_semantics.py -q
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright scripts/phase3/rollout_gates.py scripts/phase3/rollout_gate_contracts.py scripts/phase3/rollout_gate_selection.py scripts/phase3/rollout_gate_promotion.py tests/phase3/test_rollout_gates.py tests/phase3/test_planimation_pairing.py
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3/rollout_gates.py scripts/phase3/rollout_gate_contracts.py scripts/phase3/rollout_gate_selection.py scripts/phase3/rollout_gate_promotion.py tests/phase3/test_rollout_gates.py tests/phase3/test_planimation_pairing.py
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/rollout_gates.py --help
git diff --check
```

Results: focused suite `67 passed in 6.82s`; basedpyright `0 errors, 0 warnings, 0 notes`; compilation and diff check passed; direct CLI help listed `prepare` and `assess`.
