
## Todo 1 Source Snapshot Provenance

- Pairing manifests now reload source examples from `source_root` plus root-relative JSONL path and physical line index. They freeze a source-record SHA-256, selected split SHA-256, whole-root snapshot SHA-256, root ID, and active planner ID; no `traces/**.full_example.json` file is required.
- RED source-provenance command: `source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_planimation_pairing.py -q`. Before implementation: `4 failed, 2 passed`, including missing standalone full-example reload, absent provenance fields, drift not classified, and legacy `bfs` acceptance.
- RED snapshot-cache command: `source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_planimation_pairing.py::test_validate_pairing_output_reuses_source_root_snapshot_per_root -q`. Before caching: `1 failed`; observable `_source_root_snapshot` calls were `2` for two rows in one root.
- GREEN focused command: `source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_planimation_pairing.py -q`. Result: `7 passed in 0.17s`.
- Real CLI command: `source ~/cd_vlaplan && source .venv/bin/activate && output_root="tmp/phase3_task1_manifest_$(date +%Y%m%d_%H%M%S)" && python scripts/phase3/generate_planimation_vlm.py --dataset-root outputs/phase3_curriculum_traces_15puzzle_easy_20260709_002417 --output-root "$output_root" --domain 15puzzle --bucket easy --manifest-only && python scripts/phase3/verify_planimation_vlm.py --output-root "$output_root"`.
- Real CLI result: the 688-row 15puzzle manifest completed and verification returned `errors: []`; artifact: `tmp/phase3_task1_manifest_20260715_191332`.

## Todo 1 Review-Blocker Correction

- The earlier 688-row verifier success did not prove linear source-row loading. Oracle measured `139,398,064,350` cumulative prefix bytes from per-pair rescans, so the earlier success claim was incomplete.
- RED command: `source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_planimation_pairing.py -q`. Before this fix: `9 failed, 7 passed`, exposing unchecked manifest identity fields, missing-provenance `KeyError`, and repeated JSONL scans.
- GREEN command: `source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_planimation_pairing.py -q`. Result: `16 passed in 0.25s`.
- Typing command: `source ~/cd_vlaplan && source .venv/bin/activate && basedpyright scripts/phase3/planimation_pairing.py tests/phase3/test_planimation_pairing.py`. Result: `0 errors, 0 warnings, 0 notes`.
- Compile command: `source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3/planimation_pairing.py tests/phase3/test_planimation_pairing.py`. Result: exit `0`.
- Exact timeout command: `source ~/cd_vlaplan && source .venv/bin/activate && /usr/bin/time -f 'ELAPSED_SECONDS=%e EXIT_STATUS=%x' timeout 300s python scripts/phase3/verify_planimation_vlm.py --output-root tmp/phase3_task1_manifest_20260715_191332`. Result: `errors: []`, `pair_records: 688`, `ELAPSED_SECONDS=7.37`, `EXIT_STATUS=0`.

## Todo 2 Trace Contract

- `phase3_traversal_trace_v1` is a strict nested trace boundary for exactly `ff`, `gbfs`, `iw`, and `graphplan`. The legacy `bfs` identifier and an absent or unsupported version are controlled errors, never aliases or fallbacks.
- Projection receives the frozen source identity from the pairing manifest plus the reloaded Todo 1 source row. FF, GBFS, and IW preserve recorded concrete-state hashes; Graphplan layer/mutex/extraction events are planner semantics with no concrete state/frame claim.
- RED command: `source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_traversal_trace_contracts.py -q`. Before implementation it failed collection with `ModuleNotFoundError: scripts.phase3.trace_contracts`.
- GREEN command: `source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_traversal_trace_contracts.py tests/phase3/test_planimation_pairing.py -q`. Result: `22 passed in 0.19s`.
- Final targeted regression command: `source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_traversal_trace_contracts.py tests/phase3/test_planimation_pairing.py tests/phase3/test_phase3_gbfs.py tests/phase3/test_phase3_local_trace_safety.py tests/phase3/test_phase3_pipeline_regressions.py -q`. Result: `47 passed in 0.93s`.
- Type/compile/CLI commands: `source ~/cd_vlaplan && source .venv/bin/activate && basedpyright scripts/phase3/trace_contracts.py scripts/phase3/planimation_pairing.py scripts/phase3/gbfs.py scripts/phase3/local_planners.py scripts/phase3/local_iw.py scripts/phase3/local_graphplan.py tests/phase3/test_traversal_trace_contracts.py tests/phase3/test_planimation_pairing.py`, followed by `python -m compileall -q ...` and `python -m scripts.phase3.trace_contracts --fixtures tests/phase3/fixtures/traversal_trace_contract_cases.json --report tmp/phase3_task2_trace_projection_report.json`. Results: basedpyright `0 errors, 0 warnings, 0 notes`; compilation exit `0`; fixture report projected the four valid cases and excluded the four malformed cases with stable reasons.

