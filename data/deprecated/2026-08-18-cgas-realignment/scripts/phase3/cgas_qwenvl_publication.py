from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path


def publish_candidate(candidate: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix=f".{output.name}.publication-", dir=output.parent))
    backup.rmdir()
    moved_previous = False
    try:
        if output.exists():
            os.replace(output, backup)
            moved_previous = True
        os.replace(candidate, output)
    except OSError as primary_error:
        if moved_previous:
            try:
                os.replace(backup, output)
            except OSError as rollback_error:
                raise primary_error from rollback_error
        try:
            shutil.rmtree(candidate)
        except OSError as cleanup_error:
            raise primary_error from cleanup_error
        raise
    if moved_previous:
        shutil.rmtree(backup)
