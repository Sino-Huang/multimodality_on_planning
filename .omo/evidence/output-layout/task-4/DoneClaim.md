# DoneClaim: Task 4 Synthetic Organizer Hardening

Task 4 now includes the organizer's original synthetic relocation workflow plus Todo 4 hardening for current-inventory validation, receipt-path policy, durable catalog publication, and exact writer detection. The scope remains synthetic only. No real output tree was inspected or touched, no production migration ran, and no commit was made.

## Shipped contracts

- Inventory validation runs at apply and verify boundaries. Apply checks before preparation, around relocation mutations, before view creation, and before completion. Verify rejects an unknown immediate output root before reading or validating the supplied receipt.
- Apply accepts only the exact lexical canonical receipt path `outputs/deprecated/phase3/output_reorganization_20260726.json`. Alternate spellings are rejected before lock acquisition or mutation. Verify remains read-only and may read a complete private mode-`0600` receipt outside the repository without rewriting it.
- Catalog rendering remains pure when no output path is requested. File publication uses a private mode-`0600` temporary regular file, complete short-write handling, file `fsync`, descriptor-relative `RENAME_NOREPLACE`, parent `fsync`, parent identity checks, and owned-temporary cleanup. It never replaces an existing destination and fails closed if no-replace publication is unavailable.
- Writer detection recognizes exact direct-script and `python -m` forms for the registered Phase 3 writers, follows their real parser defaults and effective mutating subcommands, uses the last repeated option value, resolves relative targets against each process `cwd`, and rejects equal, ancestor, or descendant overlaps. Incidental command text and read-only or dry-run commands do not count as writers.
- Process metadata handling is fail-closed for unreadable live `/proc` metadata, malformed NUL framing, malformed recognized invocations, and unresolved live process `cwd`. A process that vanishes during inspection is skipped as a normal race.

The added implementation modules are `scripts/phase3/organize_outputs_catalog.py`, `scripts/phase3/organize_outputs_inventory.py`, `scripts/phase3/output_layout_writer_detection.py`, and `scripts/phase3/output_layout_writer_registry.py`. They extend the existing coordinator and helpers in `organize_outputs.py`, `organize_outputs_preflight.py`, `organize_outputs_receipt.py`, `organize_outputs_view.py`, and `output_layout_rename.py`.

## Latest evidence

The required-environment focused command used `source ~/cd_vlaplan && PYTHONPATH="$PWD/tests/phase3" python -m pytest -q` on the eight organizer, catalog, inventory, and writer paths recorded in `commands.md`. Final remediated result: `81 passed in 13.29s`.

Basedpyright reported `0 errors, 0 warnings, 0 notes`. Compileall exited 0. The no-excuse checker reported `no violations in 11 file(s)`.

Manual synthetic CLI QA printed `{"command": "apply", "ok": true}` and `{"command": "verify", "ok": true}` for an external mode-`0600` receipt. It also proved exact stdout-only catalog rendering, silent mode-`0600` catalog publication, unchanged external receipt bytes and mode after verify, and fake-`/proc` detection of a PID-relative Planimation overlap from `python -- scripts/phase3/generate_planimation_vlm.py` as a direct script without module reinterpretation.

Final Oracle remediation review reported no blocking findings after proof of catalog temporary-substitution prevention, final inventory validation for a fresh prepared receipt, and Python `--` direct-script recognition without module reinterpretation.

Earlier `27 passed in 8.35s` and `72 passed, 1 deselected in 8.26s` results remain historical evidence in `commands.md`; they were not relabeled as latest reruns.

## Residual environment limitation

`tests/phase3/test_phase3_writer_output_layout_lock.py` could not collect in required `ada_vla` Python 3.10 because its pre-existing support imports `typing.assert_never`, a Python 3.11 or newer standard-library symbol. This is an environment-only collection limitation. No lock file, lock test, product writer, organizer code, or support module was changed to work around it.

No planned Task 4 hardening requirement was intentionally omitted.
