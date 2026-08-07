from __future__ import annotations

import ast
import hashlib
import importlib
import json
import re
from pathlib import Path

import scripts.phase3.cgas_bfs as cgas_bfs
import scripts.phase3.cgas_partition_characterization as characterization
import pytest

from scripts.phase3.cgas_partition_characterization import (
    CHARACTERIZATION_LIMITS,
    CharacterizationInput,
    canonical_composition_signature,
    characterize_instances,
    load_accepted_blocksworld,
    write_characterization,
)
from scripts.phase3.cgas_partition_contracts import (
    CharacterizationContractError,
    require_full_trace_source,
)
from scripts.phase3.cgas_serialization import canonical
from scripts.phase3.cgas_bfs import run_fifo_bfs
from scripts.phase3.pddl import GroundAction, PDDLTask, parse_task


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = REPOSITORY_ROOT / "tests/fixtures/planning/blocksworld_nontrivial.json"
CHARACTERIZE_AST_SHA256 = "d2867a5e5960b4b4b3434253f59aeee9f274f45435036d5f9bbe239bd3c17a47"
REPRESENTATIVE_ROW_SHA256 = "7d642607a6e7ff4c92a63a52a9656ce1a2b63a7b5c11d79998fa62af80671377"


def test_characterization_kernel_ast_and_representative_row_bytes_are_frozen(tmp_path: Path) -> None:
    # Given: the baseline normalized kernel AST and a representative local Blocksworld task.
    source = Path(characterization.__file__).read_text(encoding="utf-8")
    module = ast.parse(source)
    characterize = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == "_characterize")
    domain, problem = _write_task(tmp_path / "baseline", {"a": "a", "b": "b", "c": "c"})
    instance = CharacterizationInput("baseline", "train", domain, problem, "a" * 64)

    # When: the unmodified scientific kernel characterizes the representative input.
    row_bytes = canonical(characterize_instances((instance,))[0]).encode("utf-8")

    # Then: the kernel and canonical row bytes retain the captured scientific baseline.
    assert hashlib.sha256(ast.dump(characterize, annotate_fields=False, include_attributes=False).encode()).hexdigest() == CHARACTERIZE_AST_SHA256
    assert hashlib.sha256(row_bytes).hexdigest() == REPRESENTATIVE_ROW_SHA256
    rows = importlib.import_module("scripts.phase3.cgas_characterization_rows")
    assert characterization._planner_record is rows._planner_record
    assert characterization.canonical_composition_signature is rows.canonical_composition_signature


def test_characterization_is_name_invariant_and_replay_valid(tmp_path: Path) -> None:
    # Given: equivalent Blocksworld PDDL tasks whose object names differ.
    first_domain, first_problem = _write_task(tmp_path / "first", {"a": "a", "b": "b", "c": "c"})
    second_domain, second_problem = _write_task(tmp_path / "second", {"a": "x", "b": "y", "c": "z"})
    first = CharacterizationInput("first", "train", first_domain, first_problem, "a" * 64)
    second = CharacterizationInput("second", "dev", second_domain, second_problem, "b" * 64)

    # When: the local Stage A/B characterization runs without partition assignment.
    rows = characterize_instances((first, second))

    # Then: PDDL-derived descriptors agree across renaming and both planners replay exactly.
    assert len(rows) == 2
    assert rows[0]["composition_signature"] == rows[1]["composition_signature"]
    for row in rows:
        bfs = row["bfs"]
        iw = row["iw_width_1"]
        assert isinstance(bfs, dict)
        assert isinstance(iw, dict)
        assert row["partition"] is None
        assert row["object_count"] == 3
        assert bfs["implementation"] == "scripts.phase3.cgas_bfs.run_fifo_bfs"
        assert bfs["limits"] == CHARACTERIZATION_LIMITS
        assert iw["implementation"] == "scripts.phase3.local_iw.run_iterated_width"
        assert iw["limits"] == CHARACTERIZATION_LIMITS
        assert bfs["exact_search"]["status"] == "exact_solution_replayed"
        assert iw["characterization_outcome"] == "exact_search_bounded_trace"
        assert iw["retained_trace"]["status"] == "bounded_snapshot"
        assert iw["source_eligibility"] == "ineligible_bounded_trace"


def test_characterization_bytes_are_stable_when_input_order_reverses(tmp_path: Path) -> None:
    # Given: two valid source identities in a deliberately noncanonical input order.
    domain, problem = _write_task(tmp_path / "source", {"a": "a", "b": "b", "c": "c"})
    inputs = (
        CharacterizationInput("zeta", "train", domain, problem, "z" * 64),
        CharacterizationInput("alpha", "test", domain, problem, "a" * 64),
    )

    # When: independently written artifacts receive forward and reversed input sequences.
    forward = write_characterization(characterize_instances(inputs), tmp_path / "forward")
    reverse = write_characterization(characterize_instances(tuple(reversed(inputs))), tmp_path / "reverse")

    # Then: canonical JSONL and manifest bytes are exactly identical.
    assert forward.read_bytes() == reverse.read_bytes()
    assert (forward.parent / "characterization_manifest.json").read_bytes() == (
        reverse.parent / "characterization_manifest.json"
    ).read_bytes()


