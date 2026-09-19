from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from examples.planning_benchmark_slice.benchmark_loop import (
    BenchmarkLoopError,
    load_validated_loop,
    shortest_action_plan,
)
from examples.planning_benchmark_slice.search_trace import (
    TraceSegmentLimits,
    replay_search_trace_segment,
    verify_search_trace_segment,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "planning"
NONTRIVIAL_FIXTURE = FIXTURE_DIR / "blocksworld_nontrivial.json"
INVALID_ACTIONS = FIXTURE_DIR / "actions_invalid.json"


def _run_loop(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "examples.planning_benchmark_slice.benchmark_loop", *args],
        cwd=REPO_ROOT,
        check=False,
        text=True,
        capture_output=True,
    )


def test_oracle_bfs_plan_solves_nontrivial_fixture() -> None:
    loop = load_validated_loop(NONTRIVIAL_FIXTURE, max_steps=20)
    plan = shortest_action_plan(loop.problem, loop.problem.initial_state(), max_depth=20)

    assert [action.serialize() for action in plan or ()] == ["pickup(a)", "stack(a,b)"]

    payload = loop.run_oracle()
    assert payload["valid"] is True
    assert payload["mode"] == "oracle"
    assert payload["solved"] is True
    assert payload["steps"] == 2
    assert payload["selected_actions"] == ["pickup(a)", "stack(a,b)"]
    assert payload["illegal_action_count"] == 0
    assert payload["terminal_status"]["reason"] == "goal"