## Todo 2 Broad Pytest Runtime Classification

- Collection command: `source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3 --collect-only -q`. Result: `106 tests collected in 0.08s`.
- Full reproduction: `source ~/cd_vlaplan && source .venv/bin/activate && /usr/bin/time -f 'ELAPSED_SECONDS=%e EXIT_STATUS=%x' timeout 600s pytest tests/phase3 -vv --durations=0`. Result: last node `test_15puzzle_easy_first_ten_curriculum_trace_cli_defaults_emit_all_planner_traces`; `ELAPSED_SECONDS=600.01 EXIT_STATUS=124`.
- Exact-node replay: `source ~/cd_vlaplan && source .venv/bin/activate && /usr/bin/time -f 'ELAPSED_SECONDS=%e EXIT_STATUS=%x' timeout 180s pytest tests/phase3/test_phase3_15puzzle_easy_traces.py::test_15puzzle_easy_first_ten_curriculum_trace_cli_defaults_emit_all_planner_traces -vv`. Result: `ELAPSED_SECONDS=180.00 EXIT_STATUS=124`.
- Runtime tree at 15 seconds was `pytest -> generate_curriculum_trace_dataset.py -> generate_curriculum_trace_dataset.py`; after timeout its child became PPID 1. The generator imports `scripts.phase3.pipeline`, not Todo 2 pairing/trace-contract modules. This is an independent pre-existing expensive-subprocess and child-cleanup issue; no Todo 2 code was changed.

## Todo 3 Render Cache Hardening

- Profiles now resolve only from the repository-managed curriculum mapping. Cache results record the relative configured profile path and its SHA-256, plus domain/problem/state/renderer/config/schema identity.
- A cache hit revalidates result metadata, derived PDDL state, VFG structure/hash, decoded PNG hash/dimensions, and deterministic nontransparent-pixel image QA. Corrupt PNG or stale metadata forces a rerender.
- Raster archives validate all members before writes and reject escaping paths, symlinks, non-PNG payloads, and bounded-resource violations. The Phase 1 archive helper delegates to the same safe extractor.
- Focused verification: `source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_planimation_pairing.py tests/data_collect/test_rendering.py tests/test_planimation_phase1.py -q` returned `34 passed in 0.56s`.

## Todo 4 Concrete Traversal State Projection

- `scripts/phase3/traversal_states.py` creates event-distinct candidates from strict FF/GBFS/IW events. Candidate IDs include frozen root/JSONL/line provenance and role; sorted state hashes are asset keys only.
- FF successor atoms are checked against deterministic PDDL action application; GBFS/IW successors reconstruct only after normalized-action lookup and applicability against the recorded parent state. Invalid action, unknown action, atom mismatch, absent parent atoms, unsupported PDDL, and non-concrete events become exclusions with no candidate.
- Focused verification: `source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_traversal_state_projection.py tests/phase3/test_traversal_trace_contracts.py tests/phase3/test_planimation_pairing.py -q` returned `31 passed in 0.33s`; basedpyright reported `0 errors, 0 warnings, 0 notes`; the CLI fixture report projected two candidates each for nonzero-plan FF/GBFS/IW fixtures.

## Todo 4 Semantic Label Correction

- Concrete trace events and successor records now carry strict explicit `event_kind` values: `expansion`, `generation`, `revisit`, or `backtrack`. Candidate projection copies this field; no semantic is inferred from action/state relationships.
- Local FF/GBFS/IW emitters serialize those labels. Missing or unsupported labels are strict controlled exclusions, and the CLI report exposes candidate `event_kinds`.
- RED command: `source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_traversal_state_projection.py::test_preserves_explicit_successor_semantics_when_assets_repeat -q` failed with successor labels inheriting `expansion`. GREEN focused regression returned `58 passed in 1.10s`.

## Todo 5 Safe Graphplan Replay

