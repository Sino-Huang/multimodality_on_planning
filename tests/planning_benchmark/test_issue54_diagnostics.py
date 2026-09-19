from __future__ import annotations

from scripts.diagnose_bfs_issue54 import analyze_episode_payload, classify_rejection


def test_classifies_retained_failure_modes() -> None:
    assert classify_rejection("Unterminated string starting at: line 1 column 200", '{"typed_operation":"') == (
        "truncated_json"
    )
    assert classify_rejection("BFS successors must be appended at the frontier tail", "{}") == "frontier_tail"
    assert classify_rejection("BFS successor target was already visited", "{}") == "already_visited"
    assert classify_rejection("action is not applicable in state x", "{}") == "inapplicable_action"


def test_episode_summary_counts_deterministic_rejection_replays() -> None:
    repeated = {
        "budget_charge": 1,
        "input": {"search_memory": {"context_type": "rolling_search_context"}},
        "raw_output": "not-json",
        "runtime_result": {"reason": "Expecting value: line 1 column 1", "status": "rejected"},
        "status": "rejected",
        "trace_record_index": None,
    }
    payload = {
        "result": {"goal_reached": False},
        "evidence": {"policy_events": [repeated, repeated]},
    }

    summary = analyze_episode_payload(payload)

    assert summary["decision_count"] == 2
    assert summary["rejected_count"] == 2
    assert summary["deterministic_replay_count"] == 1
    assert summary["failure_categories"] == {"invalid_json": 2}
    assert summary["input_contracts"] == {"rolling_search_context": 2}
