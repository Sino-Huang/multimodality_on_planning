from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path


ARTIFACT_NAMES = ("steps", "schema", "steps_manifest.json")


def publish_steps(candidate: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix=f".{output.name}.publication-", dir=output.parent))
    published: list[tuple[Path, Path, Path | None]] = []
    try:
        for name in ARTIFACT_NAMES:
            source = candidate / name
            destination = output / name
            previous = backup / name if destination.exists() else None
            if previous is not None:
                os.replace(destination, previous)
            try:
                os.replace(source, destination)
            except OSError:
                if previous is not None:
                    os.replace(previous, destination)
                raise
            published.append((source, destination, previous))
    except OSError as primary_error:
        try:
            _restore(published)
        except OSError as rollback_error:
            raise primary_error from rollback_error
        try:
            shutil.rmtree(backup)
        except OSError as cleanup_error:
            raise primary_error from cleanup_error
        raise
    shutil.rmtree(backup)
    candidate.rmdir()


def _restore(published: list[tuple[Path, Path, Path | None]]) -> None:
    for source, destination, previous in reversed(published):
        os.replace(destination, source)
        if previous is not None:
            os.replace(previous, destination)