def test_composition_signature_uses_pddl_state_not_historical_metadata(tmp_path: Path) -> None:
    # Given: a parsed Blocksworld task from the repository fixture.
    domain, problem = _write_task(tmp_path / "source", {"a": "a", "b": "b", "c": "c"})
    task = parse_task(domain, problem)

    # When: its composition signature is derived from parsed init and goal atoms.
    signature = json.loads(canonical_composition_signature(task))

    # Then: the signature contains only structural PDDL composition descriptors.
    assert signature["object_count"] == 3
    assert signature["init"]["stack_heights"]
    assert signature["goal"]["on_edges"] == 1
    assert "bucket" not in signature
    assert "plan_length" not in signature


def test_bfs_retains_only_the_configured_number_of_full_frontier_snapshots() -> None:
    # Given: a linear graph that requires more expansions than its trace cap.
    task = PDDLTask(
        domain_name="trace-cap",
        problem_name="linear",
        objects_by_type={},
        init=frozenset({("state-0",)}),
        goal=frozenset({("state-5",)}),
        actions=(),
        unsupported_features=(),
    )
    actions = tuple(
        GroundAction(
            f"advance-{index}",
            (),
            frozenset({(f"state-{index}",)}),
            frozenset({(f"state-{index + 1}",)}),
            frozenset({(f"state-{index}",)}),
        )
        for index in range(5)
    )

    # When: canonical BFS runs with a smaller trace budget than its full search.
    result = run_fifo_bfs(grounded=actions, task=task, limits={"max_expansions": 10, "max_plan_length": 10, "max_trace_steps": 2})

    # Then: planning completes, while retained full-state snapshots stay bounded.
    assert result.plan == tuple(f"(advance-{index})" for index in range(5))
    assert result.trace["expansion_count"] == 5
    expansions = result.trace["expansions"]
    assert isinstance(expansions, list)
    assert len(expansions) == 2
    assert result.trace["trace_complete"] is False
    assert result.status == "success_truncated_trace"


def test_characterization_reports_exact_search_and_bounded_trace_as_distinct_non_source_state() -> None:
    # Given: an accepted instance whose canonical BFS needs more than one retained snapshot.
    source = REPOSITORY_ROOT / "data/curriculum_pddl/accepted_manifest.jsonl"
    instance = next(
        row
        for row in load_accepted_blocksworld(source)
        if row.instance_id == "blocksworld-dev-easy-0001"
    )

    # When: characterization runs under its one-snapshot retention budget.
    row = characterize_instances((instance,))[0]
    bfs = row["bfs"]

    # Then: exact search metrics are retained without representing a complete transition source.
    assert isinstance(bfs, dict)
    assert bfs["characterization_outcome"] == "exact_search_bounded_trace"
    assert bfs["exact_search"] == {
        "expansion_count": 15,
        "plan_length": 4,
        "status": "exact_solution_replayed",
    }
    assert bfs["retained_trace"]["retained_expansion_count"] == 1
    assert bfs["retained_trace"]["snapshot_budget"] == 1
    assert bfs["retained_trace"]["status"] == "bounded_snapshot"
    assert bfs["source_eligibility"] == "ineligible_bounded_trace"
    assert "success_full_trace" not in bfs.values()
    with pytest.raises(CharacterizationContractError, match="bounded_trace_not_source_ready"):
        require_full_trace_source(bfs)


def test_bfs_sorts_grounded_actions_once_for_the_entire_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = PDDLTask(
        domain_name="sort-once",
        problem_name="linear",
        objects_by_type={},
        init=frozenset({("state-0",)}),
        goal=frozenset({("state-5",)}),
        actions=(),
        unsupported_features=(),
    )
    actions = tuple(
        GroundAction(
            f"advance-{index}",
            (),
            frozenset({(f"state-{index}",)}),
            frozenset({(f"state-{index + 1}",)}),
            frozenset({(f"state-{index}",)}),
        )
        for index in range(5)
    )
    original_sorted = sorted
    grounded_action_sorts = 0

    def observed_sorted(values: object, *args: object, **kwargs: object) -> object:
        nonlocal grounded_action_sorts
        if values is actions:
            grounded_action_sorts += 1
        return original_sorted(values, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(cgas_bfs, "sorted", observed_sorted, raising=False)

    result = run_fifo_bfs(
        grounded=actions,
        task=task,
        limits={"max_expansions": 10, "max_plan_length": 10, "max_trace_steps": 0},
    )

    assert result.status == "success_truncated_trace"
    assert grounded_action_sorts == 1


def _write_task(root: Path, names: dict[str, str]) -> tuple[Path, Path]:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    root.mkdir(parents=True)
    domain = root / "domain.pddl"
    problem = root / "problem.pddl"
    domain.write_text(fixture["domain_pddl"].replace("(domain blocksworld-4ops)", "(domain blocksworld)"), encoding="utf-8")
    text = fixture["problem_pddl"].replace("(:domain blocksworld-4ops)", "(:domain blocksworld)")
    for old, new in names.items():
        text = re.sub(rf"\b{old}\b", new, text)
    problem.write_text(text, encoding="utf-8")
    return domain, problem
