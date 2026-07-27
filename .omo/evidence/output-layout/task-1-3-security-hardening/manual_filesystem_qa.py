from __future__ import annotations

import os
import stat
import time
from pathlib import Path

import pytest

from scripts.phase3.output_layout_inventory import OutputLayoutInventoryError, read_receipt
from scripts.phase3 import output_layout_view_stage


def test_fifo_receipt_rejection_and_unowned_stage_quarantine(tmp_path: Path) -> None:
    receipt_path = tmp_path / "receipt.json"
    os.mkfifo(receipt_path, 0o600)
    os.chmod(receipt_path, 0o600)

    started = time.monotonic()
    with pytest.raises(OutputLayoutInventoryError, match="regular file"):
        read_receipt(receipt_path)
    elapsed = time.monotonic() - started

    assert elapsed < 1.0
    assert stat.S_ISFIFO(receipt_path.lstat().st_mode)

    parent_descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    stage = output_layout_view_stage.create_private_stage(parent_descriptor, Path("datasets/view"))
    try:
        racer = tmp_path / stage.name / "racer-owned"
        racer.write_text("retain\n", encoding="utf-8")

        with pytest.raises(OSError):
            output_layout_view_stage.cleanup(stage)

        retained = tmp_path / f"{stage.name}.cleanup" / "racer-owned"
        assert retained.read_text(encoding="utf-8") == "retain\n"
    finally:
        os.close(stage.descriptor)
        os.close(parent_descriptor)
