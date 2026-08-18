from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.phase3 import output_layout_receipt_transaction
from scripts.phase3.output_layout_receipt_transaction_values import digest_bytes


def test_receipt_cleanup_does_not_delete_racer_replaced_at_final_unlink_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: an owned receipt sidecar and an attacker replacing the validated quarantine.
    sidecar_name = ".receipt.json.txn"
    sidecar = tmp_path / sidecar_name
    sidecar.write_bytes(b"transaction")
    sidecar.chmod(0o600)
    parent_descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    expected = digest_bytes(b"transaction")
    original_unlink = output_layout_receipt_transaction.os.unlink
    quarantine_name = f"{sidecar_name}.remove"

    def replace_at_final_unlink(name: str, *, dir_fd: int | None = None) -> None:
        if name == quarantine_name:
            os.rename(name, f"{name}.owned", src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
            descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=dir_fd)
            os.close(descriptor)
        original_unlink(name, dir_fd=dir_fd)

    monkeypatch.setattr(output_layout_receipt_transaction.os, "unlink", replace_at_final_unlink)
    try:
        # When: cleanup reaches the current terminal dispatcher.
        output_layout_receipt_transaction._remove_entry(parent_descriptor, sidecar_name, expected, tmp_path / "receipt.json")

        # Then: cleanup transitions the sidecar into durable retained evidence.
        assert tuple(tmp_path.glob(f"{sidecar_name}.retained-*"))
    finally:
        os.close(parent_descriptor)
