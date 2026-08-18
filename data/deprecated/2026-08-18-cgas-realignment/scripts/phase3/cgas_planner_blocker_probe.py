from __future__ import annotations

import argparse
import hashlib
import json
import signal
import time
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Callable, Generator, Mapping, Sequence
from typing import Final, TypeVar

from .cgas_bfs import run_fifo_bfs
from .cgas_characterization_bundle import parse_bundle
from .cgas_characterization_rows import CHARACTERIZATION_LIMITS
from .cgas_planner_blocker_probe_fs import ProbeFilesystemError, ProbeOutput, open_probe_output, repository_file, write_new
from .local_iw import run_iterated_width
from .local_planner_types import JSONValue, LocalPlannerRequest
from .pddl import ground_actions, parse_task, replay_plan


REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[2]
BUNDLE_PATH: Final = REPOSITORY_ROOT / "tmp/.cgas-characterization/planning_cgas_v1-characterization-481.cgas"
DRAFT_PATH: Final = REPOSITORY_ROOT / ".claude/evidence/cgas-partition-characterization/planning_cgas_v1-draft.json"
SOURCE_PATH: Final = REPOSITORY_ROOT / "data/curriculum_pddl/accepted_manifest.jsonl"
BFS_IMPLEMENTATION: Final = REPOSITORY_ROOT / "scripts/phase3/cgas_bfs.py"
IW_IMPLEMENTATION: Final = REPOSITORY_ROOT / "scripts/phase3/local_iw.py"
EXPECTED_HASHES: Final = {
    "bundle": "942d7be93ad0eb0ec6580bfe380fb8f09141662140ffc3d3c98e7f09a10ddaf4",
    "characterization": "4596ffdeedf3a212f8e44f9bcb3af6c80b33315d643cba6b9e0d93226b010417",
    "draft": "409f712797f8f02d49fe6d6b5a5b4e7a444f38c54e2cdefcbd4e0e9e7214630d",
}
EXPECTED_FINGERPRINT: Final = "0856e76571643362abb70551ff9d4e02e2d585f7384fc3ac0adb64df240d893a"
REPRESENTATIVES: Final = (
    "blocksworld-dev-hard-0000",
    "blocksworld-test-hard-0014",
    "blocksworld-train-hard-0000",
)
TIME_LIMIT_SECONDS: Final = 60
Result = TypeVar("Result")


class PlannerBlockerProbeError(RuntimeError):
    pass


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write a non-authoritative CGAS planner blocker diagnostic.")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(arguments)
    paths = _prepare_output(args.output)
    try:
        hashes_before, bundle_rows, contract_rows, fingerprint = _load_authoritative_inputs()
        representatives, timings = _probe_representatives(bundle_rows, contract_rows)
        hashes_after, _rows_after, _contract_after, fingerprint_after = _load_authoritative_inputs()
        if hashes_before != hashes_after or fingerprint != fingerprint_after:
            raise PlannerBlockerProbeError("authoritative_hash_changed")
        record = {
            "authoritative_hashes": {"after": hashes_after, "before": hashes_before},
            "bundle": {"run_fingerprint": fingerprint, "sha256": hashes_before["bundle"]},
            "diagnostic_only": True,
            "limits": _serialized_limits(),
            "non_authoritative": True,
            "representatives": representatives,
            "repeat_count": 2,
            "schema_version": "cgas_planner_blocker_probe_v1",
        }
        _write_new(paths.directory_descriptor, "probe.json", _canonical(record))
        _write_new(paths.directory_descriptor, "timings.jsonl", b"".join(_canonical(timing) + b"\n" for timing in timings))
    finally:
        paths.close()
    return 0


def _prepare_output(raw_output: Path) -> ProbeOutput:
    try:
        return open_probe_output(REPOSITORY_ROOT, raw_output)
    except ProbeFilesystemError as error:
        raise PlannerBlockerProbeError("unsafe_output_path" if str(error).startswith("source_") else str(error)) from error


