"""Readable successor semantics, pagination and qualification gates."""

import copy
import json

import pytest
from PIL import Image

from examples.planning_benchmark_slice.modality_pages import (
    PAGE_SIZE,
    ROLES,
    PageRecipe,
    StatePageCache,
    compose_page,
    fact_blocks,
    font,
    paginate,
    project_messages,
    validate_pages,
    wrap,
)
from examples.planning_benchmark_slice.modality_view_preparation import (
    CONTRACT,
    recommend_context,
    require_approval,
    validate_process_state,
)
from examples.planning_benchmark_slice.source_goal import evaluate_goal, goal_blocks, source_task, validate_goal

SOURCE = {
    "objects_by_type": {"button": ["b1", "b2"], "block": ["c1", "c2"], "position": ["p1", "p2"]},
    "type_parents": {"button": "object", "block": "object", "position": "object"},
}
SOKOBAN = [
    "forall",
    [["?b", "button"]],
    [
        "exists",
        [["?c", "block"], ["?p", "position"]],
        ["and", [["atom", "at", ["?b", "?p"]], ["atom", "at", ["?c", "?p"]]]],
    ],
]


def test_sokoban_each_button_shares_position_with_some_block():
    facts = {"at(b1,p1)", "at(b2,p2)", "at(c1,p1)", "at(c2,p2)"}
    assert evaluate_goal(SOKOBAN, facts, SOURCE)
    assert not evaluate_goal(SOKOBAN, facts - {"at(c2,p2)"}, SOURCE)
    blocks = goal_blocks(SOKOBAN)
    assert "FOR EVERY" in blocks[0]["label"]
    assert "THERE EXISTS" in blocks[1]["label"]
    assert blocks[1]["text"] == "?c : block; ?p : position"


def test_snake_forbidden_points_are_constraints_not_satisfaction():
    goal = ["and", [["atom", "at", ["head", "p1"]], ["not", ["atom", "at", ["head", "p2"]]]]]
    assert evaluate_goal(goal, {"at(head,p1)"}, SOURCE)
    assert not evaluate_goal(goal, {"at(head,p1)", "at(head,p2)"}, SOURCE)
    assert any("NOT" in block["label"] for block in goal_blocks(goal))


def test_quantifier_lexical_shadowing_inheritance_and_empty_domains():
    source = {"objects_by_type": {"child": ["a", "b"]}, "type_parents": {"child": "parent", "parent": "object"}}
    goal = [
        "forall",
        [["?x", "parent"]],
        ["and", [["exists", [["?x", "child"]], ["atom", "p", ["?x"]]], ["atom", "q", ["?x"]]]],
    ]
    assert evaluate_goal(goal, {"p(a)", "q(a)", "q(b)"}, source)
    assert not evaluate_goal(goal, {"p(a)", "q(a)"}, source)
    assert evaluate_goal(["forall", [["?x", "empty"]], ["false"]], set(), source)
    assert not evaluate_goal(["exists", [["?x", "empty"]], ["true"]], set(), source)


@pytest.mark.parametrize(
    "goal,expected",
    [(["true"], True), (["false"], False), (["and", []], True), (["or", []], False), (["not", ["false"]], True)],
)
def test_empty_and_boolean_goals(goal, expected):
    assert evaluate_goal(goal, set(), SOURCE) == expected
    assert goal_blocks(goal)


@pytest.mark.parametrize("goal", [["expression", "(> (fuel) 1)"], ["atom", "p", ["?free"]], ["atom", "@exists-2@", []]])
def test_unsupported_and_unbound_stop(goal):
    with pytest.raises(ValueError):
        validate_goal(goal)


