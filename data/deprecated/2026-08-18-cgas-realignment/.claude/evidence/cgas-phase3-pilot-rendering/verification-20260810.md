# Phase 3 Pilot Rendering Verification - 2026-08-10

## Outcome

Local hardening is complete, but production rendering remains blocked. Authoritative source confirms that the repository client uses the correct endpoint, multipart fields, and no-filename part encoding. The exact smoke problem parses and solves locally, while the server's exact error pair proves the request reached Planimation's planner invocation and its downstream solver returned neither `ok` nor `PENDING` before VFG generation; it does not distinguish service availability from solver-side PDDL compatibility. No multipart client defect was proven, so no speculative transport change was made. Independent review additionally found that the frozen state-only request does not bind a canonical source candidate for 4,293 shared-state groups; the adapter now fails before network use when same-state rows have different source identity. The authorized one-state smoke produced no VFG or PNG; the 16,822-state production run and 790-row replay alignment were therefore not started.

## Smoke and local rendering

- Remote smoke: requested 1, processed 1, succeeded 0, failed 1, duplicate 0, collision 0, remaining 1.
- Canonical endpoint response: `API error: The process ends with an exception / Unexpected status from the server`.
- Transmitted data: 1,002-byte Blocksworld domain PDDL, one repository-derived 8-object/449-byte problem PDDL, and the 9,368-byte Blocksworld animation profile. No credentials, traces, manifests, models, or secrets were transmitted.
- No remote VFG or PNG was returned. The saved smoke run contract predates the final source-digest contract and is not a resumable production checkpoint.
- A previously accepted VFG rendered locally to one 1024x1024 RGBA PNG with semantic status `validated_expected_object_coverage`.
- VFG SHA-256: `9df741b2b68a8c74b867f6f86e34960c94300d57b782427c9c394de1dff8fb69`.
- PNG SHA-256: `acb586051383106416b8aa1c761cbc8cfc9d2c8e2a1d7bb3228a6050d1645827`.

## Verification results

- Focused adapter/alignment after provenance fix: `24 passed in 0.36s`.
- Final relevant Phase 3 regression subset: `156 passed in 19.02s`.
- Ruff: `All checks passed!`.
- basedpyright: `0 errors, 0 warnings, 0 notes`.
- Independent review: PASS after the fail-fast shared-state source-identity correction; accepted MEDIUM size debt remains.
- Staged secret review: 13 files scanned, no secrets detected.
- Frozen index: 31,171 rows, SHA-256 `46d1e7c1c0a6a133372782e691888840a74f3d3732dd625b5e2d8611fdf5d390`.
- Frozen request: 16,822 rows, SHA-256 `13db7cba5fb1cf885bd203ff657e5c7714bda6f832c5970dbfe5a9dee36d0585`.
- Read-only rerun: covered 0, missing 16,822, historical collisions 2; neither collision is required. The regenerated request has the frozen 16,822-row digest.
- Immutable inputs: all six checks passed.

## Exact verification commands

```bash
source ~/cd_vlaplan && python -m pytest -q tests/phase3/test_cgas_pilot_planimation_adapter.py
source ~/cd_vlaplan && python -m pytest -q tests/phase3/test_cgas_pilot_planimation_adapter.py tests/phase3/test_cgas_pilot_expansion_index.py tests/phase3/test_planimation_pairing.py tests/phase3/test_planimation_pairing_contracts.py tests/phase3/test_planimation_profile_regressions.py tests/phase3/test_planimation_search_traversal.py tests/phase3/test_render_semantics.py tests/phase3/test_verify_planimation_vlm.py
source ~/cd_vlaplan && ruff check scripts/phase3/cgas_pilot_planimation_adapter.py scripts/phase3/cgas_pilot_replay_alignment.py scripts/phase3/planimation_pairing_rendering.py tests/phase3/test_cgas_pilot_planimation_adapter.py
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_pilot_planimation_adapter.py scripts/phase3/cgas_pilot_replay_alignment.py scripts/phase3/planimation_pairing_rendering.py tests/phase3/test_cgas_pilot_planimation_adapter.py
source ~/cd_vlaplan && python -m scripts.phase3.cgas_pilot_render_coverage --repository . --index tmp/cgas-phase3-pilot-expansion-index-v1/pilot-expansion-index.jsonl --output tmp/cgas-phase3-pilot-render-coverage-rerun-20260810
sha256sum -c .claude/evidence/cgas-phase3-pilot-materialization/immutable-inputs.after.sha256
```

Expected signals are 23 focused passes, 143 regression passes, clean Ruff and basedpyright output, coverage `0/16822`, the frozen request digest, and six `OK` immutable-input lines.