- RED command: `source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_traversal_state_projection.py tests/phase3/test_traversal_trace_contracts.py -q`. Before the boundary: `4 failed, 15 passed`; Graphplan had no extracted-plan candidates and accepted forged extraction parent linkage.
- GREEN command: `source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_planimation_pairing.py tests/phase3/test_traversal_trace_contracts.py tests/phase3/test_traversal_state_projection.py -q`. Result: `39 passed in 0.71s`.
- CLI commands: `python -m scripts.phase3.trace_contracts --fixtures tests/phase3/fixtures/traversal_trace_contract_cases.json --report tmp/phase3_task5_trace_event_report.json` reports three projected Graphplan semantic events; `python -m scripts.phase3.traversal_state_projection_cli --fixtures tests/phase3/fixtures/traversal_state_projection_cases.json --domain tests/phase3/fixtures/traversal_state_domain.pddl --problem tests/phase3/fixtures/traversal_state_problem.pddl --report tmp/phase3_task5_graphplan_replay_report.json` reports two `extracted_plan_replay` candidates and semantic layer exclusions.
- Type/compile commands reported `0 errors, 0 warnings, 0 notes` and exit `0`, respectively.
- Final render-adapter regression: `source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_planimation_pairing.py tests/phase3/test_traversal_trace_contracts.py tests/phase3/test_traversal_state_projection.py -q` returned `40 passed in 0.38s`. A Graphplan row with forged raw replay atoms rendered the PDDL state derived from its validated extraction instead.

## Todo 6 Validated Replay Rendering

- Semantic receipts now reject unreadable PNGs and malformed, boolean/non-numeric, out-of-canvas, degenerate, or coincident stage-zero VFG sprites. Each required sprite must have at least 1% non-background pixel coverage in its projected image bounds.
- One action renders one pre-action and one terminal diagnostic frame; only the pre-action row becomes a next-action VLM record. Zero-action solved cases render one initial/terminal full frame and zero next-action rows. A missing pre-action step zero yields no VLM record.
- Focused command: `source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_render_semantics.py tests/phase3/test_planimation_pairing.py tests/phase3/test_traversal_state_projection.py tests/phase3/test_traversal_trace_contracts.py -q`. Result: `48 passed in 0.51s`.

## Todo 7 Strict Hybrid Supervision

- Full and step records now expose separate strict nested targets and exact pair/event/state/trace/render provenance. JSON schemas prohibit additional fields at the record and nested contract levels, while `validate_vlm_record` rejects omissions before JSONL write.
- Production defaults reject `--render-limit`; bounded smoke requires `--mode bounded-smoke` and writes `diagnostics/hybrid_output_manifest.json` with `partial=true`, selected pair/state IDs, and the configured limit. `production_complete` is false for any cardinality skip, including missing step zero.
- Focused CLI fixtures use temporary roots only. The production parser rejects the limit with exit 2; bounded smoke returns 0 with a partial manifest at render limit 1. Evidence: `.omo/evidence/phase3-task-7-hybrid-supervision.json`.

## Todo 7 Schema Correction

- Root `additionalProperties=false` requires every valid root key to be declared in `properties`. Full and step schemas now declare all emitted root keys; only step schemas declare `step_index`. Closed nested boundaries remain unchanged.
- The activated environment lacks JSON Schema validator packages and CLIs. The regression evaluates persisted Draft 2020-12 schemas against emitted JSON with the exact object keywords emitted by this generator, proving valid full/step acceptance plus omitted/unexpected root and nested rejection. Command: `source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_planimation_pairing.py::test_generated_hybrid_schemas_validate_emitted_records_and_reject_extra_root_field -q`; result: `1 passed in 0.27s`.
- Focused pairing regression returned `32 passed in 1.50s`; basedpyright returned `0 errors, 0 warnings, 0 notes`; compilation exited 0.

## F2 Pairing And Release Modularization

- Pairing was separated into source, reasoning, schema, rendering, manifest, replay, record, and validation modules; the compatibility aggregator synchronizes facade monkeypatch hooks into source and manifest before calls.
- `Any` JSON boundaries were replaced by `JSONValue`, and copied unused imports were removed after extraction. Focused pairing/release regression: `53 passed in 8.20s`; basedpyright reported `0 errors, 0 warnings, 0 notes`.
- A generated production-complete fixture passed `verify_planimation_vlm.py --mode release` with one pair, four render records, one full record, one step record, and two search-traversal records in train.

## Todo 8 Release Verifier

