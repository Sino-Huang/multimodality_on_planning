"""Prepare the reviewed issue-62 source panel from frozen BFWS evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from examples.planning_benchmark_slice.astar_hmax import HMaxHeuristic, UnsupportedHMaxTaskError
from examples.planning_benchmark_slice.astar_landmarks import LandmarkCountHeuristic
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority
from examples.planning_benchmark_slice.strips_relaxation import (
    UnsupportedSTRIPSTaskError,
    estimated_grounded_operator_count,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEVELOPMENT = Path("data/bfws_phase_v1/development-manifest.jsonl")
_BFWS_AUTHORIZATION = Path("configs/experiments/bfws_phase_authorization_v1.json")
_BFWS_EVIDENCE = Path("data/bfws_phase_v1/exact-traces/manifests/bfws-expert-traces.json")
_OUTPUT = Path("data/astar_paired_phase_v1")
_BUDGET_POLICY = "shared_ceiling_by_development_difficulty"
_BUDGET_BASIS = "maximum_issue57_exact_bfws_expansion_count_by_source_difficulty"
_GROUNDED_OPERATOR_CEILING = 200_000
_SELECTION_POLICY = {
    "astar_outcome_used_for_selection": False,
    "estimated_grounded_operator_ceiling": _GROUNDED_OPERATOR_CEILING,
    "estimated_grounded_operator_formula": "sum(object_count ** action_parameter_count)",
    "required_adapters": ["astar_hmax", "astar_landmark_count"],
    "unsupported_adapter_contract": "exclude",
}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, default=_REPO_ROOT)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--refresh", action="store_true")
    args = parser.parse_args(argv)

    root = args.artifact_root.resolve()
    products, summary = _build_products(root)
    if args.dry_run:
        print(
            json.dumps(
                {**summary, "status": "dry_run_valid_source", "writes": 0},
                sort_keys=True,
            ),
            flush=True,
        )
        return 0
    if args.check:
        for path, payload in products.items():
            if not path.is_file() or path.read_bytes() != payload:
                raise ValueError(
                    f"A* paired source differs from deterministic regeneration: {path}"
                )
        print(
            json.dumps(
                {**summary, "checked": len(products), "status": "byte_identical"},
                sort_keys=True,
            ),
            flush=True,
        )
        return 0

    differing = [
        path for path, payload in products.items() if path.is_file() and path.read_bytes() != payload
    ]
    if differing:
        raise ValueError(
            f"immutable A* paired source v1 differs; create v2 instead: {differing[0]}"
        )
    missing = [(path, payload) for path, payload in products.items() if not path.is_file()]
    for path, payload in missing:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    print(
        json.dumps(
            {**summary, "status": "refreshed", "written": len(missing)},
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


def _build_products(root: Path) -> tuple[dict[Path, bytes], dict[str, object]]:
    development_path = root / _DEVELOPMENT
    authorization_path = root / _BFWS_AUTHORIZATION
    evidence_path = root / _BFWS_EVIDENCE
    output_root = root / _OUTPUT

    development = _jsonl_objects(development_path)
    authorization_bytes, authorization = _canonical_object(
        authorization_path, "issue-56 BFWS authorization"
    )
    evidence_bytes, evidence = _canonical_object(evidence_path, "issue-57 BFWS evidence")
    _validate_authorization(authorization)
    traces = _validated_evidence_traces(evidence, len(development))

    trace_by_identity: dict[tuple[str, str, str, str, str], Mapping[str, Any]] = {}
    for trace in traces:
        key = _identity_key(trace)
        if key in trace_by_identity:
            raise ValueError("issue-57 BFWS evidence repeats a source identity")
        trace_by_identity[key] = trace

    started = time.monotonic()
    products: dict[Path, bytes] = {}
    source_rows: list[dict[str, Any]] = []
    expansion_caps: dict[str, int] = {}
    observed_keys: set[tuple[str, str, str, str, str]] = set()
    exclusion_counts: Counter[str] = Counter()
    for completed, row in enumerate(development, start=1):
        _validate_development_row(row)
        domain_path = _repository_path(root, row["domain_path"], "BFWS domain")
        problem_path = _repository_path(root, row["problem_path"], "BFWS problem")
        domain_pddl = domain_path.read_text(encoding="utf-8")
        problem_pddl = problem_path.read_text(encoding="utf-8")
        authority = PDDLStateAuthority.from_pddl(domain_pddl, problem_pddl)
        identity = authority.semantic_task_identity()
        if identity != row["semantic_task_identity"]:
            raise ValueError("BFWS development semantic identity differs from its PDDL task")

        key = (
            row["domain_id"],
            row["difficulty"],
            row["instance_id"],
            identity,
            row["split"],
        )
        trace = trace_by_identity.get(key)
        if trace is None:
            raise ValueError("BFWS development task has no matching issue-57 trace")
        if trace.get("max_expansions") != row["exact_reference_expansion_count"]:
            raise ValueError("issue-57 expansion evidence differs from the BFWS development row")
        observed_keys.add(key)

        estimate = estimated_grounded_operator_count(authority)
        print(
            json.dumps(
                {
                    "completed": completed - 1,
                    "elapsed_seconds": round(time.monotonic() - started, 6),
                    "estimated_grounded_operator_count": estimate,
                    "estimated_remaining_seconds": None,
                    "instance_id": row["instance_id"],
                    "stage": "source_validation_started",
                    "total": len(development),
                },
                sort_keys=True,
            ),
            flush=True,
        )
        exclusion_reason: str | None = None
        if estimate > _GROUNDED_OPERATOR_CEILING:
            exclusion_reason = "grounded_operator_ceiling"
        else:
            try:
                HMaxHeuristic(authority)
                LandmarkCountHeuristic(authority)
            except (UnsupportedHMaxTaskError, UnsupportedSTRIPSTaskError):
                exclusion_reason = "unsupported_adapter_contract"
        if exclusion_reason is not None:
            exclusion_counts[exclusion_reason] += 1
            elapsed = time.monotonic() - started
            remaining = 0.0 if completed == len(development) else elapsed / completed * (
                len(development) - completed
            )
            print(
                json.dumps(
                    {
                        "completed": completed,
                        "elapsed_seconds": round(elapsed, 6),
                        "estimated_grounded_operator_count": estimate,
                        "estimated_remaining_seconds": round(remaining, 6),
                        "instance_id": row["instance_id"],
                        "selection_status": f"excluded_{exclusion_reason}",
                        "stage": "source_validation",
                        "total": len(development),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            continue

        difficulty = row["difficulty"]
        expansion_caps[difficulty] = max(
            expansion_caps.get(difficulty, 0), row["exact_reference_expansion_count"]
        )
        task_relative = (
            _OUTPUT
            / "tasks"
            / row["domain_id"]
            / difficulty
            / row["split"]
            / f"{row['instance_id']}.json"
        )
        products[root / task_relative] = _canonical_bytes(
            {
                "domain": row["domain_id"],
                "domain_pddl": domain_pddl,
                "instance_id": row["instance_id"],
                "problem_pddl": problem_pddl,
            }
        )
        source_rows.append(
            {
                "difficulty": difficulty,
                "domain_id": row["domain_id"],
                "generation_max_expansions": None,
                "instance_id": row["instance_id"],
                "split": row["split"],
                "task_path": task_relative.as_posix(),
            }
        )
        elapsed = time.monotonic() - started
        remaining = 0.0 if completed == len(development) else elapsed / completed * (
            len(development) - completed
        )
        print(
            json.dumps(
                {
                    "completed": completed,
                    "elapsed_seconds": round(elapsed, 6),
                    "estimated_remaining_seconds": round(remaining, 6),
                    "estimated_grounded_operator_count": estimate,
                    "instance_id": row["instance_id"],
                    "selection_status": "selected",
                    "stage": "source_validation",
                    "total": len(development),
                },
                sort_keys=True,
            ),
            flush=True,
        )

    if observed_keys != set(trace_by_identity):
        raise ValueError("issue-57 BFWS trace coverage differs from the development panel")
    if set(expansion_caps) != {"easy", "medium", "hard"}:
        raise ValueError("BFWS development source does not cover all three frozen difficulties")
    if {row["split"] for row in source_rows} != {"train", "dev"}:
        raise ValueError("A* paired source must retain both train and dev tasks")
    for row in source_rows:
        row["generation_max_expansions"] = expansion_caps[row["difficulty"]]
    source_rows.sort(
        key=lambda row: (row["split"], row["domain_id"], row["difficulty"], row["instance_id"])
    )
    source_bytes = b"".join(_canonical_bytes(row) + b"\n" for row in source_rows)
    source_path = output_root / "source-task-manifest.jsonl"
    audit_path = output_root / "source-audit.json"
    products[source_path] = source_bytes
    products[audit_path] = _canonical_bytes(
        {
            "audit_id": "issue-62-reviewed-bfws-development-source-v1",
            "efficacy_data": False,
            "expected_pair_count": len(source_rows),
            "expected_source_candidate_count": len(development),
            "expected_task_count": len(source_rows),
            "generation_budget": {
                "adapters": ["astar_hmax", "astar_landmark_count"],
                "decision_outcome_blind": True,
                "frozen_before_astar_execution": True,
                "max_expansions_by_difficulty": dict(sorted(expansion_caps.items())),
                "policy": _BUDGET_POLICY,
                "task_specific_overrides_allowed": False,
            },
            "generation_budget_basis": _BUDGET_BASIS,
            "panel_purpose": "paired_astar_development",
            "replay_proven": True,
            "review_status": "reviewed",
            "schema_version": "astar_paired_source_audit_v1",
            "selection_outcome_blind": True,
            "selection_policy": _SELECTION_POLICY,
            "source_authorization": _binding(
                authorization_path,
                authorization_bytes,
                root,
                "issue-56-bfws-development-authorization-v1",
                "bfws_phase_authorization_v1",
            ),
            "source_evidence": _binding(
                evidence_path,
                evidence_bytes,
                root,
                "issue-57-bfws-expert-traces-v1",
                "bfws_expert_trace_generation_v1",
            ),
        }
    )
    split_counts = Counter(row["split"] for row in source_rows)
    return products, {
        "generation_budget_basis": _BUDGET_BASIS,
        "excluded_candidate_count": sum(exclusion_counts.values()),
        "exclusion_counts": dict(sorted(exclusion_counts.items())),
        "max_expansions_by_difficulty": dict(sorted(expansion_caps.items())),
        "pair_count": len(source_rows),
        "product_count": len(products),
        "source_candidate_count": len(development),
        "split_counts": dict(sorted(split_counts.items())),
    }


def _validate_development_row(row: Mapping[str, Any]) -> None:
    required_text = {
        "difficulty",
        "domain_id",
        "domain_path",
        "instance_id",
        "problem_path",
        "semantic_task_identity",
        "split",
    }
    if (
        any(not isinstance(row.get(field), str) or not row[field] for field in required_text)
        or row.get("algorithm") != "best_first_width"
        or row.get("variant") != "full_bfws_goal_count"
        or row.get("qualification_replay_valid") is not True
        or row.get("qualification_status") != "solved"
        or row.get("difficulty") not in {"easy", "medium", "hard"}
        or row.get("split") not in {"train", "dev"}
        or not _positive_int(row.get("exact_reference_expansion_count"))
    ):
        raise ValueError("BFWS development row is not a replay-proven supported source task")


def _validate_authorization(value: Mapping[str, Any]) -> None:
    if (
        value.get("authorization_id") != "issue-56-bfws-development-authorization-v1"
        or value.get("contract_id") != "issue-56-bfws-development-v1"
        or value.get("outcome") != "PASS"
        or value.get("efficacy_test_access_authorized") is not False
        or value.get("schema_version") != "bfws_phase_authorization_v1"
    ):
        raise ValueError("issue-56 BFWS authorization is not the frozen PASS authority")


def _validated_evidence_traces(value: Mapping[str, Any], expected_count: int) -> list[Mapping[str, Any]]:
    traces = value.get("traces")
    coverage = value.get("coverage")
    receipt = value.get("phase_receipt")
    if (
        value.get("schema_version") != "bfws_expert_trace_generation_v1"
        or value.get("source_issue") != 57
        or not isinstance(traces, list)
        or len(traces) != expected_count
        or not isinstance(coverage, Mapping)
        or coverage.get("instance_count") != expected_count
        or coverage.get("replay_verified_instance_count") != expected_count
        or not isinstance(receipt, Mapping)
        or receipt.get("authorization_id") != "issue-56-bfws-development-authorization-v1"
        or receipt.get("outcome") != "PASS"
        or receipt.get("stage") != "trace_generation"
    ):
        raise ValueError("issue-57 BFWS evidence is not complete replay-proven source evidence")
    if any(not isinstance(trace, Mapping) for trace in traces):
        raise ValueError("issue-57 BFWS trace entries must be objects")
    return traces


def _identity_key(row: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    values = tuple(
        row.get(field)
        for field in ("domain_id", "difficulty", "instance_id", "semantic_task_identity", "split")
    )
    if any(not isinstance(value, str) or not value for value in values):
        raise ValueError("paired source identity fields must be nonempty strings")
    return values  # type: ignore[return-value]


def _repository_path(root: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} path must be nonempty text")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"{label} path must be artifact-root-relative")
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise FileNotFoundError(f"{label} artifact is missing: {path}")
    return path


def _jsonl_objects(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"BFWS development manifest is missing: {path}")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_bytes().splitlines(), start=1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"BFWS development line {line_number} is invalid JSON") from error
        if not isinstance(value, dict):
            raise ValueError(f"BFWS development line {line_number} is not an object")
        rows.append(value)
    if not rows:
        raise ValueError("BFWS development manifest is empty")
    return rows


def _canonical_object(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"{label} is missing: {path}")
    payload = path.read_bytes()
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ValueError(f"{label} is invalid JSON") from error
    canonical = _canonical_bytes(value)
    if not isinstance(value, dict) or payload not in {canonical, canonical + b"\n"}:
        raise ValueError(f"{label} must be canonical JSON with at most one trailing LF")
    return payload, value


def _binding(
    path: Path,
    payload: bytes,
    root: Path,
    identifier: str,
    schema_version: str,
) -> dict[str, object]:
    return {
        "identifier": identifier,
        "path": path.relative_to(root).as_posix(),
        "schema_version": schema_version,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
    }


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


if __name__ == "__main__":
    raise SystemExit(main())
