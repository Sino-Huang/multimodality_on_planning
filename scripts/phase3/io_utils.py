from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Iterable


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def ensure_layout(output_root: Path) -> None:
    for relative in ("diagnostics", "reports", "schema"):
        (output_root / relative).mkdir(parents=True, exist_ok=True)


def clear_output_root(output_root: Path, *, input_root: Path | None = None) -> None:
    _assert_safe_output_root(output_root, input_root=input_root)
    if output_root.exists():
        shutil.rmtree(output_root)
    ensure_layout(output_root)


def _assert_safe_output_root(output_root: Path, *, input_root: Path | None) -> None:
    root = repo_root().resolve()
    output = output_root.resolve()
    forbidden = {Path("/").resolve(), root, Path.cwd().resolve(), Path.home().resolve()}
    allowed_parents = tuple(parent.resolve() for parent in (root / "data", root / "outputs", root / "tmp"))
    forbidden.update(allowed_parents)
    if output in forbidden:
        raise RuntimeError(f"unsafe output root: {output_root}")
    if input_root is not None:
        input_path = input_root.resolve()
        if output == input_path or input_path.is_relative_to(output):
            raise RuntimeError(f"unsafe output root: {output_root}")
    if not any(output.is_relative_to(parent) for parent in allowed_parents):
        raise RuntimeError(f"unsafe output root: {output_root}")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if text:
                rows.append(json.loads(text))
    return rows


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=True) + "\n")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")


def stable_hash(value: Any) -> str:
    text = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relpath(path: str | Path, *, root: Path | None = None) -> str:
    root = (root or repo_root()).resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        return candidate.as_posix()
    try:
        return candidate.resolve().relative_to(root).as_posix()
    except ValueError:
        return candidate.name


def resolve_repo_path(path_text: str | None, *, root: Path | None = None) -> Path | None:
    if not path_text:
        return None
    path = Path(path_text)
    if path.is_absolute():
        return path
    return (root or repo_root()) / path


def count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())
