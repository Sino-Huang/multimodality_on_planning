# Phase 3 Output Layout Wave 1 Security Hardening

## Scope

This pass hardens synthetic output-layout filesystem operations only. It does
not invoke an organizer command, move data, write receipts under `outputs/`,
or change the approved plan.

## Changes

- Added explicit bounded directory recursion to deterministic snapshots and
  protected-content token calculation.
- Hardened receipt and fixed-sidecar reads with no-follow/nonblocking opens,
  regular-file validation, and exact `0600` public receipt read enforcement.
- Added aggregate JSON collection accounting before typed receipt parsing.
- Made private-stage cleanup identity-owned: unknown or replaced children are
  quarantined rather than destructively removed.
- Updated parse/recovery fixtures to be explicitly `0600` where their intended
  assertion is beyond the receipt permission boundary.

## Commands

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest -q tests/phase3/test_output_layout_acceptance_security.py
source ~/cd_vlaplan && source .venv/bin/activate && pytest -q tests/phase3/test_output_layout_*.py
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright scripts/phase3/output_layout_snapshot.py scripts/phase3/output_layout_view_content.py scripts/phase3/output_layout_receipt_io.py scripts/phase3/output_layout_receipt_transaction.py scripts/phase3/output_layout_receipt_values.py scripts/phase3/output_layout_view_stage.py scripts/phase3/output_layout_view.py tests/phase3/test_output_layout_acceptance_security.py tests/phase3/test_output_layout_receipt_adversarial.py tests/phase3/test_output_layout_inventory.py .omo/evidence/output-layout/task-1-3-security-hardening/manual_filesystem_qa.py
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3/output_layout_snapshot.py scripts/phase3/output_layout_view_content.py scripts/phase3/output_layout_receipt_io.py scripts/phase3/output_layout_receipt_transaction.py scripts/phase3/output_layout_receipt_values.py scripts/phase3/output_layout_view_stage.py scripts/phase3/output_layout_view.py tests/phase3/test_output_layout_acceptance_security.py tests/phase3/test_output_layout_receipt_adversarial.py tests/phase3/test_output_layout_inventory.py .omo/evidence/output-layout/task-1-3-security-hardening/manual_filesystem_qa.py
source ~/cd_vlaplan && source .venv/bin/activate && pytest -q .omo/evidence/output-layout/task-1-3-security-hardening/manual_filesystem_qa.py
```

Results: 18 focused acceptance tests passed; 172 output-layout tests passed;
Basedpyright reported 0 errors, 0 warnings, 0 notes; compileall exited 0; and
the manual FIFO/unowned-child QA passed. Evidence logs are in
`.omo/evidence/output-layout/task-1-3-security-hardening/`.

## Boundaries

The manual QA creates its FIFO and private stage solely below pytest `tmp_path`
and closes both opened descriptors. `git status --short -- outputs` was empty,
and no command in this pass targeted a real `outputs/` path.
