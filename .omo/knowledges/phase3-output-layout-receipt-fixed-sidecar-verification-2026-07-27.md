# Phase 3 Fixed-Sidecar Receipt Verification

The receipt persistence protocol uses only `.<receipt>.txn` and `.<receipt>.swap` for crash recovery. A replacement interrupted after the atomic exchange converges on the next `write_receipt` call, retaining the replacement receipt and removing both sidecars without creating retired artifacts. A durable txn-only record is also reconciled as unstarted only when the receipt namespace proves it: create has no receipt, or replace retains exactly the transaction's old digest. Recovery removes the digest-verified txn, fsyncs the parent, and lets the requested write start normally; every other txn-only state remains evidence.

Verification performed:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest -q tests/phase3/test_output_layout_*.py
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright --project /tmp/opencode/output-layout-pyrightconfig.json
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3/output_layout_*.py tests/phase3/test_output_layout_*.py
git diff --check -- scripts/phase3/output_layout_receipt.py scripts/phase3/output_layout_receipt_fs.py scripts/phase3/output_layout_receipt_io.py scripts/phase3/output_layout_receipt_transaction.py scripts/phase3/output_layout_receipt_transaction_values.py scripts/phase3/output_layout_receipt_values.py tests/phase3/test_output_layout_receipt_adversarial.py tests/phase3/test_output_layout_inventory.py tests/phase3/test_output_layout_snapshot_adversarial.py
```

The output-layout pytest suite passed 153 tests. Strict Basedpyright completed with 0 errors, 0 warnings, and 0 notes.
