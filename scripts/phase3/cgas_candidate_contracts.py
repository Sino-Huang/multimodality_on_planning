from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .cgas_candidate_space import JsonValue, stream_capacity


@dataclass(frozen=True, slots=True)
class CandidateContractError(RuntimeError):
    code: str
    path: Path | None = None

    def __str__(self) -> str:
        return self.code if self.path is None else f"{self.code}:{self.path}"


@dataclass(frozen=True, slots=True)
class StreamConfig:
    object_count: int
    raw_quota: int


@dataclass(frozen=True, slots=True)
class CandidateConfig:
    schema_version: str
    streams: tuple[StreamConfig, ...]
    sha256: str

    def stream(self, object_count: int) -> StreamConfig:
        for stream in self.streams:
            if stream.object_count == object_count:
                return stream
        raise CandidateContractError("object_count_not_configured")


@dataclass(frozen=True, slots=True)
class RangeReceipt:
    object_count: int
    start_rank: int
    count: int
    end_rank: int
    capacity: int
    config_sha256: str
    raw_accounting_sha256: str
    planner_inputs_sha256: str
    raw_accounting_rows: int
    planner_input_rows: int
    emitted: int
    duplicate: int
    solved: int

    def record(self) -> dict[str, JsonValue]:
        return {
            "capacity": self.capacity,
            "config_sha256": self.config_sha256,
            "count": self.count,
            "end_rank": self.end_rank,
            "files": {
                "planner-inputs.jsonl": {
                    "rows": self.planner_input_rows,
                    "sha256": self.planner_inputs_sha256,
                },
                "raw-accounting.jsonl": {
                    "rows": self.raw_accounting_rows,
                    "sha256": self.raw_accounting_sha256,
                },
            },
            "object_count": self.object_count,
            "schema_version": "cgas_production_candidate_range_v1",
            "start_rank": self.start_rank,
            "status_counts": {
                "duplicate": self.duplicate,
                "emitted": self.emitted,
                "solved": self.solved,
            },
        }


def canonical_json_bytes(value: dict[str, JsonValue]) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_json_line(value: dict[str, JsonValue]) -> bytes:
    return canonical_json_bytes(value) + b"\n"


def sha256(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


def load_config(path: Path) -> CandidateConfig:
    try:
        contents = path.read_bytes()
        payload = json.loads(contents)
    except (OSError, json.JSONDecodeError) as error:
        raise CandidateContractError("config_malformed", path) from error
    if not isinstance(payload, dict) or payload.get("schema_version") != "cgas_production_candidates_v1":
        raise CandidateContractError("config_malformed", path)
    raw_streams = payload.get("streams")
    if not isinstance(raw_streams, list) or not raw_streams:
        raise CandidateContractError("config_malformed", path)
    streams: list[StreamConfig] = []
    for raw_stream in raw_streams:
        if not isinstance(raw_stream, dict):
            raise CandidateContractError("config_malformed", path)
        object_count = raw_stream.get("object_count")
        raw_quota = raw_stream.get("raw_quota")
        if (
            not isinstance(object_count, int)
            or isinstance(object_count, bool)
            or object_count <= 0
            or not isinstance(raw_quota, int)
            or isinstance(raw_quota, bool)
            or raw_quota <= 0
        ):
            raise CandidateContractError("config_malformed", path)
        streams.append(StreamConfig(object_count, raw_quota))
    if len({stream.object_count for stream in streams}) != len(streams):
        raise CandidateContractError("config_malformed", path)
    return CandidateConfig(
        "cgas_production_candidates_v1",
        tuple(sorted(streams, key=lambda item: item.object_count)),
        sha256(contents),
    )


def validate_range(config: CandidateConfig, object_count: int, start_rank: int, count: int) -> StreamConfig:
    stream = config.stream(object_count)
    if start_rank < 0 or count <= 0:
        raise CandidateContractError("range_malformed")
    if start_rank + count > stream_capacity(object_count):
        raise CandidateContractError("range_capacity_exceeded")
    return stream