def test_source_goal_is_recovered_before_normalization():
    from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority

    domain = """(define (domain d) (:requirements :typing :adl) (:types item)
    (:predicates (p ?x - item))
    (:action add :parameters (?x - item) :precondition (and) :effect (p ?x)))"""
    problem = """(define (problem p) (:domain d) (:objects a - item)
    (:init) (:goal (exists (?x - item) (p ?x))))"""
    source = source_task(domain, problem)
    authority = PDDLStateAuthority.from_pddl(domain, problem)
    assert source["source_goal"][0] == "exists"
    assert "@exists" not in json.dumps(source)
    initial = authority.initial_state
    for state in (initial, authority.apply(initial, authority.applicable_actions(initial)[0]).target_state):
        assert evaluate_goal(source["source_goal"], set(state.atoms), source) == authority.is_goal(state)


def test_dense_long_names_continuations_and_no_clipping(tmp_path):
    text = "; ".join(f"predicate(object_{i}_{'x' * 300},second_argument_{i})" for i in range(60))
    blocks = [{"id": "facts:0", "label": "state / predicate", "text": text}]
    pages = paginate("current-state", blocks)
    assert len(pages) > 2
    assert any("continued" in f["label"] for p in pages for f in p.fragments)
    validate_pages(blocks, pages)
    assert "".join(wrap(text, 332)) == text
    for page in pages:
        for fragment in page.fragments:
            assert fragment["y"] + 32 * (len(fragment["heading"]) + len(fragment["lines"])) <= 980
            for line in fragment["heading"] + fragment["lines"]:
                assert font().getlength(line) <= fragment["width"] - 16
        assert compose_page(page, tmp_path).size == PAGE_SIZE
    corrupt = copy.deepcopy(pages[0].to_dict())
    corrupt["fragments"][0]["text"] = "omitted"
    with pytest.raises(ValueError):
        validate_pages(blocks, (PageRecipe(**corrupt), *pages[1:]))


def test_grouping_preserves_fact_arguments_fluents_and_source_types():
    context = {
        "static_initial_facts": ["connected(b,a)", "connected(a,b)"],
        "initial_dynamic_atoms": ["at(a,b)"],
        "initial_dynamic_fluents": ["fuel(a)=17"],
    }
    source = {**SOURCE, "source_goal": SOKOBAN}
    blocks = fact_blocks(context, {"atoms": ["at(b,a)"], "fluents": ["fuel(a)=9"]}, source)
    assert (
        next(b["text"] for b in blocks["task-context"] if b["label"] == "static / connected")
        == "connected(a,b); connected(b,a)"
    )
    for role in ROLES:
        pages = paginate(role, blocks[role])
        validate_pages(blocks[role], pages)
    assert any("fuel(a)=9" in b["text"] for b in blocks["current-state"])


def test_cache_is_bounded_and_task_state_page_keyed(tmp_path):
    size = PAGE_SIZE[0] * PAGE_SIZE[1] * 3
    cache = StatePageCache(tmp_path, capacity=size)
    page = paginate("current-state", [{"id": "a", "label": "state", "text": "p(a)"}])[0]
    first = cache.get("task-a", 0, page)
    first.putpixel((0, 0), (0, 0, 0))
    assert cache.get("task-a", 0, page).getpixel((0, 0)) == (255, 255, 255)
    cache.get("task-b", 0, page)
    assert list(cache.pages) == [("task-b", 0, 0)]
    assert cache.bytes == size


def test_visual_text_parity_and_common_candidates():
    raw = {
        "observation": {"state_atoms": ["p(a)"], "state_id": "s0"},
        "task_context": {},
        "goal_atoms": ["p(b)"],
        "search_memory": {"accepted_deltas": [], "successor_candidates": [{"target_state_id": "s1"}]},
    }
    blocks = {role: [{"id": role, "label": role, "text": "p(a)"}] for role in ROLES}
    common = []
    for modality in ("text-state", "visual-state", "multimodal-state"):
        messages = project_messages(raw, "bfs", modality, blocks, [(role, f"{role}.png") for role in ROLES])
        content = messages[-1]["content"]
        payload = json.loads(content[0]["text"])
        assert payload["search_memory"] == raw["search_memory"]
        if modality != "visual-state":
            assert payload.pop("semantic_blocks") == blocks
        payload.pop("representation")
        common.append(payload)
        assert len([c for c in content if c["type"] == "image"]) == (0 if modality == "text-state" else 3)
        assert "s1.png" not in json.dumps(messages)
    assert common[0] == common[1] == common[2]


