"""Verify two issue-111 v3 qualification runs and publish their selected release."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from examples.planning_benchmark_slice.bfs_pilot import BAND_BOUNDS, BANDS, DOMAINS, SPLITS
from src.data_collect.splits import whole_instance_identity

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_DESTINATION = _REPO_ROOT / "data" / "bfs_pilot_v3"
_ATTEMPT_ID = "qualification-attempt-002"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first-root", type=Path, required=True)
    parser.add_argument("--second-root", type=Path, required=True)
    parser.add_argument("--destination", type=Path, default=_DEFAULT_DESTINATION)
    args = parser.parse_args()
    report = publish(args.first_root.resolve(), args.second_root.resolve(), args.destination.resolve())
    print(json.dumps(report, sort_keys=True))
    return 0


def publish(first: Path, second: Path, destination: Path) -> dict[str, Any]:
    if destination.exists():
        raise FileExistsError(f"BFS v3 release destination already exists: {destination}")
    for relative in ("candidates.jsonl", "selected-manifest.jsonl", "qualification-report.json", "gate-receipt.json"):
        _require_equal(first / relative, second / relative)
    first_tasks = _tree_payloads(first / "tasks")
    second_tasks = _tree_payloads(second / "tasks")
    if first_tasks != second_tasks:
        raise ValueError("BFS v3 selected task bytes differ between qualification runs")

    report = _json_object(first / "qualification-report.json")
    receipt = _json_object(first / "gate-receipt.json")
    rows = _jsonl_objects(first / "selected-manifest.jsonl")
    required = {(domain, band, split) for domain in DOMAINS for band in BANDS for split in SPLITS}
    cells = {(row.get("domain_id"), row.get("band"), row.get("split")) for row in rows}
    if (
        report.get("outcome") != "PASS"
        or report.get("attempt_id") != _ATTEMPT_ID
        or report.get("selected_count") != 90
        or report.get("missing_cells") != []
        or report.get("test_data_accessed") is not False
        or receipt.get("outcome") != "PASS"
        or len(rows) != 90
        or cells != required
    ):
        raise ValueError("BFS v3 qualification did not produce the complete governed PASS")

    identities: dict[str, str] = {}
    for row in rows:
        domain = str(row["domain_id"])
        split = str(row["split"])
        band = str(row["band"])
        source_root = first / "tasks" / domain / split / band
        domain_bytes = (source_root / "domain.pddl").read_bytes()
        problem_bytes = (source_root / "problem.pddl").read_bytes()
        count = row["expansion_count"]
        lower, upper = BAND_BOUNDS[band]
        identity = whole_instance_identity(domain_bytes, problem_bytes)
        if (
            not isinstance(count, int)
            or isinstance(count, bool)
            or not lower <= count <= upper
            or row.get("domain_hash") != _sha256(domain_bytes)
            or row.get("problem_hash") != _sha256(problem_bytes)
            or row.get("whole_instance_id") != identity
            or identities.get(identity, split) != split
        ):
            raise ValueError(f"BFS v3 selected row failed publication checks: {domain}/{split}/{band}")
        identities[identity] = split

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        shutil.copytree(first / "tasks", staging / "tasks")
        shutil.copy2(first / "selected-manifest.jsonl", staging / "selected-manifest.jsonl")
        attempt = staging / _ATTEMPT_ID
        attempt.mkdir(parents=True)
        for relative in ("candidates.jsonl", "qualification-report.json", "gate-receipt.json"):
            shutil.copy2(first / relative, attempt / relative)
        publication = {
            "attempt_id": _ATTEMPT_ID,
            "candidate_report_sha256": _sha256((first / "candidates.jsonl").read_bytes()),
            "gate_receipt_sha256": _sha256((first / "gate-receipt.json").read_bytes()),
            "qualification_report_sha256": _sha256((first / "qualification-report.json").read_bytes()),
            "schema_version": "bfs_pilot_publication_v3",
            "second_run_byte_identical": True,
            "selected_manifest_sha256": _sha256((first / "selected-manifest.jsonl").read_bytes()),
            "selected_task_count": len(rows),
            "selected_task_file_count": len(first_tasks),
        }
        (staging / "publication.json").write_bytes(_canonical_bytes(publication))
        staging.replace(destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return publication


def _require_equal(first: Path, second: Path) -> None:
    if first.read_bytes() != second.read_bytes():
        raise ValueError(f"BFS v3 qualification artifact differs between runs: {first.name}")


def _tree_payloads(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError(f"BFS v3 artifact must be a JSON object: {path}")
    return value


def _jsonl_objects(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"BFS v3 manifest rows must be JSON objects: {path}")
    return rows


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
