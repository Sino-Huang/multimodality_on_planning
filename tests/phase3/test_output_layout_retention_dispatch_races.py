from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.phase3 import output_layout_receipt_transaction, output_layout_view_stage
from scripts.phase3.output_layout_receipt_transaction_values import digest_bytes


def test_stage_cleanup_retains_its_original_private_name_without_rename_or_delete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a private stage whose unique name must remain durable evidence.
    parent_descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    stage = output_layout_view_stage.create_private_stage(parent_descriptor, Path("datasets/view"))

    def reject_rename(
        source: os.PathLike[str] | str,
        destination: os.PathLike[str] | str,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
    ) -> None:
        raise AssertionError(f"cleanup must not rename {source} to {destination}")

    def reject_remove(name: os.PathLike[str] | str, *, dir_fd: int | None = None) -> None:
        raise AssertionError(f"cleanup must not delete {name}")

    def reject_renameat2(
        parent_descriptor: int,
        source_name: str,
        destination_name: str,
        flags: int,
    ) -> None:
        raise AssertionError(f"cleanup must not rename {source_name} to {destination_name}")

    monkeypatch.setattr(output_layout_view_stage.os, "rename", reject_rename)
    monkeypatch.setattr(output_layout_view_stage.os, "replace", reject_rename)
    monkeypatch.setattr(output_layout_view_stage.os, "unlink", reject_remove)
    monkeypatch.setattr(output_layout_view_stage.os, "rmdir", reject_remove)
    monkeypatch.setattr(output_layout_view_stage.output_layout_view_fs, "_renameat2", reject_renameat2)
    try:
        # When: cleanup retains the failed stage.
        output_layout_view_stage.cleanup(stage)

        # Then: no cleanup pathname mutation is performed.
        assert (tmp_path / stage.name).is_dir()
        assert stage.identity.matches(os.stat(stage.name, dir_fd=parent_descriptor, follow_symlinks=False))
        assert not (tmp_path / f"{stage.name}.cleanup").exists()
    finally:
        os.close(stage.descriptor)
        os.close(parent_descriptor)


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
