from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from scripts.phase3.cgas_certificate_contracts import expected_certificate

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPOSITORY_ROOT / "data/planning_cgas_v1"
SNAPSHOT_FIELDS = ("frontier_before", "frontier_after", "visited_after")


def test_reconstructs_fixture_release_certificates_without_bfs_snapshots() -> None:
    # Given: every released v2 BFS row converted in memory to the v3 event shape.
    source_rows = _rows(FIXTURE_ROOT / "source")
    released_steps = {
        row["source_transition_id"]: row
        for row in _rows(FIXTURE_ROOT / "steps")
    }
    bfs_rows = [row for row in source_rows if _mapping(row, "planner")["algorithm"] == "breadth_first_search"]
    v3_rows = deepcopy(bfs_rows)
    for row in v3_rows:
        for expansion in _mappings(_mapping(row, "planner_trace"), "expansions"):
            for field in SNAPSHOT_FIELDS:
                expansion.pop(field)

    # When: the reader rebuilds certificates using only retained v3 fields.
    rebuilt = [
        (expected_certificate(v2_row), expected_certificate(v3_row))
        for v2_row, v3_row in zip(bfs_rows, v3_rows, strict=True)
    ]

    # Then: all rebuilt certificates match the immutable fixture release.
    expected = [_mapping(released_steps[row["record_id"]], "certificate") for row in bfs_rows]
    assert rebuilt == [(certificate, certificate) for certificate in expected]


def test_reconstructs_index_zero_bfs_certificate() -> None:
    # Given: a v3 root expansion that enqueues two successors.
    source = _bfs_source("state-root", _fifo_expansions())

    # When: the reader projects the root certificate.
    certificate = expected_certificate(source)

    # Then: the initial root is included only in the first visited delta.
    assert certificate == {
        "kind": "bfs",
        "frontier_head": "state-root",
        "frontier_order_summary": ["state-parent", "state-sibling"],
        "visited_delta": ["state-parent", "state-root", "state-sibling"],
        "expanded_state": "state-root",
    }


def test_reconstructs_fifo_after_goal_found_mid_expansion() -> None:
    # Given: the next expansion records its goal successor and returns before later actions.
    source = _bfs_source("state-parent", _fifo_expansions())

    # When: the reader projects that early-return expansion.
    certificate = expected_certificate(source)

    # Then: the fold retains the sibling and appends only the recorded goal state.
    assert certificate == {
        "kind": "bfs",
        "frontier_head": "state-parent",
        "frontier_order_summary": ["state-sibling", "state-goal"],
        "visited_delta": ["state-goal"],
        "expanded_state": "state-parent",
    }


def _fifo_expansions() -> list[dict[str, object]]:
    return [
        {
            "state_id": "state-root",
            "successors": [
                {"enqueued": True, "state_id": "state-parent"},
                {"enqueued": True, "state_id": "state-sibling"},
            ],
        },
        {
            "state_id": "state-parent",
            "successors": [{"enqueued": True, "state_id": "state-goal"}],
        },
    ]


def _bfs_source(state_before_id: str, expansions: list[dict[str, object]]) -> dict[str, object]:
    return {
        "record_id": f"record-{state_before_id}",
        "state_before_id": state_before_id,
        "planner": {"algorithm": "breadth_first_search"},
        "planner_trace": {"expansions": expansions},
    }


def _rows(root: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for split in ("train", "dev", "test")
        for line in (root / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()
    ]


def _mapping(value: dict[str, object], field: str) -> dict[str, object]:
    item = value[field]
    assert isinstance(item, dict)
    return item


def _mappings(value: dict[str, object], field: str) -> list[dict[str, object]]:
    items = value[field]
    assert isinstance(items, list)
    assert all(isinstance(item, dict) for item in items)
    return [item for item in items if isinstance(item, dict)]