- `verify_planimation_vlm.py` now separates `manifest`, `render`, and `release` checks. Release requires every persisted manifest/schema/report and six split JSONL files, reloads immutable source provenance, validates strict records, semantic render receipts and hashes, split isolation, coverage, and reconciled counts, and accepts only `production_complete` production output.
- Focused command: `source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_verify_planimation_vlm.py tests/phase3/test_planimation_pairing.py tests/phase3/test_render_semantics.py -q`. Result: `40 passed in 3.60s`.
- CLI release fixture: `source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/verify_planimation_vlm.py --output-root tmp/phase3_task8_release_fixture --mode release`. Result: exit `0`, reconciled one pair, two render states, one train full record, and one train step record. An absent root exits `1` with `missing_required_file: diagnostics/pairing_manifest.jsonl`.

## Todo 9 Staged Promotion Gates

- `rollout_gates.py` freezes source-root/split/line/record provenance and selected pair IDs before render. `--selection-file` lets the generator materialize only those frozen pairs; `assess` writes an approved receipt only after release verification and stage coverage checks.
- Fresh strict fixture command sequence passed the real release verifier and fixture promotion: one pair, two state renders, one train full record, and one train step record. Semantic metrics remain in `tmp/phase3_release_fixture_task9_fixture_cli_20260715/diagnostics/state_render_manifest.jsonl`; evidence is `.omo/evidence/phase3-task-9-rollout-gates-2026-07-15.json`.

## Todo 10 Hybrid Format and Release Documentation

- The dated final summary separates completed hybrid, projection, render, verifier, and rollout work from active-source release status. The approved temporary fixture is evidence for the fixture boundary only.
- Reusable fixture commands projected strict trace events and concrete candidates, passed two focused schema/release tests, reconciled one pair plus two renders in release mode, and renewed an approved fixture promotion receipt. All five documented commands exited zero.
- Durable documentation is in `doc/detailed_implementation_summary/phase3_hybrid_traversal_rendering_release_evidence_2026-07-15.md`; reusable knowledge and the exact command log are in `.omo/knowledges/phase3-hybrid-traversal-release-evidence-2026-07-15.md` and `.omo/evidence/phase3-task-10-documentation-command-log-2026-07-15.json`.

## F2 Strict Contract Correction

- Traversal validation now checks concrete planner fields and nested successors, including exact booleans and integers so Python `bool` cannot satisfy an integer field.
- Hybrid schemas declare concrete primitive, object, nullable-action, and typed-array contracts for every emitted root, provenance, artifact, and target field. `validate_vlm_record` consumes the same schema construction.
- Release recursively checks every persisted hybrid schema rather than inspecting only root keywords. A regression changes persisted `provenance.pair.source_line_index` to a string and release rejects the integer record value.
- Focused verification on 2026-07-16: `61 passed in 4.64s`; basedpyright reported `0 errors, 0 warnings, 0 notes`; compileall exited `0`; the strict trace CLI projected four valid and excluded four malformed fixtures; the release CLI accepted the existing persisted fixture.

## F4 Scope-Fidelity Relocation

- Moved `outputs/phase3_planimation_vlm_blocksworld_smoke_20260715` to `tmp/phase3_planimation_vlm_blocksworld_smoke_20260715`.
- Moved `outputs/phase3_planimation_vlm_manifest_audit_20260715` to `tmp/phase3_planimation_vlm_manifest_audit_20260715`.
- Moved `outputs/phase3_planimation_vlm_manifest_safe_audit_20260715` to `tmp/phase3_planimation_vlm_manifest_safe_audit_20260715`.
- Moved `outputs/phase3_planimation_vlm_manifest_smoke_20260715` to `tmp/phase3_planimation_vlm_manifest_smoke_20260715`.
- Post-move counts remained `9`, `3`, `3`, and `3` files, respectively. Sizes remained `11M`, `13M`, `9.6M`, and `1.2M`.
- `outputs/` now contains only `deprecated/` and the four frozen `phase3_curriculum_traces_*` source roots. No source curriculum root was moved or edited.
- Current verifier replay of the relocated Blocksworld smoke and combined manifest audit exits nonzero with `source_snapshot_mismatch: malformed_provenance: source_root_id`. The artifacts are preserved, but current verifier availability isn't claimed.

## F1 Search Traversal Production Integration

- Strict FF/GBFS/IW candidate projection now feeds the existing PDDL/cache/image gate and emits a separate `search_traversal_<split>.jsonl` family. Event IDs remain distinct even when a cached state asset is reused.
- FF missing successor atoms are an exclusion (`ff_missing_recorded_successor_state`); only GBFS/IW retain deterministic successor reconstruction. Graphplan layers remain nonvisual.

## F1 Final Verification Wave