def _load_authoritative_inputs() -> tuple[dict[str, str], dict[str, dict[str, object]], dict[str, dict[str, object]], str]:
    for path in (BUNDLE_PATH, DRAFT_PATH, SOURCE_PATH):
        if not path.is_file() or path.is_symlink():
            raise PlannerBlockerProbeError("authoritative_input_unavailable")
    bundle_contents = BUNDLE_PATH.read_bytes()
    parsed = parse_bundle(bundle_contents)
    members = {member.name: member.contents for member in parsed.members}
    hashes = {
        "bundle": _sha256(bundle_contents),
        "characterization": _sha256(members["characterization.jsonl"]),
        "draft": _sha256(DRAFT_PATH.read_bytes()),
    }
    if hashes != EXPECTED_HASHES or parsed.run_fingerprint != EXPECTED_FINGERPRINT:
        raise PlannerBlockerProbeError("authoritative_hash_mismatch")
    rows = _rows(members["characterization.jsonl"])
    contract = json.loads(members["run-contract.json"])
    if not isinstance(contract, dict) or not isinstance(contract.get("source"), dict):
        raise PlannerBlockerProbeError("invalid_run_contract")
    source_rows = contract["source"].get("records")
    if not isinstance(source_rows, dict):
        raise PlannerBlockerProbeError("invalid_run_contract")
    return hashes, rows, {str(key): value for key, value in source_rows.items() if isinstance(value, dict)}, parsed.run_fingerprint


def _probe_representatives(bundle_rows: dict[str, dict[str, object]], contract_rows: dict[str, dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, int | str]]]:
    records: list[dict[str, object]] = []
    timings: list[dict[str, int | str]] = []
    for instance_id in REPRESENTATIVES:
        row = bundle_rows.get(instance_id)
        contract_row = contract_rows.get(instance_id)
        if row is None or contract_row is None:
            raise PlannerBlockerProbeError("missing_representative")
        _bind_source(row, contract_row)
        first, first_timings = _run_once(instance_id, contract_row, 1)
        second, second_timings = _run_once(instance_id, contract_row, 2)
        if first != second:
            raise PlannerBlockerProbeError("nondeterministic_planner_result")
        records.append({**first, "runs_match": True})
        timings.extend((*first_timings, *second_timings))
    return records, timings


def _bind_source(row: dict[str, object], contract_row: dict[str, object]) -> None:
    identity = row.get("source_identity")
    if not isinstance(identity, dict) or identity.get("source_record_sha256") != contract_row.get("source_record_sha256"):
        raise PlannerBlockerProbeError("source_identity_mismatch")
    if row.get("domain_sha256") != contract_row.get("domain_sha256") or row.get("problem_sha256") != contract_row.get("problem_sha256"):
        raise PlannerBlockerProbeError("source_input_mismatch")
    if contract_row.get("object_count") != 12:
        raise PlannerBlockerProbeError("representative_object_count_mismatch")


