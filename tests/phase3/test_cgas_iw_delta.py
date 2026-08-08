from __future__ import annotations

import json
from copy import deepcopy
from itertools import combinations
from pathlib import Path

from scripts.phase3.cgas_certificate_contracts import expected_certificate
from scripts.phase3.cgas_trace_contract_v3 import (
    CONTRACT_ID,
    IW_EVENT_FIELDS_ADDED,
    IW_EVENT_FIELDS_REMOVED,
)
from scripts.phase3.local_iw import run_iterated_width
from scripts.phase3.local_planner_types import JSONValue, LocalPlannerRequest
from scripts.phase3.pddl import PDDLTask


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPOSITORY_ROOT / "data/planning_cgas_fixture_v1"


def test_rebuilds_released_iw_certificates_from_v2_and_v3_event_shapes() -> None:
    # Given: every released IW row and an in-memory copy migrated to the signed v3 shape.
    source_rows = _rows(FIXTURE_ROOT / "source")
    released_steps = {row["source_transition_id"]: row for row in _rows(FIXTURE_ROOT / "steps")}
    v2_rows = [row for row in source_rows if _mapping(row, "planner")["algorithm"] == "iterated_width"]
    v3_rows = deepcopy(v2_rows)
    for row in v3_rows:
        trace = _mapping(row, "planner_trace")
        trace["trace_contract_version"] = CONTRACT_ID
        for event in _mappings(trace, "events"):
            before = set(_strings(event, IW_EVENT_FIELDS_REMOVED[1]))
            after = set(_strings(event, IW_EVENT_FIELDS_REMOVED[0]))
            event[IW_EVENT_FIELDS_ADDED[0]] = sorted(after - before)
            for field in IW_EVENT_FIELDS_REMOVED:
                event.pop(field)

    # When: certificates are projected from both persistence shapes.
    rebuilt = [
        (expected_certificate(v2_row), expected_certificate(v3_row))
        for v2_row, v3_row in zip(v2_rows, v3_rows, strict=True)
    ]

    # Then: both paths reproduce the immutable released certificates exactly.
    expected = [_mapping(released_steps[row["record_id"]], "certificate") for row in v2_rows]
    assert rebuilt == [(certificate, certificate) for certificate in expected]


def test_native_iw_uses_the_signed_v3_contract_id_as_its_trace_version() -> None:
    # Given: a width-one search with one expandable initial state.
    task = PDDLTask("fixture", "version", {}, frozenset({("start",)}), frozenset({("missing",)}), (), ())

    # When: the native IW emitter produces a trace.
    result = run_iterated_width(_request(task, width=1))

    # Then: the embedded discriminator is the exact owner-approved contract id.
    assert result.trace["trace_contract_version"] == CONTRACT_ID == "cgas_trace_contract_v3"


def test_width_two_expand_delta_is_exact_beyond_the_old_snapshot_clip() -> None:
    # Given: 21 root atoms whose width-two novelty set contains 231 features.
    atoms = tuple(f"feature-{index:02d}" for index in range(21))
    task = PDDLTask(
        "fixture",
        "wide-delta",
        {},
        frozenset((atom,) for atom in atoms),
        frozenset({("missing",)}),
        (),
        (),
    )
    canonical_atoms = tuple(f"({atom})" for atom in atoms)
    expected = sorted([*canonical_atoms, *(" | ".join(pair) for pair in combinations(canonical_atoms, 2))])
    assert len(expected) == 231

    # When: the root expands at width two.
    result = run_iterated_width(_request(task, width=2))
    event = _mappings(result.trace, "events")[0]

    # Then: the emitted delta contains every new feature without the former 200-item clip.
    assert _strings(event, IW_EVENT_FIELDS_ADDED[0]) == expected


def _request(task: PDDLTask, *, width: int) -> LocalPlannerRequest:
    return LocalPlannerRequest(
        "iw",
        task,
        (),
        {
            "gbfs_max_expansions": 10,
            "local_iw_max_width": width,
            "local_iw_novelty_max_expansions": 10,
            "local_iw_recovery": 0,
            "local_iw_width": width,
            "local_max_applicable_actions": 10,
            "max_plan_length": 10,
            "max_trace_steps": 10,
        },
    )


def _rows(root: Path) -> list[dict[str, JSONValue]]:
    return [
        json.loads(line)
        for split in ("train", "dev", "test")
        for line in (root / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()
    ]


def _mapping(value: dict[str, JSONValue], field: str) -> dict[str, JSONValue]:
    item = value[field]
    assert isinstance(item, dict)
    return item


def _mappings(value: dict[str, JSONValue], field: str) -> list[dict[str, JSONValue]]:
    items = value[field]
    assert isinstance(items, list)
    assert all(isinstance(item, dict) for item in items)
    return [item for item in items if isinstance(item, dict)]


def _strings(value: dict[str, JSONValue], field: str) -> list[str]:
    items = value[field]
    assert isinstance(items, list)
    assert all(isinstance(item, str) for item in items)
    return [item for item in items if isinstance(item, str)]