- Final F1 review approved the fixture-release remediation only. Current rerun passed 66 focused tests in 5.37 seconds, basedpyright with zero findings, compileall with exit 0, and `verify_planimation_vlm.py --mode release` with one pair, four renders, one full record, one step record, and two search-traversal records.
- The active 15-puzzle root remains blocked: a current manifest-only probe found 688 pair records, zero strict-v1 eligible pairs, and 688 `missing_required_field: trace_contract_version` exclusions. Changed-canary selection returned `no_strict_v1_eligible_pairs`; no active-corpus rollout is approved.

## F3 Final Manual CLI Verification (2026-07-16)

- Commands executed with the prescribed environment:
  - `source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/verify_planimation_vlm.py --output-root tmp/f1_search_traversal_release_surface --mode release`
  - `source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.traversal_state_projection_cli --fixtures tests/phase3/fixtures/traversal_state_projection_cases.json --domain tests/phase3/fixtures/traversal_state_domain.pddl --problem tests/phase3/fixtures/traversal_state_problem.pddl --report /tmp/f3_graphplan_projection.json`
  - `source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/generate_planimation_vlm.py --dataset-root tmp/f3_fresh_source_20260716 --output-root tmp/f3_fresh_bounded_retry_20260716 --domain grid --bucket easy --mode bounded-smoke --render-limit 1 --base-url http://127.0.0.1:9 --timeout-seconds 1 --request-delay-seconds 0`
  - `source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/generate_planimation_vlm.py --dataset-root outputs/phase3_curriculum_traces_15puzzle_easy_20260709_002417 --output-root tmp/f3_active_legacy_20260716 --manifest-only --domain 15puzzle --bucket easy --request-delay-seconds 0`
  - `source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/rollout_gates.py prepare --output-root tmp/f3_active_legacy_20260716 --stage changed-canary --domain 15puzzle`
  - `source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/rollout_gates.py assess --output-root tmp/f3_active_legacy_20260716 --stage changed-canary --selection-file tmp/f3_active_legacy_20260716/diagnostics/rollout_selection.json`
- Fixture release verifier exited 0 and reconciled 1 pair, 4 state-render rows, 1 train full record, 1 train step record, and 2 train search-traversal records. All four render rows were successful `validated_expected_object_coverage` receipts; two decoded unique PNGs were 100x100 RGBA, with one expected sprite covered out of one on every receipt.
- FF, GBFS, and IW fixture projections each produced two concrete candidates. FF used recorded successor state atoms, while GBFS and IW allowed the documented PDDL-action reconstruction. The semantic-repeat GBFS fixture yielded four unique candidate event IDs for expansion, generation, revisit, and backtrack.
- Graphplan emitted only two `extracted_plan_replay` candidates from its validated extraction. Its proposition and action layers were explicitly excluded as `graphplan_nonvisual_event:*`; they were not treated as concrete image states.
- Final-plan replay remained separate from traversal records: full and step records shared the plan-replay event and cached pre-action asset, while the two traversal records used distinct search event IDs and cache/state assets. State cache reuse was visible across final-plan and traversal render rows for the same content.
- The fresh bounded-smoke CLI succeeded as a partial artifact (`partial=true`, limit 1), then correctly withheld full/step/traversal records when the intentional unreachable Planimation endpoint produced a failed render and release verification rejected render coverage reconciliation. The generator also correctly rejected a production `--render-limit` and rejected output roots outside repository `tmp/` or `outputs/`.
- The active 15-puzzle manifest-only probe stayed fail-closed: 688 pairs, 0 training eligible, and 688 strict-v1 exclusions for missing `trace_contract_version`. Changed-canary selection reported `no_strict_v1_eligible_pairs`; assessment returned `approved=false` with a persisted rejected receipt. This is fixture-capability evidence only, not active-source rollout approval.

## F2 Final Code-Quality Verification (2026-07-16T00:55:20+10:00)

