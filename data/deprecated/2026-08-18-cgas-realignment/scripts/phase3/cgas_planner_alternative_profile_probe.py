from __future__ import annotations

import argparse
import signal
import time
from collections.abc import Callable, Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final, TypeVar

from .cgas_bfs import BFSResult, run_fifo_bfs
from .cgas_characterization_rows import CHARACTERIZATION_LIMITS
from .cgas_planner_blocker_probe import (
    BFS_IMPLEMENTATION,
    IW_IMPLEMENTATION,
    REPRESENTATIVES,
    PlannerBlockerProbeError,
    _bind_source,
    _canonical,
    _load_authoritative_inputs,
    _planner_summary,
    _replay_summary,
    _repository_file,
    _sha256,
)
from .cgas_planner_blocker_probe_fs import ProbeFilesystemError, ProbeOutput, open_probe_output, write_new
from .local_iw import run_iterated_width
from .local_planner_types import LocalPlannerRequest, LocalPlannerResult, RecoveryPolicy
from .pddl import GroundAction, PDDLTask, ground_actions, parse_task, replay_plan


REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[2]
TIME_LIMIT_SECONDS: Final = 120
Result = TypeVar("Result")


@dataclass(frozen=True, slots=True)
class Profile:
    profile_id: str
    algorithm: str
    limits: dict[str, int | RecoveryPolicy]


PROFILES: Final = (
    Profile("bfs_30000", "bfs", {"max_expansions": 30_000, "max_trace_steps": 0}),
    Profile("bfs_100000", "bfs", {"max_expansions": 100_000, "max_trace_steps": 0}),
    Profile("iw_2", "iw", {"local_iw_width": 2, "local_iw_max_width": 2, "local_iw_novelty_max_expansions": 10_000, "local_iw_recovery": RecoveryPolicy.DISABLED, "max_trace_steps": 0}),
    Profile("iw_3", "iw", {"local_iw_width": 3, "local_iw_max_width": 3, "local_iw_novelty_max_expansions": 10_000, "local_iw_recovery": RecoveryPolicy.DISABLED, "max_trace_steps": 0}),
)


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write non-authoritative alternative CGAS planner profile evidence.")
    parser.add_argument("--output", required=True, type=Path)
    parsed_arguments = parser.parse_args(arguments)
    output = _prepare_output(parsed_arguments.output)
    try:
        hashes_before, bundle_rows, contract_rows, fingerprint = _load_authoritative_inputs()
        profiles, timings = _probe_profiles(bundle_rows, contract_rows)
        hashes_after, _rows_after, _contract_after, fingerprint_after = _load_authoritative_inputs()
        if hashes_before != hashes_after or fingerprint != fingerprint_after:
            raise PlannerBlockerProbeError("authoritative_hash_changed")
        record = {
            "authoritative_hashes": {"after": hashes_after, "before": hashes_before},
            "bundle": {"run_fingerprint": fingerprint, "sha256": hashes_before["bundle"]},
            "diagnostic_only": True,
            "non_authoritative": True,
            "profile_changed": True,
            "profiles": profiles,
            "probe_implementation_sha256": _sha256(Path(__file__).read_bytes()),
            "repeat_count": 2,
            "schema_version": "cgas_planner_alternative_profile_probe_v1",
        }
        write_new(output.directory_descriptor, "probe.json", _canonical(record))
        write_new(output.directory_descriptor, "timings.jsonl", b"".join(_canonical(timing) + b"\n" for timing in timings))
    finally:
        output.close()
    return 0


def _prepare_output(raw_output: Path) -> ProbeOutput:
    try:
        return open_probe_output(REPOSITORY_ROOT, raw_output, "alternative")
    except ProbeFilesystemError as error:
        raise PlannerBlockerProbeError("unsafe_output_path" if str(error).startswith("source_") else str(error)) from error


def _probe_profiles(bundle_rows: dict[str, dict[str, object]], contract_rows: dict[str, dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, int | str]]]:
    profiles: list[dict[str, object]] = []
    timings: list[dict[str, int | str]] = []
    for profile in PROFILES:
        instances, profile_timings = _probe_profile(profile, bundle_rows, contract_rows)
        profiles.append({"instances": instances, "limits": _serialized_limits({**CHARACTERIZATION_LIMITS, **profile.limits}), "profile_id": profile.profile_id})
        timings.extend(profile_timings)
    return profiles, timings


