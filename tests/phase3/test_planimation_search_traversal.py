from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.phase3.planimation_pairing import (
    PairingConfig,
    RenderConfig,
    build_pairing_manifest,
    build_vlm_records,
    render_replay_states,
)
from scripts.phase3.trace_contracts import FrozenSourceIdentity
from scripts.phase3.traversal_state_types import TraversalProjectionInput
from scripts.phase3.traversal_states import project_traversal_state_candidates
from tests.phase3.test_planimation_pairing import _output_root, _render_artifacts, _source_root


FIXTURES = Path("tests/phase3/fixtures/traversal_state_projection_cases.json")


@pytest.mark.parametrize("planner", ("ff", "gbfs", "iw"))
def test_emits_distinct_search_traversal_records_for_concrete_candidates(tmp_path: Path, planner: str) -> None:
    # Given: a strict concrete traversal fixture and the existing replay source.
    source_root = _source_root(tmp_path)
    source = json.loads((source_root / "train.jsonl").read_text(encoding="utf-8"))
    fixture = _fixture(planner)
    source["planner"] = planner
    source["supervised_target"]["planner_trace"] = json.loads(json.dumps(fixture["supervised_target"]["planner_trace"]).replace("(MOVE A B)", "(move a b)"))
    source["supervised_target"]["replay_transitions"][0]["state_before"].append("(connected b a)")
    source["supervised_target"]["replay_transitions"][0]["state_after"].append("(connected b a)")
    (source_root / "train.jsonl").write_text(json.dumps(source) + "\n", encoding="utf-8")
    output_root = _output_root(tmp_path)

    # When: production rendering and hybrid record emission run.
    build_pairing_manifest([source_root], output_root, config=_config())
    render_replay_states(
        output_root,
        renderer=lambda _domain, _problem, _profile, cache_dir, _config: _render_artifacts(cache_dir),
        config=RenderConfig(request_delay_seconds=0),
    )
    summary = build_vlm_records(output_root)
    records = _rows(output_root / "search_traversal_train.jsonl")

    # Then: candidate events remain separate from plan replay while equal assets may be reused.
    assert summary["search_traversal_records"] == {"train": 2, "dev": 0, "test": 0}
    assert {record["record_type"] for record in records} == {"search_traversal_record"}
    assert {record["supervision_mode"] for record in records} == {"search_traversal"}
    assert len({record["provenance"]["event"]["event_id"] for record in records}) == 2
    assert len({record["provenance"]["state"]["state_asset_hash"] for record in records}) == 2


def test_excludes_ff_successor_without_recorded_state_atoms() -> None:
    # Given: FF succeeds at the strict trace boundary but omits its successor state.
    source = _fixture("ff")
    successor = source["supervised_target"]["planner_trace"]["steps"][0]["selected_successor"]
    del successor["state_atoms"]
    del source["supervised_target"]["planner_trace"]["steps"][0]["successor_heuristics"][0]["state_atoms"]

    # When: the projection evaluates render eligibility.
    projection = project_traversal_state_candidates(
        TraversalProjectionInput(_identity(source), source, Path("tests/phase3/fixtures/traversal_state_domain.pddl"), Path("tests/phase3/fixtures/traversal_state_problem.pddl"))
    )

    # Then: FF never reconstructs an absent successor state.
    assert len(projection.candidates) == 1
    assert [exclusion.reason for exclusion in projection.exclusions] == ["ff_missing_recorded_successor_state"]


def test_shared_traversal_asset_preserves_distinct_search_events(tmp_path: Path) -> None:
    # Given: one GBFS traversal with generation, revisit, and backtrack events for the same successor state.
    source_root = _source_root(tmp_path)
    source = json.loads((source_root / "train.jsonl").read_text(encoding="utf-8"))
    fixture = _fixture("gbfs_semantic_repeat")
    source["supervised_target"]["planner_trace"] = fixture["supervised_target"]["planner_trace"]
    source["supervised_target"]["replay_transitions"][0]["state_before"].append("(connected b a)")
    source["supervised_target"]["replay_transitions"][0]["state_after"].append("(connected b a)")
    (source_root / "train.jsonl").write_text(json.dumps(source) + "\n", encoding="utf-8")
    output_root = _output_root(tmp_path)

    # When: the candidates are rendered and emitted through the separate traversal stream.
    build_pairing_manifest([source_root], output_root, config=_config())
    render_replay_states(output_root, renderer=lambda _domain, _problem, _profile, cache_dir, _config: _render_artifacts(cache_dir), config=RenderConfig(request_delay_seconds=0))
    build_vlm_records(output_root)
    records = _rows(output_root / "search_traversal_train.jsonl")
    successor_records = [record for record in records if record["provenance"]["event"]["state_role"] == "successor"]

    # Then: three graph events reuse one state asset without collapsing their event IDs or semantics.
    assert len(successor_records) == 3
    assert len({record["provenance"]["event"]["event_id"] for record in successor_records}) == 3
    assert len({record["provenance"]["event"]["event_kind"] for record in successor_records}) == 3
    assert len({record["provenance"]["state"]["state_asset_hash"] for record in successor_records}) == 1


def test_graphplan_semantic_layers_do_not_emit_search_traversal_records(tmp_path: Path) -> None:
    # Given: a Graphplan fixture with raw semantic layers and one extracted plan.
    source_root = _source_root(tmp_path, planner="graphplan")
    output_root = _output_root(tmp_path)

    # When: the hybrid pipeline renders its permitted plan replay path.
    build_pairing_manifest([source_root], output_root, config=_config())
    render_replay_states(
        output_root,
        renderer=lambda _domain, _problem, _profile, cache_dir, _config: _render_artifacts(cache_dir),
        config=RenderConfig(request_delay_seconds=0),
    )
    build_vlm_records(output_root)

    # Then: Graphplan layers remain absent from the visual search-traversal stream.
    assert _rows(output_root / "search_traversal_train.jsonl") == []


def test_rejects_output_root_equal_to_or_nested_under_a_source_root(tmp_path: Path) -> None:
    # Given: a fixture source root selected for a production manifest.
    source_root = _source_root(tmp_path)

    # When / Then: output creation cannot target the immutable source tree or a child.
    with pytest.raises(ValueError, match="output_root must not equal or be nested under a source root"):
        build_pairing_manifest([source_root], source_root, config=_config())
    with pytest.raises(ValueError, match="output_root must not equal or be nested under a source root"):
        build_pairing_manifest([source_root], source_root / "derived", config=_config())


def _config() -> PairingConfig:
    return PairingConfig(domains=frozenset({"grid"}), buckets=frozenset({"easy"}))


def _fixture(name_or_planner: str) -> dict[str, object]:
    fixtures = json.loads(FIXTURES.read_text(encoding="utf-8"))
    return next(case["source_row"] for case in fixtures if case["name"] == name_or_planner or case["source_row"]["planner"] == name_or_planner)


def _identity(source: dict[str, object]) -> FrozenSourceIdentity:
    return FrozenSourceIdentity("fixture-root", "train.jsonl", 0, "hash", str(source["example_id"]), str(source["planner"]))


def _rows(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