- Reviewed the complete Phase 3/rendering contract, pairing, semantic image, release verifier, rollout gate, archive-extraction, traversal-projection, and targeted-test surfaces. No production or test files were changed during this review.
- Strict scalar contracts reject Python `bool` for integer fields in trace and persisted-record validation; recursive schema checks reject wrong nested primitive, object, required-key, and additional-property values. Release re-evaluates the persisted schemas, rather than relying only on generated in-memory structure.
- Render receipts bind recomputed semantic metrics and PNG/VFG SHA-256 values to manifest rows and release records. Textured gradient, grid, and deterministic-noise blanks are rejected; unsafe path-escape archives are rejected before any member is written. Fixture promotion evidence is accepted only for its fixture boundary, not as active-corpus promotion evidence.
- Evidence: focused adversarial probes `18 passed in 0.89s`; complete F2/rendering focused suite `105 passed in 11.45s`; basedpyright `0 errors, 0 warnings, 0 notes`; compileall exit 0; LSP diagnostics clean for `scripts/phase3`, `src/data_collect/rendering.py`, `tests/phase3`, and rendering tests. AST-aware querying was run for broad exception and cause-suppression shapes; no `raise ... from None` escape was found. The review still found broad `except Exception` handlers suppressed by `# noqa: BLE001` in the delivered rendering path, so the code-quality verdict is reject despite functional F2 success.
- Blocking code-quality findings: `scripts/phase3/planimation_pairing.py` (1175 lines) and `src/data_collect/rendering.py` (702 lines) exceed the project 250 pure-LOC ceiling; `planimation_pairing.py` uses broad `Exception` catches at lines 438, 571, and 635 with `# noqa: BLE001`, and contract/release boundaries rely pervasively on `Any`. These must be refactored into typed boundary errors and cohesive modules before a code-quality approval.

## F2 Exception-Boundary Remediation (2026-07-16)

- Planimation retry and record-failure boundaries now catch only modeled I/O, renderer, PDDL, decoding, validation, archive, and image errors. The `# noqa: BLE001` broad-exception suppressions were removed from `src/data_collect/rendering.py`, `scripts/phase3/planimation_pairing.py`, and `scripts/planimation_phase1.py`.
- Regression: an injected `AttributeError` from the Planimation PDDL adapter must propagate rather than be silently converted into a failed render receipt. This keeps programming-contract violations visible while retaining controlled render failure outcomes for expected boundary errors.
- `PlanimationRenderer` now accepts explicit protocols for PDDL upload, VFG visualization, local frame rendering, archive extraction, and host preflight instead of `Any`-typed injected adapters.
- Verification: `source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/data_collect/test_rendering.py tests/test_planimation_phase1.py tests/phase3/test_planimation_pairing.py -q` returned `57 passed in 2.51s`; basedpyright returned `0 errors, 0 warnings, 0 notes`; `python -m compileall -q src/data_collect/rendering.py scripts/phase3/planimation_pairing.py scripts/planimation_phase1.py tests/data_collect/test_rendering.py` exited `0`; textual scan found no remaining `except Exception` or `noqa: BLE001` in these three files.

## F2 Structural Extraction Map (2026-07-16)

- `src/data_collect/rendering.py` must become a facade over archive validation/extraction, renderer contracts/backends, and acceptance/preflight gates. Its public imports are used by data-collection tests and the generator orchestrator.
- `scripts/planimation_phase1.py` must become a CLI facade over manifest/assets, remote Planimation client, local VFG PNG renderer, and entry runner. Its `post_pddl_for_vfg` and `render_vfg_to_local_png_frames` imports are consumed by Phase 3 pairing and the data-collection adapter.
- `scripts/phase3/planimation_pairing.py` must become a facade over source provenance/pair manifest, state rendering/cache, and strict VLM schema/record construction. `generate_planimation_vlm.py`, `verify_planimation_vlm.py`, pairing tests, and traversal tests import its public and verifier-facing private hooks.
- Compatibility re-exports are required for `SCHEMA_VERSION`, `PairingConfig`, `RenderConfig`, `build_pairing_manifest`, `render_replay_states`, `build_vlm_records`, `validate_pairing_output`, `_load_source_example`, `_render_receipt_is_valid`, `_trace_identity`, `validate_pair_record`, `validate_state_render_record`, and `validate_vlm_record`.

## F2 Compatibility Facade Remediation

- Legacy module paths now load compact facades, while implementation modules retain behavior. The pairing facade synchronizes its two monkeypatchable source-index hooks before calling validation.
- Focused regression command returned `90 passed in 6.44s`; basedpyright, compileall, diff check, and fixture release verification were clean.

## F2 Phase 1 Module Decomposition (2026-07-16)

- Replaced the 665-line `scripts/planimation_phase1_implementation.py` monolith with explicit manifest/assets, remote client, local VFG frame, runner, and CLI modules. `scripts.planimation_phase1` remains the direct-alias compatibility facade used by rendering and Phase 3.
- Archive handling delegates to `src.data_collect.render_archive`; hosted visualization retains PNG-only local fallback. Direct tests cover facade identity, explicit endpoints, named preflight failure, readable local PNG output, and unexpected request-adapter `AttributeError` propagation.
- Verification: `source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/test_planimation_phase1.py tests/data_collect/test_rendering.py tests/data_collect/test_imports.py tests/data_collect/test_cli.py tests/data_collect/test_generate_orchestrator.py tests/phase3/test_planimation_pairing.py -q` returned `83 passed in 3.04s`; basedpyright returned zero findings; compileall, CLI help/bad-input surfaces, LOC checks, and diff check passed.