def test_context_reserves_output_and_stops_at_32k():
    assert recommend_context(8192 - 384) == 8192
    assert recommend_context(8192 - 383) == 16384
    assert recommend_context(32768 - 384) == 32768
    assert recommend_context(32768 - 383) is None


def test_approval_requires_complete_matching_preview_context_and_output(tmp_path):
    qualification = {
        "contract": CONTRACT,
        "counts": CONTRACT["expected"],
        "complete_selected_coverage": True,
        "outcome": "PASS",
        "processor_qualified": True,
        "attempt_id": "q1",
        "recommended_context": 16384,
        "preview_index": "q1/previews.json",
    }
    approval = {
        "contract_id": CONTRACT["contract_id"],
        "qualification_attempt": "q1",
        "materialization_output": str(tmp_path.resolve()),
        "approved_context": 16384,
        "readability_approved": True,
        "preview_index": "q1/previews.json",
        "approved_by": "human",
    }
    require_approval(approval, qualification, tmp_path)
    for key, bad in [
        ("approved_context", 8192),
        ("readability_approved", False),
        ("qualification_attempt", "q0"),
        ("approved_by", ""),
    ]:
        with pytest.raises(ValueError):
            require_approval({**approval, key: bad}, qualification, tmp_path)
    with pytest.raises(ValueError):
        require_approval(approval, {**qualification, "complete_selected_coverage": False}, tmp_path)


def test_wrong_process_state_stops():
    with pytest.raises(ValueError, match="wrong observed state"):
        validate_process_state({"observation": {"state_atoms": ["p(a)"]}}, "bfs", {"atoms": ["p(b)"], "fluents": []})


