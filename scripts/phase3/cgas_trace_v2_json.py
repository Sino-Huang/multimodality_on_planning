from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .local_planner_types import JSONValue


@dataclass(frozen=True, slots=True)
class TraceJsonError(RuntimeError):
    rule: str
    path: Path

    def __str__(self) -> str:
        return f"{self.rule}: {self.path}"


def canonical_json_bytes(value: JSONValue, path: Path, rule: str) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise TraceJsonError(rule, path) from error


def parse_canonical_json_line(line: bytes, path: Path, rule: str) -> dict[str, JSONValue]:
    if not line.endswith(b"\n") or line.endswith(b"\n\n"):
        raise TraceJsonError(rule, path)
    try:
        value: JSONValue = json.loads(line)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TraceJsonError(rule, path) from error
    if not isinstance(value, dict) or canonical_json_bytes(value, path, rule) + b"\n" != line:
        raise TraceJsonError(rule, path)
    return dict(value)