## F3 Independent Manual QA (2026-07-16)

- Fixture release command: `source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/verify_planimation_vlm.py --output-root tmp/f1_search_traversal_release_surface --mode release`. Exit `0`; release reconciled 1 pair, 4 state renders, 1 train full record, 1 train step record, and 2 train search-traversal records.
- Decoded each fixture render PNG through Pillow and recomputed PNG/VFG SHA-256 values. Every asset had derived PDDL, VFG, and PNG provenance; all PNGs were `100x100` `RGBA`, all hashes matched the persisted receipts, and all receipts reported `validated_expected_object_coverage` with 1 covered sprite out of 1 at a `0.01` minimum.
- Real projection CLI wrote a temporary report and returned 2 candidates for FF, GBFS, IW, and validated Graphplan extraction replay. FF used trace-recorded successor state; GBFS/IW used PDDL-action reconstruction. Graphplan proposition/action layers were excluded with `graphplan_nonvisual_event:*`, leaving only `extracted_plan_replay` candidates renderable.
- A fresh-source bounded-smoke invocation against unreachable `http://127.0.0.1:9` exited `0` but wrote `partial=true`, `production_complete=false`, selection render limit 1, one failed render, and zero full/step/traversal records. Release verification exited `1` with `render coverage reconciliation`. Production `--render-limit 1` exited `2` with the explicit bounded-smoke-only error.
- A read-only active-root manifest probe found 688 pairs, 0 training-eligible records, and 688 `trace_contract_exclusion:missing_required_field: trace_contract_version` entries. Changed-canary preparation selected zero pairs with `no_strict_v1_eligible_pairs`; assessment persisted `approved=false` and included `selection_preparation_blocked`.
- Cleanup: removed only `tmp/f3_independent_bounded_20260716`, `tmp/f3_independent_active_legacy_20260716`, `tmp/f3_independent_production_reject_20260716`, and `tmp/f3_independent_traversal_projection_20260716.json`; post-check emitted `F3_TEMP_CLEANUP=PASS`. Evidence: `.omo/evidence/planimation-hybrid-traversal-rendering/f3-manual-qa-2026-07-16.{json,md}`.

## F2 Independent Code-Quality Gate (2026-07-16)

- Verdict: `REJECT`. Focused execution passed (`113 passed in 7.57s`), basedpyright was clean, compileall exited 0, fixture release passed, LSP diagnostics were clean, and archive traversal/symlink/non-PNG/member-limit/compression-ratio probes rejected unsafe archives.
- Real copied-fixture release probes exposed a material strict-contract bypass: `validate_pair_record` at `scripts/phase3/planimation_pairing_implementation.py:445-452` coerces `True` to integer via `int(...)`, so release accepted boolean `plan_length` and `trace_size_chars`; `validate_state_render_record` at lines 455-466 does not type-check `step_index`, so release accepted boolean `step_index`.
- The same implementation carries pervasive `Any`/`dict[str, Any]` across active pairing, rendering, schema, and release boundaries. Required remediation is a shared typed parser or strict recursive validator for pair/state persisted rows, with release-level boolean-primitive rejection tests. Full independent evidence: `.omo/evidence/planimation-hybrid-traversal-rendering/f2-code-quality-review-2026-07-16.md` and `.json`.

## F4 Independent Scope-Fidelity Gate (2026-07-16)

- APPROVE for the current snapshot only. `outputs/` contains exactly `deprecated/` plus four frozen curriculum roots; the roots have 1,393, 10,885, 167, and 1,255 files. Every declared `generated_file_digests` entry in their manifests recomputed successfully, and their current file-list SHA-256 values are retained in `.omo/evidence/planimation-hybrid-traversal-rendering/f4-scope-fidelity-audit-2026-07-16.md`.
- `git diff --name-status HEAD -- outputs`, cached equivalent, and status filtered to `outputs/` were empty; `git ls-files --stage outputs` returned `0`, and the `HEAD` tree contains no output artifact. Historical output additions/removals exist before HEAD (`31dfbef`, `e0ddccb`) but no current output commit or staging occurred; this audit did not modify Git state.
- Planner diffs add only strict trace version/event-kind serialization. The focused six-file planner/projection suite returned `59 passed in 1.42s`. Graphplan proposition/action/mutex data stays semantic and nonvisual; only a normalized, applicable, goal-satisfying extraction replay can produce candidates marked `extracted_plan_replay`, and Graphplan emits no search-traversal frames.

