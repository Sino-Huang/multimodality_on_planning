from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_state_hash_is_canonical_and_rejects_duplicate_atoms() -> None:
    from scripts.phase3.cgas_pilot_expansion_index import PilotExpansionIndexError, state_sha256

    atoms = ["(on b1 b0)", "(clear b1)"]

    assert state_sha256(atoms) == state_sha256(sorted(atoms))
    with pytest.raises(PilotExpansionIndexError, match="pilot_expansion_state_atoms_noncanonical"):
        state_sha256(["(clear b1)", "(clear b1)"])


def test_bfs_projection_reconstructs_exact_certificate_without_action_target() -> None:
    from scripts.phase3.cgas_pilot_expansion_index import BfsCertificateFold, project_expansion

    first = {
        "actions_considered": ["(pickup b1)", "(pickup b2)"],
        "state_atoms": ["(arm-empty)", "(clear b1)", "(clear b2)"],
        "state_id": "root",
        "successors": [
            {"action": "(pickup b1)", "enqueued": True, "is_goal": False, "state_id": "left"},
            {"action": "(pickup b2)", "enqueued": True, "is_goal": False, "state_id": "right"},
        ],
    }
    second = {
        "actions_considered": ["(putdown b1)"],
        "state_atoms": ["(holding b1)"],
        "state_id": "left",
        "successors": [
            {"action": "(putdown b1)", "enqueued": False, "is_goal": False, "state_id": "root"}
        ],
    }
    fold = BfsCertificateFold()

    first_row = project_expansion("bfs", first, fold)
    second_row = project_expansion("bfs", second, fold)

    assert first_row is not None
    assert second_row is not None
    assert first_row["certificate"] == {
        "kind": "bfs",
        "frontier_head": "root",
        "frontier_order_summary": ["left", "right"],
        "visited_delta": ["left", "right", "root"],
        "expanded_state": "root",
    }
    assert second_row["certificate"] == {
        "kind": "bfs",
        "frontier_head": "left",
        "frontier_order_summary": ["right"],
        "visited_delta": [],
        "expanded_state": "left",
    }
    assert first_row["successors"] == first["successors"]
    assert "action_target" not in first_row
    assert "selected_action" not in first_row


def test_iw_projection_keeps_exact_delta_and_skips_prunes() -> None:
    from scripts.phase3.cgas_pilot_expansion_index import project_expansion

    expansion = {
        "decision": "expand",
        "event_kind": "expansion",
        "novel_item": "(clear b1)",
        "seen_feature_delta": ["(clear b1)", "(holding b2)"],
        "state_atoms": ["(clear b1)"],
        "successors": [{"action": "(pickup b1)", "enqueued": True, "is_goal": False}],
        "width_decision": "width_2_novel",
    }
    prune = {
        "decision": "prune",
        "event_kind": "backtrack",
        "novel_item": "",
        "seen_feature_delta": [],
        "state_atoms": ["(clear b1)"],
        "width_decision": "width_2_seen",
    }

    assert project_expansion("iw", prune, None) is None
    row = project_expansion("iw", expansion, None)
    assert row is not None
    assert row["certificate"] == {
        "kind": "iw",
        "novelty_tuple": "(clear b1)",
        "seen_feature_delta": ["(clear b1)", "(holding b2)"],
        "width_decision": "width_2_novel",
    }
    assert row["successors"] == expansion["successors"]


def test_verified_event_reader_rejects_v2_contract(tmp_path: Path) -> None:
    from scripts.phase3.cgas_pilot_expansion_index import PilotExpansionIndexError, iter_verified_events
    from scripts.phase3.cgas_trace_stream_v2 import TraceWriteRequest, write_trace_stream

    trace = tmp_path / "bfs.trace-v2.jsonl"
    write_trace_stream(
        TraceWriteRequest(trace, "bfs", "failed_no_plan_extracted", (), 0),
        (),
    )

    with pytest.raises(PilotExpansionIndexError, match="pilot_expansion_contract_unsupported"):
        tuple(iter_verified_events(trace))


def test_verified_event_reader_refuses_a_tampered_hash_chain(tmp_path: Path) -> None:
    from scripts.phase3 import cgas_trace_contract_v3
    from scripts.phase3.cgas_pilot_expansion_index import PilotExpansionIndexError, iter_verified_events
    from scripts.phase3.cgas_trace_stream_v2 import TraceWriteRequest, write_trace_stream

    trace = tmp_path / "bfs.trace-v3.jsonl"
    event = {
        "actions_considered": [],
        "state_atoms": ["(arm-empty)"],
        "state_id": "root",
        "successors": [],
    }
    write_trace_stream(
        TraceWriteRequest(
            trace,
            "bfs",
            "failed_no_plan_extracted",
            (),
            1,
            cgas_trace_contract_v3.CONTRACT_ID,
        ),
        (event,),
    )
    trace.write_bytes(trace.read_bytes().replace(b"arm-empty", b"arm-fault", 1))

    with pytest.raises(PilotExpansionIndexError, match="pilot_expansion_stream_invalid"):
        tuple(iter_verified_events(trace))