@pytest.mark.parametrize(
    "goal",
    [
        "(p)",
        "(exists (?x - item) (marked ?x))",
        "(forall (?x - item) (exists (?y - item) (and (marked ?x) (marked ?y))))",
    ],
    ids=["atom", "exists", "forall-exists"],
)
def test_interrupted_materialization_reuses_scenes_and_rejects_partial(tmp_path, monkeypatch, goal):
    from examples.planning_benchmark_slice import modality_view_preparation as prep
    from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority

    domain = """(define (domain d) (:requirements :typing :adl) (:types item)
    (:predicates (p) (marked ?x - item))
    (:action add :parameters (?x - item) :precondition (and) :effect (and (p) (marked ?x))))"""
    problem = f"(define (problem p) (:domain d) (:objects a - item) (:init) (:goal {goal}))"
    authority = PDDLStateAuthority.from_pddl(domain, problem)
    state = authority.initial_state
    scene = tmp_path / "original.png"
    Image.new("RGB", (128, 128), "red").save(scene)
    catalog = {
        "task_id": "tiny",
        "task_context": authority.task_context(),
        "canonical_goal": authority.canonical_goal,
        "split": "dev",
        "source_trace_paths": {"bfs": "trace.json"},
        "reference_costs": {"bfs": {"decisions": 1}},
        "states": [
            {"index": 0, "atoms": list(state.atoms), "fluents": [], "parent": None, "scene_path": "original.png"}
        ],
        "decisions": [{"algorithm": "bfs", "index": 0, "state": 0, "successor": None}],
    }
    prep.write_json(tmp_path / "catalog.json.gz", catalog)
    row = {
        "task_id": "tiny",
        "domain": "d",
        "split": "dev",
        "trace_paths": {"bfs": "trace.json"},
        "reference_costs": catalog["reference_costs"],
    }
    monkeypatch.setattr(prep, "load_scene_task", lambda *_: (domain, problem, {}))
    output = tmp_path / "views"
    original_compose = prep.compose_page
    calls = 0

    def interrupted(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("interrupted")
        return original_compose(*args)

    monkeypatch.setattr(prep, "compose_page", interrupted)
    with pytest.raises(OSError, match="interrupted"):
        prep.prepare_task(tmp_path, row, {"catalog": "catalog.json.gz"}, "materialize", output)
    assert not (output / "manifest.json.gz").exists()
    monkeypatch.setattr(prep, "compose_page", original_compose)
    result = prep.prepare_task(tmp_path, row, {"catalog": "catalog.json.gz"}, "materialize", output)
    assert prep.check_task(tmp_path, result, row)["states"] == 1
    with monkeypatch.context() as reuse_patch:

        def forbidden_render(*_):
            raise AssertionError("reuse must not render")

        reuse_patch.setattr(prep, "compose_page", forbidden_render)
        assert prep.reuse_task(tmp_path, result, row) == result
    assert not list(output.glob("*state*.png"))
    manifest = prep.read_json(tmp_path / result["manifest"])
    assert manifest["state_recipes"][0][0]["scene"] == "original.png"
    original_goal = manifest["source"]["source_goal"]
    manifest["source"]["source_goal"] = ["true"]
    prep.write_json(tmp_path / result["manifest"], manifest)
    with pytest.raises(ValueError, match="source-goal/task/split binding differs"):
        prep.check_task(tmp_path, result, row)
    manifest["source"]["source_goal"] = original_goal
    manifest["decisions"][0]["input_pages"][1][1] = 99
    prep.write_json(tmp_path / result["manifest"], manifest)
    with pytest.raises(ValueError, match="future-image leakage"):
        prep.check_task(tmp_path, result, row)
    manifest["decisions"] = []
    prep.write_json(tmp_path / result["manifest"], manifest)
    with pytest.raises(ValueError, match="partial manifest coverage"):
        prep.check_task(tmp_path, result, row)


def test_cli_refuses_materialization_without_approval(tmp_path, monkeypatch, capsys):
    from types import SimpleNamespace

    from scripts import prepare_modality_views as cli

    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(cli, "EXPECTED", {"tasks": 1})
    monkeypatch.setattr(
        cli, "load_modality_phase", lambda: SimpleNamespace(components={"corpus": {"panel_manifest": "panel"}})
    )
    monkeypatch.setattr(cli, "read_json", lambda _: {"selected": [{"task_id": "tiny"}]})
    monkeypatch.setattr(cli, "validate_scene_selection", lambda *_: {})
    assert cli.main(["--materialize", "--output", str(tmp_path / "output")]) == 1
    assert "--approval is required" in capsys.readouterr().out
    assert not list(tmp_path.iterdir())


def test_frozen_processor_full_input_and_resizing():
    import os

    from examples.planning_benchmark_slice.modality_view_preparation import FrozenPageProcessor

    if os.environ.get("ISSUE72_PROCESSOR_TESTS") != "1":
        pytest.skip("opt-in local frozen processor test")
    processor = FrozenPageProcessor()
    image = Image.new("RGB", PAGE_SIZE, "white")
    messages = project_messages({"search_memory": {}}, "bfs", "multimodal-state", {}, [(role, image) for role in ROLES])
    processor.verify_complete(messages, [image] * 3)
    assert processor.cross_checked
    assert processor.preview(image).size == PAGE_SIZE
    resized = Image.new("RGB", (1000, 700), "white")
    preview = processor.preview(resized)
    assert preview.size != resized.size
    assert preview.width % 32 == preview.height % 32 == 0
    with pytest.raises(ValueError, match="token expansion"):
        processor.verify_complete(messages, [resized] * 3)


def test_duplicate_empty_constraint_is_rejected():
    blocks = goal_blocks(["true"])
    page = paginate("goal", blocks)[0]
    duplicate = PageRecipe("goal", 0, 1, page.fragments + page.fragments)
    with pytest.raises(ValueError, match="duplicated"):
        validate_pages(blocks, (duplicate,))