def _probe_profile(profile: Profile, bundle_rows: dict[str, dict[str, object]], contract_rows: dict[str, dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, int | str]]]:
    instances: list[dict[str, object]] = []
    timings: list[dict[str, int | str]] = []
    for instance_id in REPRESENTATIVES:
        row = bundle_rows.get(instance_id)
        contract_row = contract_rows.get(instance_id)
        if row is None or contract_row is None:
            raise PlannerBlockerProbeError("missing_representative")
        _bind_source(row, contract_row)
        first, first_timing = _run_once(profile, instance_id, contract_row, 1)
        second, second_timing = _run_once(profile, instance_id, contract_row, 2)
        if first != second:
            raise PlannerBlockerProbeError("nondeterministic_planner_result")
        instances.append({**first, "runs_match": True})
        timings.extend((first_timing, second_timing))
    return instances, timings


def _run_once(profile: Profile, instance_id: str, contract_row: dict[str, object], repeat_index: int) -> tuple[dict[str, object], dict[str, int | str]]:
    domain = _repository_file(contract_row.get("domain_path"))
    problem = _repository_file(contract_row.get("problem_path"))
    task = parse_task(domain, problem)
    grounded, grounding_status = ground_actions(task, max_grounded_actions=CHARACTERIZATION_LIMITS["max_grounded_actions"], max_grounded_atoms=CHARACTERIZATION_LIMITS["max_grounded_atoms"])
    if grounding_status is not None:
        raise PlannerBlockerProbeError("unexpected_grounding_status")
    result, timing = _run_profile(profile, task, tuple(grounded), instance_id, repeat_index)
    replay = replay_plan(task, list(result.plan), grounded_actions=grounded)
    return {
        "domain_sha256": _sha256(domain.read_bytes()),
        "instance_id": instance_id,
        "planner": {**_planner_summary(result.plan, result.status, result.trace), "implementation_sha256": _implementation_hash(profile), "recovery_absent": "plan_recovery" not in result.trace, "replay": _replay_summary(replay)},
        "problem_sha256": _sha256(problem.read_bytes()),
        "source_record_sha256": contract_row["source_record_sha256"],
    }, timing


def _run_profile(profile: Profile, task: PDDLTask, grounded: tuple[GroundAction, ...], instance_id: str, repeat_index: int) -> tuple[BFSResult | LocalPlannerResult, dict[str, int | str]]:
    limits = {**CHARACTERIZATION_LIMITS, **profile.limits}
    match profile.algorithm:
        case "bfs":
            return _timed(instance_id, profile.profile_id, repeat_index, lambda: run_fifo_bfs(task, grounded, limits))
        case "iw":
            request = LocalPlannerRequest("iw", task, grounded, limits)
            return _timed(instance_id, profile.profile_id, repeat_index, lambda: run_iterated_width(request))
        case other:
            raise PlannerBlockerProbeError(f"unknown_profile_algorithm:{other}")


def _timed(instance_id: str, profile_id: str, repeat_index: int, operation: Callable[[], Result]) -> tuple[Result, dict[str, int | str]]:
    wall_start = time.perf_counter_ns()
    cpu_start = time.process_time_ns()
    with _time_limit():
        result = operation()
    return result, {"cpu_nanoseconds": time.process_time_ns() - cpu_start, "instance_id": instance_id, "profile_id": profile_id, "repeat_index": repeat_index, "wall_nanoseconds": time.perf_counter_ns() - wall_start}


@contextmanager
def _time_limit() -> Generator[None, None, None]:
    def expired(_signal_number: int, _frame: object) -> None:
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


def _implementation_hash(profile: Profile) -> str:
    match profile.algorithm:
        case "bfs":
            return _sha256(BFS_IMPLEMENTATION.read_bytes())
        case "iw":
            return _sha256(IW_IMPLEMENTATION.read_bytes())
        case other:
            raise PlannerBlockerProbeError(f"unknown_profile_algorithm:{other}")


def _serialized_limits(limits: dict[str, int | RecoveryPolicy]) -> dict[str, int | str]:
    return {key: value.value if isinstance(value, RecoveryPolicy) else value for key, value in sorted(limits.items())}


if __name__ == "__main__":
    raise SystemExit(main())