def test_final_iw_width_enforces_approved_progression(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from scripts.phase3 import cgas_pilot_expansion_materialize as materialize
    from scripts.phase3.cgas_pilot_expansion_index import PilotExpansionIndexError

    trace = tmp_path / "iw.trace-v3.jsonl"

    def events(widths: list[int]) -> object:
        return iter(
            {
                "event": {
                    "decision": "expand",
                    "event_kind": "expansion",
                    "width_decision": f"width_{width}_novel",
                }
            }
            for width in widths
        )

    monkeypatch.setattr(materialize, "iter_verified_events", lambda _: events([1, 1, 2, 2]))
    assert materialize._final_iw_width(trace) == 2
    monkeypatch.setattr(materialize, "iter_verified_events", lambda _: events([2]))
    with pytest.raises(PilotExpansionIndexError, match="pilot_expansion_iw_width_sequence_invalid"):
        materialize._final_iw_width(trace)
    monkeypatch.setattr(materialize, "iter_verified_events", lambda _: events([1, 2, 1]))
    with pytest.raises(PilotExpansionIndexError, match="pilot_expansion_iw_width_sequence_invalid"):
        materialize._final_iw_width(trace)


def test_publish_once_is_byte_stable_and_refuses_collision(tmp_path: Path) -> None:
    from scripts.phase3.cgas_pilot_expansion_index import PilotExpansionIndexError, publish_once

    output = tmp_path / "index.jsonl"

    assert publish_once(output, b'{"row":1}\n') is False
    stat_before = output.stat()
    assert publish_once(output, b'{"row":1}\n') is True
    assert output.stat().st_mtime_ns == stat_before.st_mtime_ns
    with pytest.raises(PilotExpansionIndexError, match="pilot_expansion_publication_collision"):
        publish_once(output, b'{"row":2}\n')
    assert output.read_bytes() == b'{"row":1}\n'


def test_render_coverage_deduplicates_by_full_state_hash(tmp_path: Path) -> None:
    from scripts.phase3.cgas_pilot_expansion_index import build_render_coverage, state_sha256

    index = tmp_path / "index.jsonl"
    render_manifest = tmp_path / "state_render_manifest.jsonl"
    atoms_a = ["(arm-empty)", "(clear b1)"]
    atoms_b = ["(holding b1)"]
    hash_a = state_sha256(atoms_a)
    hash_b = state_sha256(atoms_b)
    rows = [
        {
            "row_id": "a",
            "state_atoms": atoms_a,
            "state_sha256": hash_a,
            "role": "train",
            "object_count": 4,
            "planner": "bfs",
        },
        {
            "row_id": "b",
            "state_atoms": atoms_a,
            "state_sha256": hash_a,
            "role": "train",
            "object_count": 4,
            "planner": "iw",
        },
        {
            "row_id": "c",
            "state_atoms": atoms_b,
            "state_sha256": hash_b,
            "role": "held_out_calibration",
            "object_count": 8,
            "planner": "bfs",
        },
    ]
    index.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    frame = tmp_path / "covered.png"
    frame.write_bytes(b"png-bytes")
    import hashlib

    render_manifest.write_text(
        json.dumps(
            {
                "frame_path": "covered.png",
                "png_sha256": hashlib.sha256(frame.read_bytes()).hexdigest(),
                "state_sha256": hash_a,
                "status": "success",
                "transition": {"state_before": atoms_a},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report, missing = build_render_coverage(index, (render_manifest,), tmp_path)

    assert report["index_row_count"] == 3
    assert report["required_unique_state_count"] == 2
    assert report["covered_unique_state_count"] == 1
    assert report["missing_unique_state_count"] == 1
    assert [row["state_sha256"] for row in missing] == [hash_b]
    partitions = report["partitions"]
    assert isinstance(partitions, dict)
    bfs_partition = partitions["train|4|bfs"]
    iw_partition = partitions["train|4|iw"]
    assert isinstance(bfs_partition, dict)
    assert isinstance(iw_partition, dict)
    assert bfs_partition["covered_rows"] == 1
    assert iw_partition["covered_rows"] == 1
