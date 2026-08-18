"""Read-only legacy Phase 3 audit pinned to issue #8 attempt-002 by default."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Sequence


EXPECTED_COUNT = 16_822
EXPECTED_REVISION = "b9fba250f5269a20cb0e950375720281621fb030"
EXPECTED_BACKEND = "94d82afb5ee122ce579dd11ca1953b7c85ca5824"
EXPECTED_PORT = 18084
LEGACY_ADAPTER_SCHEMA = "cgas_phase3_pilot_planimation_adapter_v3"
EXECUTION_RECEIPT_PATH = Path(__file__).with_name("2026-08-17-cgas-phase3-pilot-production-attempt-002-execution-receipt.json")


def _default_repository() -> Path:
    return Path(__file__).resolve().parents[3]


def _json_document(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"not an object: {path}")
    return value


def _json_lines(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"not an object: {path}:{number}")
        rows.append(value)
    return rows


def _artifact_path(repository: Path, value: object) -> Path:
    path = Path(str(value))
    return path.resolve() if path.is_absolute() else (repository / path).resolve()


def _legacy_file_sha256(path: Path) -> str:
    """Legacy Phase 3 evidence rehash only; this is not a generic hash layer."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _check(checks: list[tuple[str, bool, str]], name: str, passed: bool, detail: str) -> None:
    checks.append((name, passed, detail))


