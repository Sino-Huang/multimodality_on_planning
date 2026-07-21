# Phase 3 Planimation VLM Pairing - 2026-07-15

## Implementation

- Added `scripts/phase3/planimation_pairing.py`, `scripts/phase3/generate_planimation_vlm.py`, and `scripts/phase3/verify_planimation_vlm.py`.
- The pipeline treats source trace roots and curriculum artifacts under `outputs/` as read-only. Generated Planimation artifacts belong under a caller-provided repo-local `tmp/` root.
- Pairing manifests join each full example to its Planimation VFG/frame artifacts and record `frame_count`, `plan_length`, `trace_size_chars`, VFG action count, action/frame alignment status, fidelity metadata, and controlled training exclusion reasons.
- The state renderer replaces only an original problem PDDL `:init` block with a replay `state_before`, preserves the remaining PDDL, uploads that state to Planimation, and locally renders VFG stage zero. Cached state artifacts contain derived PDDL, VFG, PNG, and result metadata.
- VLM output has two model-neutral views: full unmodified planner-trace targets at the initial replay state, and one compact action/reasoning record per replay transition. Full source traces are retained by path and hash.

## Combined Manifest Audit

Command:

```bash
python scripts/phase3/generate_planimation_vlm.py \
  --dataset-root outputs/phase3_curriculum_traces_15puzzle_easy_20260709_002417 \
  --dataset-root outputs/phase3_curriculum_traces_safe_no_visitall_20260708_122431 \
  --dataset-root outputs/phase3_curriculum_traces_visitall_20260708_191916 \
  --dataset-root outputs/phase3_curriculum_traces_visitall_train_test_long_timeout_20260710_000503 \
  --output-root tmp/phase3_planimation_vlm_manifest_audit_20260715 \
  --manifest-only
```

Result: 6,816 manifest records, split counts `train=5690`, `dev=630`, and `test=496`; 2,691 records are eligible under the selected seven-domain easy/medium, unrecovered configured-method, 1M-trace-character, and 64-action limits.

- Existing VFG alignment: `action_mismatch=4973`, `existing_exact_complete=885`, and `existing_exact_preview_partial=958`.
- Exclusions overlap: `recovery_trace=3504`, `trace_size_exceeds_limit=832`, `plan_length_exceeds_limit=572`, and `domain_not_in_core=688`.
- The high mismatch count confirms that source VFG frames must not be used as local-planner action supervision. Replay-state rerendering is required.

## Real Planimation Smoke

Command:

```bash
source .venv/bin/activate && python scripts/phase3/generate_planimation_vlm.py \
  --dataset-root outputs/phase3_curriculum_traces_safe_no_visitall_20260708_122431 \
  --output-root tmp/phase3_planimation_vlm_blocksworld_smoke_20260715 \
  --domain blocksworld --bucket easy --render-limit 1 --render-only \
  --request-delay-seconds 0
```

Result: one replay state rendered successfully for `blocksworld-dev-easy-0001`, planner `ff`, step `0`, before action `(pickup b2)`. It produced a derived PDDL problem, VFG, PNG, and render metadata. The verifier returned no errors.

Visual caveat: the replay-state frame and the original Planimation initial frame are both sparse for this Blocksworld instance. This is a Planimation/profile characteristic, not a PDDL-init rewrite mismatch. Perform a small visual QA sample for every domain before starting a large render pass.

## Verification

```bash
source .venv/bin/activate && pytest tests/phase3/test_planimation_pairing.py -q
source .venv/bin/activate && pytest tests/phase3/test_phase3_pipeline.py tests/phase3/test_phase3_pipeline_regressions.py tests/phase3/test_planimation_pairing.py -q
source .venv/bin/activate && python scripts/phase3/verify_planimation_vlm.py --output-root tmp/phase3_planimation_vlm_blocksworld_smoke_20260715
source .venv/bin/activate && python scripts/phase3/verify_planimation_vlm.py --output-root tmp/phase3_planimation_vlm_manifest_audit_20260715
```

Historical result on 2026-07-15: focused pairing tests `3 passed`; Phase 3 regression subset `46 passed`; both verifier runs returned `errors: []`. After the F4 relocation on 2026-07-16, the artifacts remain available at the `tmp/` paths above, but current verifier replay is intentionally unavailable because these legacy manifests now fail with `source_snapshot_mismatch: malformed_provenance: source_root_id`.

## Next Action

Run bounded render-only visual QA for one eligible state from each of the seven core domains. After confirming visual quality, generate a fresh complete renderer root under `tmp/`; don't treat the relocated legacy manifest audit as a current release candidate.

## F4 Scope-Fidelity Relocation

On 2026-07-16, four generated roots were moved without deletion or source-root changes:

- `outputs/phase3_planimation_vlm_blocksworld_smoke_20260715` to `tmp/phase3_planimation_vlm_blocksworld_smoke_20260715`
- `outputs/phase3_planimation_vlm_manifest_audit_20260715` to `tmp/phase3_planimation_vlm_manifest_audit_20260715`
- `outputs/phase3_planimation_vlm_manifest_safe_audit_20260715` to `tmp/phase3_planimation_vlm_manifest_safe_audit_20260715`
- `outputs/phase3_planimation_vlm_manifest_smoke_20260715` to `tmp/phase3_planimation_vlm_manifest_smoke_20260715`

Post-move inspection found no `outputs/phase3_planimation_vlm_*_20260715` root. The four `outputs/phase3_curriculum_traces_*` source roots remained in place and were not edited.
