from __future__ import annotations

import importlib
import itertools
import json
import math
from pathlib import Path
from types import ModuleType

import pytest


def _production_candidates() -> ModuleType:
    try:
        return importlib.import_module("scripts.phase3.cgas_production_candidates")
    except ModuleNotFoundError:
        pytest.fail("scripts.phase3.cgas_production_candidates is not implemented")


def test_exact_lehmer_leaf_and_raw_accounting() -> None:
    # Given: every ordinal in a small Lehmer space and the complete four-object stream.
    candidates = _production_candidates()
    expected_permutations = tuple(itertools.permutations(("b00", "b01", "b02", "b03")))

    # When: ordinals are unranked and every four-object raw rank is accounted for.
    actual_permutations = tuple(candidates.lehmer_unrank(4, ordinal) for ordinal in range(math.factorial(4)))
    rows, planner_inputs = candidates.accounting_slice(4, 0, 600)

    # Then: divisor/divmod/pop order, exact leaf bytes, and minimum-rank accounting hold.
    assert actual_permutations == expected_permutations
    assert candidates.canonical_leaf_bytes(candidates.build_candidate(1, 0).graph) == (
        b'{"objects":["o00"],"relations":['
        b'{"arguments":[],"color":"init:arm-empty"},'
        b'{"arguments":[{"label":"arg0","object":"o00"}],"color":"init:clear"},'
        b'{"arguments":[{"label":"arg0","object":"o00"}],"color":"init:on-table"}]}'
    )
    assert tuple(row.raw_rank for row in rows) == tuple(range(600))
    assert len({row.candidate_id for row in rows}) == 228
    assert len({row.candidate_id for row in rows if row.status == "solved"}) == 18
    assert len(planner_inputs) == 210
    assert all(row.status == "emitted" and row.first_raw_rank == row.raw_rank for row in planner_inputs)


@pytest.mark.parametrize("object_count", range(1, 7))
def test_lehmer_unranking_matches_lexicographic_permutations(object_count: int) -> None:
    candidates = _production_candidates()
    names = tuple(f"b{index:02d}" for index in range(object_count))

    actual = tuple(candidates.lehmer_unrank(object_count, ordinal) for ordinal in range(math.factorial(object_count)))

    assert actual == tuple(itertools.permutations(names))
    for ordinal in range(math.factorial(object_count)):
        steps = candidates.lehmer_steps(object_count, ordinal)
        assert tuple(step.divisor for step in steps) == tuple(
            math.factorial(object_count - 1 - index) for index in range(object_count)
        )
        assert steps[-1].remainder == 0


def test_partitions_families_capacities_and_signature_bound_are_exact() -> None:
    candidates = _production_candidates()

    partitions = candidates.integer_partitions(4)
    families = candidates.ordered_families(4)
    twelve_signatures = {
        family.composition_signature
        for family in candidates.ordered_families(12)
        if sum(family.partial_goal_partition) > len(family.partial_goal_partition)
    }

    assert partitions == ((1, 1, 1, 1), (2, 1, 1), (2, 2), (3, 1), (4,))
    assert tuple(family.family_index for family in families) == tuple(range(25))
    assert tuple(
        (family.composition_sha256, family.init_partition_index, family.partial_goal_partition_index)
        for family in families
    ) == tuple(sorted(
        (family.composition_sha256, family.init_partition_index, family.partial_goal_partition_index)
        for family in families
    ))
    assert {count: candidates.stream_capacity(count) for count in (4, 8, 12)} == {
        4: 600,
        8: 19_514_880,
        12: 2_840_000_486_400,
    }
    assert len(twelve_signatures) == 847
    assert max(
        len({family.composition_signature for family in candidates.ordered_families(12)
             if family.init_partition_index == init_index and len(family.partial_goal_partition) < 12})
        for init_index in range(77)
    ) >= 11


def test_stable_init_and_partial_goal_preserve_historical_pddl_conventions() -> None:
    candidates = _production_candidates()
    permutation = ("b03", "b02", "b01", "b00")

    init_atoms = candidates.stable_initial_atoms((3, 1))
    goal_atoms = candidates.partial_goal_atoms((2, 1, 1), permutation)
    problem = candidates.problem_pddl(4, 17, init_atoms, goal_atoms)

    assert init_atoms == frozenset({
        ("arm-empty",),
        ("clear", "b02"),
        ("clear", "b03"),
        ("on", "b01", "b00"),
        ("on", "b02", "b01"),
        ("on-table", "b00"),
        ("on-table", "b03"),
    })
    assert goal_atoms == frozenset({("on", "b02", "b03")})
    assert "(arm-empty)" in problem
    assert "(:goal (and\n    (on b02 b03)\n  ))" in problem
    assert "on-table" not in problem.split("(:goal", maxsplit=1)[1]