def audit(repository: Path, attempt_root: Path, execution_receipt_path: Path) -> tuple[list[tuple[str, bool, str]], int]:
    repository = repository.resolve()
    root = attempt_root.resolve()
    request = repository / "tmp/cgas-phase3-pilot-expansion-index-v1/missing-render-request.jsonl"
    paths = {
        "manifest": root / "diagnostics/state_render_manifest.jsonl",
        "checkpoint": root / "diagnostics/render-checkpoint.jsonl",
        "run_contract": root / "diagnostics/run-contract.json",
        "adapter_report": root / "reports/render-report.json",
        "production_report": root / "reports/planimation-production-report.json",
        "backend_log": root / "backend.log",
    }
    try:
        request_rows = _json_lines(request)
        manifest = _json_lines(paths["manifest"])
        checkpoint = _json_lines(paths["checkpoint"])
        run_contract = _json_document(paths["run_contract"])
        adapter_report = _json_document(paths["adapter_report"])
        production_report = _json_document(paths["production_report"])
        execution_receipt = _json_document(execution_receipt_path)
    except Exception as error:
        return [("setup", False, f"{type(error).__name__}: {error}")], 1

    sys.path.insert(0, str(repository))
    from scripts.phase3.render_semantics import validate_render_artifacts

    checks: list[tuple[str, bool, str]] = []
    capture_valid = (
        execution_receipt.get("schema_version") == "cgas_issue8_attempt002_execution_receipt_v1"
        and execution_receipt.get("exit_code") == 0
        and execution_receipt.get("authorized_port") == EXPECTED_PORT
        and execution_receipt.get("attempt_root") == str(root)
        and execution_receipt.get("command") == "source ~/cd_vlaplan && python .claude/evidence/cgas-phase3-pilot-rendering/audit_cgas_issue8_attempt002.py"
        and execution_receipt.get("completion_paths")
        == {
            "adapter_report": "reports/render-report.json",
            "backend_log": "backend.log",
            "checkpoint": "diagnostics/render-checkpoint.jsonl",
            "manifest": "diagnostics/state_render_manifest.jsonl",
            "production_report": "reports/planimation-production-report.json",
            "run_contract": "diagnostics/run-contract.json",
        }
    )
    _check(checks, "captured_exit", capture_valid, f"receipt={execution_receipt_path}")
    _check(checks, "production_status", production_report.get("status") == "complete", str(production_report.get("status")))
    _check(checks, "adapter_status", adapter_report.get("status") == "complete", str(adapter_report.get("status")))
    expected_counts = {"requested": 16822, "processed": 16822, "succeeded": 16822, "failed": 0, "remaining": 0, "duplicate": 0, "collision": 0}
    _check(checks, "adapter_counts", adapter_report.get("counts") == expected_counts, str(adapter_report.get("counts")))
    _check(checks, "manifest_count", len(manifest) == EXPECTED_COUNT, str(len(manifest)))
    _check(checks, "checkpoint_count", len(checkpoint) == EXPECTED_COUNT, str(len(checkpoint)))
    _check(checks, "request_count", len(request_rows) == EXPECTED_COUNT, str(len(request_rows)))
    request_ids = [str(row.get("state_sha256")) for row in request_rows]
    manifest_ids = [str(row.get("state_sha256")) for row in manifest]
    checkpoint_ids = [str(row.get("state_sha256")) for row in checkpoint]
    _check(checks, "request_unique", len(set(request_ids)) == EXPECTED_COUNT, str(len(set(request_ids))))
    _check(checks, "manifest_unique", len(set(manifest_ids)) == EXPECTED_COUNT, str(len(set(manifest_ids))))
    _check(checks, "checkpoint_unique", len(set(checkpoint_ids)) == EXPECTED_COUNT, str(len(set(checkpoint_ids))))
    _check(checks, "manifest_request_set", set(manifest_ids) == set(request_ids), f"delta={len(set(manifest_ids) ^ set(request_ids))}")
    _check(checks, "checkpoint_request_set", set(checkpoint_ids) == set(request_ids), f"delta={len(set(checkpoint_ids) ^ set(request_ids))}")

    record_errors: list[str] = []
    semantic_errors: list[str] = []
    status_counts: Counter[str] = Counter()
    planning_counts: Counter[str] = Counter()
    sample_indexes = set(range(0, EXPECTED_COUNT, max(1, EXPECTED_COUNT // 128)))
    sample_indexes.add(EXPECTED_COUNT - 1)
    sample_count = 0
    artifact_count = 0
    for index, row in enumerate(manifest):
        state_id = str(row.get("state_sha256"))
        status_counts[str(row.get("status"))] += 1
        planning_counts[str(row.get("planning_status"))] += 1
        metadata = row.get("planner_metadata")
        if not isinstance(metadata, dict):
            record_errors.append(f"{state_id}: planner_metadata")
            continue
        actions = metadata.get("actions")
        if not all(
            (
                row.get("schema_version") == LEGACY_ADAPTER_SCHEMA,
                row.get("status") == "success",
                row.get("planning_status") == "planning_submitted",
                row.get("planimation_request_count") == 1,
                metadata.get("source") == "local_lama_first",
                metadata.get("alias") == "lama-first",
                metadata.get("planner_revision") == EXPECTED_REVISION,
                isinstance(actions, list) and bool(actions),
                metadata.get("planning_status") == "planning_submitted",
                metadata.get("planimation_request_count") == 1,
            )
        ):
            record_errors.append(f"{state_id}: provenance/status")
            continue
        frame = _artifact_path(repository, row.get("frame_path"))
        trace = _artifact_path(repository, row.get("trace_path"))
        plan = _artifact_path(repository, metadata.get("plan_path"))
        if any(not path.is_file() or not path.is_relative_to(root) for path in (frame, trace, plan)):
            record_errors.append(f"{state_id}: artifact path")
            continue
        if row.get("semantic_image_metrics") is None or row.get("semantic_image_qa") is None:
            record_errors.append(f"{state_id}: stored semantic receipt")
            continue
        if index in sample_indexes:
            sample_count += 1
            if _legacy_file_sha256(frame) != row.get("png_sha256") or _legacy_file_sha256(trace) != row.get("vfg_sha256"):
                semantic_errors.append(f"{state_id}: artifact hash")
                continue
            try:
                receipt = validate_render_artifacts(trace, frame)
            except Exception as error:
                semantic_errors.append(f"{state_id}: {type(error).__name__}: {error}")
                continue
            if receipt.status != "success":
                semantic_errors.append(f"{state_id}: {receipt.status}:{receipt.reason}")
                continue
        artifact_count += 1
    _check(checks, "record_contracts", not record_errors, f"errors={len(record_errors)} first={record_errors[:3]}")
    _check(checks, "artifact_inventory", artifact_count == EXPECTED_COUNT, f"checked={artifact_count}")
    _check(checks, "sampled_hash_semantics", not semantic_errors and sample_count == 130, f"sampled={sample_count} errors={len(semantic_errors)} first={semantic_errors[:3]}")
    _check(checks, "status_distribution", status_counts == {"success": EXPECTED_COUNT}, str(dict(status_counts)))
    _check(checks, "planning_distribution", planning_counts == {"planning_submitted": EXPECTED_COUNT}, str(dict(planning_counts)))

    authorization = production_report.get("authorization")
    network = production_report.get("network")
    _check(checks, "authorization_object", isinstance(authorization, dict), type(authorization).__name__)
    _check(checks, "network_object", isinstance(network, dict), type(network).__name__)
    expected_base = f"http://127.0.0.1:{EXPECTED_PORT}"
    if isinstance(authorization, dict):
        _check(checks, "solver_pin", authorization.get("solver_url") == expected_base + "/forbidden-solver", str(authorization.get("solver_url")))
        _check(checks, "fd_revision_pin", authorization.get("fast_downward_revision") == EXPECTED_REVISION, str(authorization.get("fast_downward_revision")))
        _check(checks, "backend_pin", authorization.get("backend_commit") == EXPECTED_BACKEND, str(authorization.get("backend_commit")))
    if isinstance(network, dict):
        urls = network.get("recorded_post_urls")
        valid_urls = isinstance(urls, list) and len(urls) == EXPECTED_COUNT and set(urls) == {expected_base + "/upload/pddl"}
        _check(checks, "network_urls", valid_urls, f"count={len(urls) if isinstance(urls, list) else 'invalid'}")
        _check(checks, "network_count", network.get("call_count") == EXPECTED_COUNT, str(network.get("call_count")))
        _check(checks, "hosted_zero", network.get("hosted_requests") == 0, str(network.get("hosted_requests")))
    render_config = run_contract.get("render_config")
    planner = run_contract.get("production_renderer")
    _check(checks, "run_contract_root", run_contract.get("request_path") == str(request.resolve()), str(run_contract.get("request_path")))
    _check(checks, "run_contract_config", isinstance(render_config, dict) and render_config.get("base_url") == expected_base and render_config.get("solver_url") == expected_base + "/forbidden-solver", str(render_config))
    _check(checks, "run_contract_planner", isinstance(planner, dict) and planner.get("planner_revision") == EXPECTED_REVISION and planner.get("alias") == "lama-first", str(planner))
    backend_text = paths["backend_log"].read_text(encoding="utf-8", errors="replace")
    _check(checks, "backend_post_count", len(re.findall(r'"POST /upload/pddl HTTP/1\.1" 200 ', backend_text)) == EXPECTED_COUNT, str(backend_text.count("POST /upload/pddl")))
    errors = [line for line in backend_text.splitlines() if re.search(r"error|traceback|exception", line, re.IGNORECASE)]
    _check(checks, "backend_no_errors", not errors, f"count={len(errors)} first={errors[:3]}")
    _check(checks, "backend_no_solver_fallback", "/forbidden-solver" not in backend_text, "forbidden-solver absent")
    attempt_one = repository / "outputs/image_frames/cgas-phase3-pilot-production-attempt-001"
    artifacts = [_artifact_path(repository, row.get("frame_path")) for row in manifest] + [_artifact_path(repository, row.get("trace_path")) for row in manifest]
    _check(checks, "attempt_one_not_imported", all(path.is_relative_to(root) and not path.is_relative_to(attempt_one) for path in artifacts), "all artifacts belong to attempt-002")
    return checks, 0 if all(passed for _, passed, _ in checks) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only audit of issue #8 attempt-002.")
    parser.add_argument("--repository-root", type=Path, default=_default_repository())
    parser.add_argument("--attempt-root", type=Path)
    parser.add_argument("--execution-receipt", type=Path, default=EXECUTION_RECEIPT_PATH)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    parsed = build_parser().parse_args(arguments)
    root = parsed.attempt_root or parsed.repository_root / "outputs/image_frames/cgas-phase3-pilot-production-attempt-002"
    checks, status = audit(parsed.repository_root, root, parsed.execution_receipt)
    for name, passed, detail in checks:
        print(f"{'PASS' if passed else 'FAIL'} {name}: {detail}")
    print(f"SUMMARY checks={len(checks)} failures={sum(not passed for _, passed, _ in checks)}")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