def test_oracle_persists_verifiable_replayable_search_trace_segment() -> None:
    loop = load_validated_loop(NONTRIVIAL_FIXTURE, max_steps=20, max_trace_bytes=20_000)

    payload = loop.run_oracle()
    segment = payload["search_trace_segment"]
    records = segment["records"]

    assert segment["record_count"] == payload["steps"] == 2
    for index, record in enumerate(records):
        for field in ("observation", "rationale", "operation", "result"):
            assert record[field]
        assert record["index"] == index

    serialized_segment = json.dumps(
        segment,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    limits = TraceSegmentLimits(max_records=20, max_bytes=20_000)
    assert verify_search_trace_segment(serialized_segment, limits=limits) is True

    replayed = replay_search_trace_segment(
        serialized_segment,
        authority=loop.problem.authority,
        limits=limits,
    )
    assert replayed.to_bytes() == loop.search_memory.to_bytes()


def test_step_log_contains_observation_state_ids_legality_and_terminal_status() -> None:
    loop = load_validated_loop(NONTRIVIAL_FIXTURE, max_steps=20)
    payload = loop.run_oracle()
    first_step = payload["step_logs"][0]

    assert first_step["action"] == "pickup(a)"
    assert first_step["pre_state_id"] == first_step["observation"]["state_id"]
    assert first_step["post_state_id"] != first_step["pre_state_id"]
    assert first_step["legal_action_check"] == {
        "action": "pickup(a)",
        "is_legal": True,
        "legal_actions": ["pickup(a)", "pickup(b)", "pickup(c)"],
    }
    assert first_step["terminal_status"]["is_terminal"] is False
    assert first_step["observation"]["schema_version"] == "planning_benchmark_observation_v1"
    assert first_step["observation"]["state_atoms"] == [
        "arm-empty",
        "clear(a)",
        "clear(b)",
        "clear(c)",
        "on-table(a)",
        "on-table(b)",
        "on-table(c)",
    ]
    assert first_step["observation"]["legal_actions"] == ["pickup(a)", "pickup(b)", "pickup(c)"]


def test_loop_retains_replayable_authority_transitions_and_logs_provenance() -> None:
    loop = load_validated_loop(NONTRIVIAL_FIXTURE, max_steps=20)
    payload = loop.run_oracle()

    assert len(loop.transition_records) == 2
    replayed = loop.problem.authority.replay(tuple(loop.transition_records))
    assert replayed[-1].atoms == tuple(sorted(loop.state))

    first_transition = loop.transition_records[0]
    assert payload["step_logs"][0]["transition_provenance"] == {
        "action": {"args": ["a"], "name": "pickup"},
        "authority_id": loop.problem.authority.authority_id,
        "provenance_id": first_transition.provenance.provenance_id,
        "source_state_id": first_transition.source_state.state_id,
        "target_state_id": first_transition.target_state.state_id,
    }
    json.dumps(payload)


def test_invalid_action_raises_structured_error_without_mutating_state() -> None:
    loop = load_validated_loop(NONTRIVIAL_FIXTURE, max_steps=20)

    with pytest.raises(BenchmarkLoopError) as error:
        loop.step("stack(a,b)")

    assert error.value.code == "illegal_action"
    assert error.value.details["pre_state_id"] == loop.problem.state_id(loop.problem.initial_state())
    assert error.value.details["legal_actions"] == ["pickup(a)", "pickup(b)", "pickup(c)"]
    assert loop.step_logs == []


def test_oracle_max_steps_stops_without_solving_when_limit_is_short() -> None:
    loop = load_validated_loop(NONTRIVIAL_FIXTURE, max_steps=1)

    payload = loop.run_oracle()

    assert payload["valid"] is True
    assert payload["solved"] is False
    assert payload["steps"] == 1
    assert payload["terminal_status"] == {
        "is_terminal": True,
        "reason": "max_steps",
        "solved": False,
        "max_steps_reached": True,
        "step_index": 1,
    }


def test_oracle_cli_solves_fixture_and_emits_json_only_on_success() -> None:
    result = _run_loop(
        "run-oracle",
        "--fixture",
        str(NONTRIVIAL_FIXTURE),
        "--max-steps",
        "20",
        "--json",
    )

    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert result.stderr == ""
    assert payload["solved"] is True
    assert payload["steps"] == 2
    assert payload["step_logs"][1]["terminal_status"]["reason"] == "goal"


def test_invalid_scripted_action_cli_returns_json_error_without_traceback() -> None:
    result = _run_loop(
        "run-scripted",
        "--fixture",
        str(NONTRIVIAL_FIXTURE),
        "--actions",
        str(INVALID_ACTIONS),
        "--json",
    )

    payload = json.loads(result.stdout)
    combined_output = result.stdout + result.stderr
    assert result.returncode != 0
    assert payload["valid"] is False
    assert payload["error"]["code"] == "illegal_action"
    assert payload["error"]["details"]["legal_actions"] == ["pickup(a)", "pickup(b)", "pickup(c)"]
    assert "illegal_action" in result.stderr
    assert "Traceback" not in combined_output


def test_invalid_scripted_action_cli_persists_rejected_search_trace_segment() -> None:
    result = _run_loop(
        "run-scripted",
        "--fixture",
        str(NONTRIVIAL_FIXTURE),
        "--actions",
        str(INVALID_ACTIONS),
        "--max-steps",
        "20",
        "--max-trace-bytes",
        "20000",
        "--json",
    )

    payload = json.loads(result.stdout)
    combined_output = result.stdout + result.stderr
    assert result.returncode != 0
    assert payload["valid"] is False
    assert payload["error"]["code"] == "illegal_action"
    assert "illegal_action" in result.stderr
    assert "Traceback" not in combined_output

    segment = payload["error"]["details"]["search_trace_segment"]
    assert segment["record_count"] == len(segment["records"]) == 1
    assert segment["records"][0]["result"]["status"] == "rejected"
    assert segment["records"][0]["result"]["budget_charge"] == 1

    serialized_segment = json.dumps(
        segment,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    limits = TraceSegmentLimits(max_records=20, max_bytes=20_000)
    assert verify_search_trace_segment(serialized_segment, limits=limits) is True

    fresh_loop = load_validated_loop(NONTRIVIAL_FIXTURE, max_steps=20, max_trace_bytes=20_000)
    replayed = replay_search_trace_segment(
        serialized_segment,
        authority=fresh_loop.problem.authority,
        limits=limits,
    )
    assert replayed.to_bytes() == fresh_loop.search_memory.to_bytes()