def test_graph_edges_colors_refinement_and_individualization_are_exact() -> None:
    candidates = _production_candidates()
    graph = candidates.identity_graph(
        ("left", "right"),
        frozenset({("arm-empty",), ("on-table", "right"), ("clear", "left"), ("on", "left", "right")}),
        frozenset({("on", "right", "left")}),
    )

    descriptors = candidates.initial_color_descriptors(graph)
    initial = candidates.initial_colors(graph)
    refined = candidates.refine_colors(graph, initial)
    left_index = graph.object_names.index("left")
    right_index = graph.object_names.index("right")
    forward = next(relation for relation in graph.relations if relation.sort == "init" and relation.predicate == "on")
    backward = next(relation for relation in graph.relations if relation.sort == "goal")
    arm_empty = next(relation for relation in graph.relations if relation.predicate == "arm-empty")

    assert descriptors[:2] == (b'"object"', b'"object"')
    assert forward.arguments == (left_index, right_index)
    assert backward.arguments == (right_index, left_index)
    assert arm_empty.arguments == ()
    assert all(edge.source >= len(graph.object_names) and edge.target < len(graph.object_names) for edge in graph.edges)
    assert {edge.label for edge in graph.edges if edge.source == graph.relation_vertex(forward)} == {0, 1}
    assert refined[left_index] != refined[right_index]
    left_branch = candidates.individualize_colors(initial, left_index, 2)
    right_branch = candidates.individualize_colors(initial, right_index, 2)
    assert left_branch[left_index] == right_branch[right_index]
    assert left_branch[right_index] == right_branch[left_index]
    assert left_branch[2:] == right_branch[2:]


def test_canonical_leaf_is_shared_rename_and_branch_order_independent() -> None:
    candidates = _production_candidates()
    first = candidates.identity_graph(
        ("a", "b", "c"),
        frozenset({("arm-empty",), ("on-table", "a"), ("on-table", "b"), ("on-table", "c"),
                   ("clear", "a"), ("clear", "b"), ("clear", "c")}),
        frozenset({("on", "a", "b")}),
    )
    second = candidates.identity_graph(
        ("z", "x", "y"),
        frozenset({("arm-empty",), ("on-table", "z"), ("on-table", "x"), ("on-table", "y"),
                   ("clear", "z"), ("clear", "x"), ("clear", "y")}),
        frozenset({("on", "z", "x")}),
    )

    forward = candidates.canonicalize_graph(first, branch_order="forward")
    reverse = candidates.canonicalize_graph(second, branch_order="reverse")
    symmetric = candidates.canonicalize_graph(candidates.identity_graph(
        ("a", "b", "c"),
        frozenset({("arm-empty",), ("on-table", "a"), ("on-table", "b"), ("on-table", "c"),
                   ("clear", "a"), ("clear", "b"), ("clear", "c")}),
        frozenset(),
    ))

    assert forward.leaf_bytes == reverse.leaf_bytes
    assert forward.candidate_id == reverse.candidate_id
    assert symmetric.explored_branches == math.factorial(3)
    assert b"individual" not in forward.leaf_bytes
    assert b'"color":"goal:on"' in forward.leaf_bytes


def test_slice_publication_is_immutable_cursor_free_and_overlap_safe(tmp_path: Path) -> None:
    candidates = _production_candidates()
    config = tmp_path / "config.json"
    output = tmp_path / "candidates"
    config.write_text(json.dumps({
        "schema_version": "cgas_production_candidates_v1",
        "streams": [
            {"object_count": 4, "raw_quota": 190},
            {"object_count": 8, "raw_quota": 198},
            {"object_count": 12, "raw_quota": 93},
        ],
    }), encoding="utf-8")

    receipt = candidates.materialize_slice(config, output, 4, 0, 25)
    range_root = output / "streams/objects-04/raw-000000000000-count-000000000025"
    before = _tree_observables(output)
    rerun = candidates.materialize_slice(config, output, 4, 0, 25)

    assert receipt == rerun
    assert set(path.name for path in range_root.iterdir()) == {
        "planner-inputs.jsonl", "raw-accounting.jsonl", "receipt.json",
    }
    assert before == _tree_observables(output)
    assert not tuple(output.rglob("*cursor*"))
    with pytest.raises(candidates.CandidateContractError, match="range_overlap"):
        candidates.materialize_slice(config, output, 4, 24, 2)
    assert before == _tree_observables(output)


def test_slice_rejects_capacity_and_digest_mismatch_without_mutation(tmp_path: Path) -> None:
    candidates = _production_candidates()
    config = tmp_path / "config.json"
    output = tmp_path / "candidates"
    config.write_text(
        '{"schema_version":"cgas_production_candidates_v1","streams":[{"object_count":4,"raw_quota":190}]}',
        encoding="utf-8",
    )
    candidates.materialize_slice(config, output, 4, 0, 1)
    planner_inputs = next(output.rglob("planner-inputs.jsonl"))
    planner_inputs.write_bytes(planner_inputs.read_bytes() + b"tamper")
    before = _tree_observables(output)

    with pytest.raises(candidates.CandidateContractError, match="artifact_mismatch"):
        candidates.materialize_slice(config, output, 4, 0, 1)
    assert before == _tree_observables(output)
    with pytest.raises(candidates.CandidateContractError, match="capacity"):
        candidates.materialize_slice(config, output, 4, 599, 2)
    assert before == _tree_observables(output)


def _tree_observables(root: Path) -> tuple[tuple[str, bytes, int], ...]:
    return tuple(
        (str(path.relative_to(root)), path.read_bytes(), path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    )
