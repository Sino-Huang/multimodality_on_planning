# Todo 7 Documentation Command Log

Timestamp: `2026-07-26T06:11:38Z`

## Evidence Read

The closure was written from the existing Todo 1 through Todo 7 evidence, all
four plan notepads, the actual pilot receipt, current pilot summaries, and nearby
documentation examples. No source, test, pilot data, cache data, temporary
recovery root, frozen selection, or plan checkbox was changed.

## Recorded Product Verification

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest -q tests/phase3/test_rollout_gates.py::test_promotion_accepts_exact_frozen_subset_from_larger_source_manifest
source ~/cd_vlaplan && source .venv/bin/activate && pytest -q tests/phase3/test_rollout_gates.py tests/phase3/test_verify_planimation_vlm.py
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright scripts/phase3/rollout_gate_selection.py tests/phase3/test_rollout_gates.py
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3 tests/phase3
git diff --check
```

The retained outcomes are: expected red failure from the frozen source-manifest
hash mismatch, 21 passed after the contract fix, basedpyright with 0 errors,
0 warnings, and 0 notes, compileall exit 0, and `git diff --check` exit 0. Ruff
was unavailable in the activated environment and wasn't installed.

## Actual Pilot Verification and Promotion

The exact commands and exit codes are recorded in `actual-command-records.json`.
Manifest, render, release, and the one actual rollout assessment all exited 0.

## Documentation Validation

The closure validation parsed five JSON files and checked eight Markdown files.
It confirmed ten required claims, all four timestamped notepad additions, zero
placeholder markers, and zero Unicode dash characters. The required receipt
hashes, counts, launcher commands, preservation statement, and full-corpus
limitation were present.

## 2026-07-26T06:34:29Z Final Oracle Provenance Correction

Oracle identified one Medium gap: the exact selected-record subset fallback
needed an explicit valid source-provenance precondition. Current
`_load_selection()` requires `input_pairing_manifest_sha256` to contain exactly
64 lowercase hexadecimal characters and emits `invalid_frozen_selection` for a
missing, uppercase, wrong-length, or non-hexadecimal value. The negative
regression recomputes `selection_sha256` after provenance mutation, so the
expected rejection is not caused by stale selection integrity.

The retained static-check command is:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright scripts/phase3/rollout_gate_selection.py scripts/phase3/rollout_gate_promotion.py tests/phase3/test_rollout_gates.py
```

The recorded result remains 0 errors, 0 warnings, and 0 notes. The focused
suite remains 21 passed; compileall and `git diff --check` remain exit 0. No
promotion receipt, approved count, artifact hash, selection, pilot output, or
full-corpus limitation changed.
