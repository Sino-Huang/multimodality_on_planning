# Phase 3 Planimation Evidence Verifier

## Scope

Issue #2 is implemented by commit `d78284d` (`feat(phase3): add offline Planimation evidence verifier`). It provides a hermetic verifier that derives Planimation Integration Certification from a submitted plan, saved VFG evidence, and the agreed eight-claim matrix without starting the Planimation backend.

The implementation normalizes one- and multi-action plans into canonical action sequences, rejects malformed plans, requires exactly one initial VFG stage and an exact ordered action match, emits stable JSON, and exits with `0` for certification, `1` for failed claims, and `2` for malformed evidence. The focused test suite also exercises the local adapter integration without Django or network access.

## Verification

```bash
source ~/cd_vlaplan && python -m pytest tests/phase3/test_cgas_planimation_evidence.py tests/phase3/test_local_planimation_adapter_integration.py -q
```

This command passed with `43 passed` on 2026-08-16.

## Legacy Full-Suite Collection Exclusion

`source ~/cd_vlaplan && python -m pytest tests -q` currently stops during collection with 13 failures unrelated to Issue #2. They predate `d78284d` and arise only from the output-layout and organize-outputs areas:

- `tests/phase3/test_organize_outputs_hardening.py` and `tests/phase3/test_organize_outputs_semantics.py` import the absent `receipt_path` helper from `tests/phase3/organize_outputs_support.py`.
- Eleven `tests/phase3/test_output_layout_*.py` modules import the absent `VIEW_ROOT` name from `scripts/phase3/output_layout_contracts.py` through the output-layout view modules.

These tests are intentionally **not deleted or skipped**. They exercise independent output-layout and organizer contracts, so removing them would hide a separate regression rather than verify this ticket. Until that separate contract breakage is repaired, treat the 13 collection errors as excluded only from Issue #2's focused verification; do not add a pytest ignore rule, skip marker, or CI exclusion for them.

The full suite therefore remains non-green, and Issue #2 must remain open under AUTO MODE's closure rule even though its focused verification passes.