def _run_once(instance_id: str, contract_row: dict[str, object], repeat_index: int) -> tuple[dict[str, object], list[dict[str, int | str]]]:
    domain = _repository_file(contract_row.get("domain_path"))
    problem = _repository_file(contract_row.get("problem_path"))
    sas_plan = problem.parent / "plan" / "sas_plan"
    if not sas_plan.is_file() or sas_plan.is_symlink():
        raise PlannerBlockerProbeError("sas_plan_unavailable")
    task = parse_task(domain, problem)
    grounded, grounding_status = ground_actions(task, max_grounded_actions=CHARACTERIZATION_LIMITS["max_grounded_actions"], max_grounded_atoms=CHARACTERIZATION_LIMITS["max_grounded_atoms"])
    if grounding_status is not None:
        raise PlannerBlockerProbeError("unexpected_grounding_status")
    persisted = tuple(line.strip() for line in sas_plan.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith(";"))
    persisted_replay = replay_plan(task, list(persisted), grounded_actions=grounded)
    if persisted_replay["replay_ok"] is not True or persisted_replay["goal_satisfied"] is not True:
        raise PlannerBlockerProbeError("sas_plan_replay_failed")
    bfs, bfs_timing = _timed(instance_id, "bfs", repeat_index, lambda: run_fifo_bfs(task, tuple(grounded), CHARACTERIZATION_LIMITS))
    iw, iw_timing = _timed(instance_id, "iw_width_1", repeat_index, lambda: run_iterated_width(LocalPlannerRequest("iw", task, tuple(grounded), CHARACTERIZATION_LIMITS)))
    bfs_replay = replay_plan(task, list(bfs.plan), grounded_actions=grounded)
    iw_replay = replay_plan(task, iw.plan, grounded_actions=grounded)
    return ({
        "bfs": {**_planner_summary(bfs.plan, bfs.status, bfs.trace), "implementation_sha256": _sha256(BFS_IMPLEMENTATION.read_bytes()), "replay": _replay_summary(bfs_replay)},
        "domain_sha256": _sha256(domain.read_bytes()),
        "instance_id": instance_id,
        "iw_width_1": {**_planner_summary(iw.plan, iw.status, iw.trace), "implementation_sha256": _sha256(IW_IMPLEMENTATION.read_bytes()), "recovery_absent": "plan_recovery" not in iw.trace, "replay": _replay_summary(iw_replay)},
        "problem_sha256": _sha256(problem.read_bytes()),
        "sas_plan": {"action_count": len(persisted), "replay": _replay_summary(persisted_replay), "sha256": _sha256(sas_plan.read_bytes())},
        "source_record_sha256": contract_row["source_record_sha256"],
    }, [bfs_timing, iw_timing])


def _timed(instance_id: str, planner: str, repeat_index: int, operation: Callable[[], Result]) -> tuple[Result, dict[str, int | str]]:
    wall_start = time.perf_counter_ns()
    cpu_start = time.process_time_ns()
    with _time_limit():
        result = operation()
    return result, {"cpu_nanoseconds": time.process_time_ns() - cpu_start, "instance_id": instance_id, "planner": planner, "repeat_index": repeat_index, "wall_nanoseconds": time.perf_counter_ns() - wall_start}


@contextmanager
def _time_limit() -> Generator[None, None, None]:
    def expired(_signal_number: int, _frame) -> None:
        raise PlannerBlockerProbeError("planner_timeout")

    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    if previous_timer != (0.0, 0.0):
        raise PlannerBlockerProbeError("existing_sigalrm_timer")
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, TIME_LIMIT_SECONDS)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def _planner_summary(plan: Sequence[str], status: str, trace: Mapping[str, JSONValue]) -> dict[str, object]:
    return {"expansion_count": trace.get("expansion_count"), "plan_length": len(plan), "status": status, "trace_complete": trace.get("trace_complete"), "trace_sha256": _sha256(_canonical(trace))}


def _replay_summary(replay: dict[str, object]) -> dict[str, object]:
    return {"goal_satisfied": replay["goal_satisfied"], "replay_ok": replay["replay_ok"], "status": replay["status"], "transition_count": replay["transition_count"]}


def _rows(contents: bytes) -> dict[str, dict[str, object]]:
    rows = [json.loads(line) for line in contents.splitlines()]
    if not all(isinstance(row, dict) and isinstance(row.get("instance_id"), str) for row in rows):
        raise PlannerBlockerProbeError("invalid_characterization_rows")
    return {str(row["instance_id"]): row for row in rows}


def _repository_file(value: object) -> Path:
    if not isinstance(value, str):
        raise PlannerBlockerProbeError("invalid_run_contract")
    try:
        return repository_file(REPOSITORY_ROOT, value)
    except ProbeFilesystemError as error:
        raise PlannerBlockerProbeError(str(error)) from error


def _serialized_limits() -> dict[str, int]:
    return {key: int(value) for key, value in sorted(CHARACTERIZATION_LIMITS.items())}


def _canonical(value: object) -> bytes:
    return json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _sha256(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


def _write_new(directory_descriptor: int, name: str, contents: bytes) -> None:
    write_new(directory_descriptor, name, contents)


if __name__ == "__main__":
    raise SystemExit(main())