## F2 Persisted Contract Remediation (2026-07-16)

- Persisted pair/state validation now uses `scripts/phase3/planimation_persisted_contracts.py`, which rejects Python booleans for every persisted integer field with `type(value) is int`. Release regressions cover `plan_length`, `trace_size_chars`, and `step_index` copied-fixture bypasses.
- State status variants are exclusive. Existing renderer metadata is accepted only where valid and remains type-checked when optional; malformed source-plan cardinality emits a controlled no-transition failed state row without crashing sort or hybrid-manifest receipt generation.
- Final verification: `source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_verify_planimation_vlm.py tests/phase3/test_planimation_pairing.py -q` returned `50 passed in 6.43s`; basedpyright returned `0 errors, 0 warnings, 0 notes`; compileall exited `0`; a valid release fixture exited `0`, and pair/state bool probes exited `1` with exact integer errors.

## F2 Controlled Cardinality Failure Contract (2026-07-16)

- A malformed persisted plan now emits the documented compact `render_cardinality_invalid` failed-state variant. Its validator accepts only the exact failure fields, so it does not fabricate state/cache/render provenance for a transition that was never produced.
- Focused regression: `source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_planimation_pairing.py::test_invalid_plan_cardinality_emits_a_controlled_failed_state_row tests/phase3/test_verify_planimation_vlm.py::test_release_handles_a_valid_controlled_failed_state_row tests/phase3/test_verify_planimation_vlm.py::test_release_rejects_mixed_state_render_variants -q` returned `3 passed in 0.84s`. Release rejects the incomplete output for `render coverage reconciliation`, rather than a self-invalid state row.

## F2 Rollout JSON Contract Remediation (2026-07-16)

- `io_utils.read_jsonl` and `read_json_object` now expose object-only `JSONRecord` contracts and reject non-object decoded input with a controlled `JSONInputError` before downstream mapping operations.
- `prepare_selection` validates every loaded persisted pair with `validate_pair_record` before filtering, transition counting, or writing a selection. Exact integer helpers reject bool values, and the persisted planner contract rejects legacy `bfs`.
- Adversarial selection tests rejected `plan_length=True`, `planner="bfs"`, and a non-object JSONL row without writing a selection receipt. A direct facade regression monkeypatched both source hooks, executed real render and VLM workflows, and observed one snapshot plus one JSONL hook call per workflow.
- Verification: focused adversarial/facade tests returned `4 passed in 0.28s`; the F2/rollout/render suite returned `67 passed in 6.99s`; basedpyright reported `0 errors, 0 warnings, 0 notes`; compileall and `git diff --check` passed; the valid fixture release verifier reconciled one pair, four state renders, one full record, one step record, and two search-traversal records.

## F2 Rollout Structural Compliance (2026-07-16)

- Measured `rollout_gates.py` at `263` pure LOC with the documented nonblank/noncomment awk expression, so the F2 ceiling required an extraction.
- The compatibility/CLI facade is now `32` pure LOC; shared contracts are `31`; strict selection is `134`; promotion/receipt validation is `144`. Every changed active rollout module is below 250 pure LOC.
- The facade passes its monkeypatchable `verify_output` to the promotion implementation, preserving direct test imports, the test monkeypatch seam, `prepare`/`assess` JSON output, and direct script invocation.
- Focused suite result: `67 passed in 6.82s`; basedpyright reported `0 errors, 0 warnings, 0 notes`; compileall and diff check passed.

## F3 Final Manual QA Refresh (2026-07-16T01:55:10Z)

- Current fixture release exited 0 with 1 pair, 4 state-render rows, 1 train full record, 1 train step record, and 2 train search-traversal records. FF, GBFS, and IW each projected two concrete fixture candidates; Graphplan emitted only two validated `extracted_plan_replay` candidates while proposition/action layers were nonvisual exclusions.
- Independent decoded-asset audit recomputed derived-PDDL, state, VFG, and PNG provenance on all four rows. The GBFS-only rendered fixture had two unique 100x100 RGBA PNG paths, valid 1/1 object-coverage receipts, and consistent cache and hybrid-record provenance.
- The active 15-puzzle source remains strictly fail-closed across all four planner classes: each has 172 rows missing `trace_contract_version`, no eligible candidates, no rendered canary states, and no visual-semantic metrics to promote.
