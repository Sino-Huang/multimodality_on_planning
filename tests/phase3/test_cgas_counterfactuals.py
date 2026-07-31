from __future__ import annotations

from pathlib import Path

from scripts.phase3.cgas_certificates import build_steps, counterfactuals_for, verify_counterfactual
from scripts.phase3.cgas_alignment import build_alignment
from test_cgas_alignment import _build_cgas_source, _write_render_manifest


def test_counterfactuals_mutate_exactly_one_required_certificate_invariant(tmp_path: Path) -> None:
    # Given: valid typed BFS and IW certificate records built from accepted inputs.
    source_root = _build_cgas_source(tmp_path)
    render_manifest = _write_render_manifest(source_root, tmp_path / "renders")
    alignment_root = tmp_path / "alignment-output"
    build_alignment(source_root, render_manifest, alignment_root)
    output_root = tmp_path / "steps"
    build_steps(source_root, alignment_root, output_root)
    records = _records(output_root)

    # When: the builder derives target-only counterfactual variants.
    variants = [variant for record in records for variant in counterfactuals_for(record)]

    # Then: each variant fails only the invariant it declares.
    assert {variant["declared_invariant"] for variant in variants if variant["planner_algorithm"] == "breadth_first_search"} == {"frontier_head", "frontier_order_summary", "visited_delta", "expanded_state"}
    assert {variant["declared_invariant"] for variant in variants if variant["planner_algorithm"] == "iterated_width"} == {"novelty_tuple", "seen_feature_delta", "width_decision"}
    assert all(verify_counterfactual(variant)["failure_count"] == 1 for variant in variants)


def test_two_field_bfs_mutation_is_rejected_as_multiple_invariants_changed(tmp_path: Path) -> None:
    # Given: one valid BFS counterfactual template.
    source_root = _build_cgas_source(tmp_path)
    render_manifest = _write_render_manifest(source_root, tmp_path / "renders")
    alignment_root = tmp_path / "alignment-output"
    build_alignment(source_root, render_manifest, alignment_root)
    output_root = tmp_path / "steps"
    build_steps(source_root, alignment_root, output_root)
    bfs = next(record for record in _records(output_root) if _mapping(record, "planner")["algorithm"] == "breadth_first_search")
    candidate = counterfactuals_for(bfs)[0]
    _mapping(candidate, "certificate")["frontier_head"] = "wrong-frontier"
    _mapping(candidate, "certificate")["visited_delta"] = ["wrong-visited"]

    # When: two independent BFS invariants change in one variant.
    result = verify_counterfactual(candidate)

    # Then: it is explicitly classified as a multi-invariant mutation.
    assert result["reason"] == "multiple_invariants_changed"
    assert result["failure_count"] == 2


def _records(root: Path) -> list[dict[str, object]]:
    import json

    return [json.loads(line) for split in ("train", "dev", "test") for line in (root / "steps" / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()]


def _mapping(record: dict[str, object], field: str) -> dict[str, object]:
    value = record[field]
    assert isinstance(value, dict)
    return value
