# F2 Independent Code-Quality Review

## Verdict

REJECT

## Blocking Findings

1. `scripts/phase3/planimation_pairing_implementation.py:445-452` accepts booleans for pair-manifest integer fields. `validate_pair_record()` calls `int(record.get(...))`, and Python treats `True` as `1`. A copied fixture release with both `plan_length` and `trace_size_chars` set to `true` was accepted by the real `verify_output(..., "release")` boundary.
2. `scripts/phase3/planimation_pairing_implementation.py:455-466` does not enforce concrete primitive types for `state_render_manifest.jsonl`. A copied fixture release with state-render `step_index` set to `true` was accepted by the real release verifier.
3. `scripts/phase3/planimation_pairing_implementation.py:14,56,69-115,419,445-469,817-922` uses pervasive `Any` and `dict[str, Any]` at the active pairing, rendering, schema-validation, and release-contract boundary. This violates the required strict Python contract review standard and is the mechanism that allows the two tested primitive contract bypasses.

## Independent Inspection

- Used `codegraph_explore` first to trace Phase 3 facades, traversal contract projection, render semantics, verifier, archive validation, and their dynamic import boundary.
- Used `codegraph_node` on the facades, pairing implementation, Phase 1 facade and components, renderer facade/components, archive extractor, trace contracts, release verifier, generator CLI, and focused tests.
- Facade compatibility is intact: `src.data_collect.rendering`, `scripts.planimation_phase1`, and `scripts.phase3.planimation_pairing` export all required legacy symbols. The direct import probe returned all three groups as `True`.
- Strict trace and hybrid-record schemas reject the covered nested scalar/object/array defects. `trace_contracts.py` explicitly rejects planner aliases and bool-as-int values. The problem is the separate pair/state manifest validation boundary that release trusts.
- The pair implementation remains 1,028 pure lines, above the project 250 LOC ceiling. This is a structural review concern, but the two primitive-type release bypasses above independently require rejection.

## Commands And Results

All Python commands used the mandated environment prefix:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/data_collect/test_rendering.py tests/data_collect/test_imports.py tests/test_planimation_phase1.py tests/phase3/test_planimation_pairing.py tests/phase3/test_planimation_search_traversal.py tests/phase3/test_render_semantics.py tests/phase3/test_traversal_state_projection.py tests/phase3/test_traversal_trace_contracts.py tests/phase3/test_verify_planimation_vlm.py tests/phase3/test_rollout_gates.py -q
```

Result: `113 passed in 7.57s`.

```bash
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright scripts/phase3/planimation_pairing.py scripts/phase3/planimation_pairing_implementation.py scripts/phase3/generate_planimation_vlm.py scripts/phase3/trace_contracts.py scripts/phase3/traversal_state_types.py scripts/phase3/traversal_states.py scripts/phase3/graphplan_replay.py scripts/phase3/render_semantics.py scripts/phase3/verify_planimation_vlm.py scripts/planimation_phase1.py scripts/planimation_phase1_client.py scripts/planimation_phase1_frames.py scripts/planimation_phase1_manifest.py scripts/planimation_phase1_runner.py src/data_collect/rendering.py src/data_collect/render_archive.py src/data_collect/render_backends.py src/data_collect/render_gates.py src/data_collect/render_types.py tests/data_collect/test_rendering.py tests/data_collect/test_imports.py tests/test_planimation_phase1.py tests/phase3/test_planimation_pairing.py tests/phase3/test_planimation_search_traversal.py tests/phase3/test_render_semantics.py tests/phase3/test_traversal_state_projection.py tests/phase3/test_traversal_trace_contracts.py tests/phase3/test_verify_planimation_vlm.py tests/phase3/test_rollout_gates.py
```

Result: `0 errors, 0 warnings, 0 notes`.

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3 scripts/planimation_phase1.py scripts/planimation_phase1_client.py scripts/planimation_phase1_frames.py scripts/planimation_phase1_manifest.py scripts/planimation_phase1_runner.py src/data_collect/rendering.py src/data_collect/render_archive.py src/data_collect/render_backends.py src/data_collect/render_gates.py src/data_collect/render_types.py tests/data_collect/test_rendering.py tests/data_collect/test_imports.py tests/test_planimation_phase1.py tests/phase3/test_planimation_pairing.py tests/phase3/test_planimation_search_traversal.py tests/phase3/test_render_semantics.py tests/phase3/test_traversal_state_projection.py tests/phase3/test_traversal_trace_contracts.py tests/phase3/test_verify_planimation_vlm.py tests/phase3/test_rollout_gates.py
```

Result: exit `0`.

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/verify_planimation_vlm.py --output-root tmp/f1_search_traversal_release_surface --mode release
```

Result: exit `0`; reconciled one pair, four state renders, one train full record, one train step record, and two train search-traversal records.

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.trace_contracts --fixtures tests/phase3/fixtures/traversal_trace_contract_cases.json --report /tmp/f2_trace_contract_report.json
```

Result: four valid fixtures projected; four malformed fixtures excluded with controlled missing-field reasons.

LSP diagnostics were clean for the pairing facade/implementation, trace contract, release verifier, rendering facade, archive extractor, and the focused pairing/rendering tests.

## Adversarial Probes

| Probe | Result |
|---|---|
| ZIP `../../escape.png` | Rejected: `unsafe archive member: ../../escape.png`; no outside write. |
| ZIP symlink member | Rejected: `unsafe archive member: link.png`. |
| Non-PNG archive member | Rejected: `unsafe archive member: not-png.txt`. |
| 129 PNG members | Rejected: `archive member count is outside the allowed bound`. |
| High compression-ratio member | Rejected: `unsafe archive member: compressed.png`. |
| `bfs` planner / unsupported trace version | Focused contract tests passed: controlled strict rejection, no alias fallback. |
| Pair `plan_length=true`, `trace_size_chars=true` copied fixture release | **Unexpectedly accepted** by `verify_output(..., "release")`. |
| State render `step_index=true` copied fixture release | **Unexpectedly accepted** by `verify_output(..., "release")`. |

## Tooling Limitation

The `ast-grep` binary is absent. `ast-grep --version` was not found and `/usr/bin/sg` is the system `setgroups` command, not AST-grep. No dependency was installed. Equivalent focused textual scans found no `except Exception`, `# noqa: BLE001`, `# type: ignore`, or `raise ... from None` in the reviewed facade/rendering surface, but they did identify the blocking `Any` usage listed above.

## Required Remediation

Replace coercive and presence-only pair/state record checks with a shared typed parser or recursive strict schema validation that rejects `bool` for integer fields before release reconciliation. Replace `Any`/untyped dictionaries at the active pairing and verifier boundary with typed models or recursive JSON value types, then add release-level regression tests that mutate these persisted primitive values to booleans.
