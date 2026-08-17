from __future__ import annotations

import math
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

from .cgas_candidate_accounting import accounting_slice
from .cgas_candidate_contracts import (
    CandidateConfig,
    CandidateContractError,
    RangeReceipt,
    canonical_json_bytes,
    load_config,
)
from .cgas_candidate_publication import materialize_slice
from .cgas_candidate_publication_fs import PublicationSpec, publish_files
from .cgas_candidate_space import (
    JsonValue,
    build_candidate,
    integer_partitions,
    lehmer_steps,
    lehmer_unrank,
    ordered_families,
    stream_capacity,
)

REPORT_NAMES: Final = (
    "canonical-graph-vectors.json",
    "combinatorics.json",
    "exhaustion.json",
    "lehmer-vectors.json",
)
_REPORT_COMMIT: Final = "exhaustion.json"


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    frontiers: dict[int, int]
    ranges: tuple[RangeReceipt, ...]
    report_root: Path


def _frontiers(config: CandidateConfig, emit_prefix: int) -> dict[int, int]:
    result: dict[int, int] = {}
    for stream in config.streams:
        capacity = stream_capacity(stream.object_count)
        limit = min(emit_prefix, capacity)
        complete = limit // stream.raw_quota * stream.raw_quota
        result[stream.object_count] = capacity if capacity <= emit_prefix else complete
    return result


def _n4_combinatorics() -> dict[str, JsonValue]:
    rows, planners = accounting_slice(4, 0, stream_capacity(4))
    unique_ids = {row.candidate_id for row in rows}
    solved_ids = {row.candidate_id for row in rows if row.status == "solved"}
    return {
        "canonical_ids": len(unique_ids),
        "raw_candidates": len(rows),
        "retained_nontrivial_ids": len(planners),
        "solved_ids": len(solved_ids),
    }


def _report_payloads(config: CandidateConfig, emit_prefix: int) -> dict[str, dict[str, JsonValue]]:
    frontiers = _frontiers(config, emit_prefix)
    streams = tuple(stream.object_count for stream in config.streams)
    twelve_signatures = {
        family.composition_signature
        for family in ordered_families(12)
        if len(family.partial_goal_partition) < 12
    } if 12 in streams else set()
    first_leaf = build_candidate(1, 0)
    graph_vectors: dict[str, JsonValue] = {
        "one_object_candidate_id": first_leaf.candidate_id,
        "one_object_leaf": first_leaf.leaf_bytes.decode("ascii"),
        "schema_version": "cgas_canonical_graph_vectors_v1",
        "stream_first_candidate_ids": {
            str(object_count): build_candidate(object_count, 0).candidate_id
            for object_count in streams
        },
    }
    combinatorics: dict[str, JsonValue] = {
        "four_object": _n4_combinatorics() if 4 in streams else None,
        "schema_version": "cgas_candidate_combinatorics_v1",
        "signature_space": {
            "bound": 847 if 12 in streams else None,
            "retained_12_object_signatures": len(twelve_signatures) if 12 in streams else None,
            "witness": 11 if 12 in streams else None,
        },
        "streams": {
            str(object_count): {
                "capacity": stream_capacity(object_count),
                "family_count": len(ordered_families(object_count)),
                "partition_count": len(integer_partitions(object_count)),
            }
            for object_count in streams
        },
    }
    exhaustion: dict[str, JsonValue] = {
        "emit_prefix": emit_prefix,
        "frontiers": {str(key): value for key, value in frontiers.items()},
        "schema_version": "cgas_candidate_exhaustion_v1",
        "streams": {
            str(object_count): {
                "capacity": stream_capacity(object_count),
                "exhausted": frontier == stream_capacity(object_count),
                "frontier": frontier,
            }
            for object_count, frontier in frontiers.items()
        },
    }
    lehmer_vectors: dict[str, JsonValue] = {
        "schema_version": "cgas_lehmer_vectors_v1",
        "streams": {
            str(object_count): {
                "first": {
                    "ordinal": 0,
                    "permutation": list(lehmer_unrank(object_count, 0)),
                    "steps": [asdict(step) for step in lehmer_steps(object_count, 0)],
                },
                "last": {
                    "ordinal": math.factorial(object_count) - 1,
                    "permutation": list(lehmer_unrank(object_count, math.factorial(object_count) - 1)),
                    "steps": [asdict(step) for step in lehmer_steps(object_count, math.factorial(object_count) - 1)],
                },
            }
            for object_count in streams
        },
    }
    return {
        "canonical-graph-vectors.json": graph_vectors,
        "combinatorics.json": combinatorics,
        "exhaustion.json": exhaustion,
        "lehmer-vectors.json": lehmer_vectors,
    }


def _report_bytes(payloads: dict[str, dict[str, JsonValue]]) -> dict[str, bytes]:
    return {name: canonical_json_bytes(payload) + b"\n" for name, payload in payloads.items()}


def _verify_reports(report_root: Path, expected: dict[str, bytes]) -> bool:
    if not report_root.exists():
        return False
    names = set(path.name for path in report_root.iterdir()) if report_root.is_dir() else set()
    if report_root.is_symlink() or not report_root.is_dir():
        raise CandidateContractError("artifact_mismatch", report_root)
    if _REPORT_COMMIT not in names:
        return False
    if names != set(REPORT_NAMES):
        raise CandidateContractError("artifact_mismatch", report_root)
    if any((report_root / name).read_bytes() != contents for name, contents in expected.items()):
        raise CandidateContractError("artifact_mismatch", report_root)
    return True


def _publish_reports(report_root: Path, expected: dict[str, bytes]) -> None:
    report_root.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".reports-stage-", dir=report_root.parent) as temporary:
        stage = Path(temporary)
        for name, contents in expected.items():
            descriptor = os.open(stage / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(contents)
                handle.flush()
                os.fsync(handle.fileno())
        try:
            publish_files(PublicationSpec(stage, report_root, REPORT_NAMES, _REPORT_COMMIT))
        except FileExistsError as error:
            if not _verify_reports(report_root, expected):
                raise CandidateContractError("artifact_mismatch", report_root) from error


def bootstrap(config_path: Path, output: Path, emit_prefix: int, report_root: Path) -> BootstrapResult:
    if emit_prefix <= 0:
        raise CandidateContractError("emit_prefix_malformed")
    config = load_config(config_path)
    expected_reports = _report_bytes(_report_payloads(config, emit_prefix))
    reports_exist = _verify_reports(report_root, expected_reports)
    frontiers = _frontiers(config, emit_prefix)
    receipts: list[RangeReceipt] = []
    for stream in config.streams:
        frontier = frontiers[stream.object_count]
        start = 0
        while start + stream.raw_quota <= frontier:
            receipts.append(materialize_slice(config_path, output, stream.object_count, start, stream.raw_quota))
            start += stream.raw_quota
        if start < frontier:
            receipts.append(materialize_slice(config_path, output, stream.object_count, start, frontier - start))
    if not reports_exist:
        _publish_reports(report_root, expected_reports)
    return BootstrapResult(frontiers, tuple(receipts), report_root)
