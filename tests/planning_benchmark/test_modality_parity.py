from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from examples.planning_benchmark_slice.best_first_controller import (
    BEST_FIRST_SETTINGS,
    BestFirstController,
    BestFirstOperation,
)
from examples.planning_benchmark_slice.modality_observation import (
    ModalityInputLimits,
    ModalityParityError,
    build_matched_best_first_observations,
    render_replayed_paths,
    render_replayed_plan,
    validate_modality_parity,
)
from examples.planning_benchmark_slice.planimation_render import PlanimationRenderRequest

DOMAIN = """(define (domain rooms) (:requirements :strips)
  (:predicates (at ?x) (link ?x ?y))
  (:action move :parameters (?x ?y) :precondition (and (at ?x) (link ?x ?y))
    :effect (and (not (at ?x)) (at ?y))))"""
PROBLEM = """(define (problem rooms-p) (:domain rooms) (:objects a b c)
  (:init (at a) (link a b) (link b a) (link b c)) (:goal (at c)))"""


def request(tmp_path: Path, actions: tuple[str, ...]) -> PlanimationRenderRequest:
    domain = tmp_path / "domain.pddl"
    problem = tmp_path / "problem.pddl"
    profile = tmp_path / "profile.pddl"
    domain.write_text(DOMAIN)
    problem.write_text(PROBLEM)
    profile.write_text("(define (animation rooms))")
    return PlanimationRenderRequest("http://127.0.0.1:18082", domain, problem, profile, actions, tmp_path / "render", 30)


def backend(monkeypatch: pytest.MonkeyPatch, actions: tuple[str, ...]) -> None:
    payload = {
        "visualStages": [
            {
                "stageName": name,
                "visualSprites": [{"name": "agent", "minX": 0.1, "maxX": 0.2, "minY": 0.1, "maxY": 0.2}],
            }
            for name in ("Initial Stage", *actions)
        ]
    }
    monkeypatch.setattr(
        "scripts.planimation_phase1_client.requests.post",
        lambda *args, **kwargs: SimpleNamespace(
            status_code=200, text=json.dumps(payload), content=json.dumps(payload).encode(), json=lambda: payload
        ),
    )


def limits() -> ModalityInputLimits:
    return ModalityInputLimits(
        tokenizer_id="test-word-counter",
        tokenizer_revision="v1",
        max_input_tokens=4096,
        image_width=1024,
        image_height=1536,
        font_size=18,
        max_memory_bytes=8192,
        accepted_delta_limit=16,
        input_size_bins=(1024, 2048, 4096),
    )


def test_replay_binds_return_to_same_state_to_first_frame(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    actions = ("(move a b)", "(move b a)", "(move a b)", "(move b c)")
    backend(monkeypatch, actions)
    rendered = render_replayed_plan(request(tmp_path, actions))

    assert [state.atoms for state in rendered.states] == [("at(a)",), ("at(b)",), ("at(a)",), ("at(b)",), ("at(c)",)]
    assert rendered.frame_for(rendered.states[2]).name == "frame_000.png"
    assert rendered.frame_for(rendered.states[3]).name == "frame_001.png"
    assert rendered.frame_for(rendered.states[4]).name == "frame_004.png"


def test_modalities_expose_static_facts_partial_goal_and_same_candidate_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    actions = ("(move a b)", "(move b c)")
    backend(monkeypatch, actions)
    frames = render_replayed_plan(request(tmp_path, actions))
    controller = BestFirstController(frames.authority, BEST_FIRST_SETTINGS["best_first_add_greedy"])
    controller.start_expansion()
    observations = build_matched_best_first_observations(
        frames=frames,
        controller=controller,
        limits=limits(),
        token_counter=lambda text, images: len(text.split()) + 256 * len(images),
        output_dir=tmp_path / "observations",
    )

    assert [item.modality for item in observations] == ["text-state", "visual-state", "multimodal-state"]
    assert validate_modality_parity(observations, controller=controller) == 3
    text, visual, multimodal = observations
    assert not text.images
    assert len(visual.images) == len(multimodal.images) == 2
    assert [row for row in visual.images[1].relations] == [("goal", "at", ("c",))]
    assert ("static", "link", ("b", "a")) in visual.images[0].relations
    assert "state" not in json.loads(visual.prompt)
    assert "goal" not in json.loads(visual.prompt)
    memories = [json.loads(item.prompt)["search_memory"] for item in observations]
    assert memories[0] == memories[1] == memories[2]
    assert memories[0]["successor_candidates"][0]["closed"] is False
    assert memories[0]["successor_candidates"][0]["frontier"] is False
    assert all(image.path.is_file() for image in visual.images)


@pytest.mark.parametrize("capacity", ["accepted_delta_limit", "max_memory_bytes", "image_height", "max_input_tokens"])
def test_input_capacity_fails_without_silently_dropping_facts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capacity: str,
) -> None:
    actions = ("(move a b)", "(move b c)")
    backend(monkeypatch, actions)
    frames = render_replayed_plan(request(tmp_path, actions))
    controller = BestFirstController(frames.authority, BEST_FIRST_SETTINGS["best_first_add_greedy"])
    controller.start_expansion()
    if capacity == "max_input_tokens":
        frozen = replace(limits(), max_input_tokens=1, input_size_bins=(1,))
    else:
        frozen = replace(limits(), **{capacity: 1})
    with pytest.raises(ModalityParityError, match=r"capacity|height|tokens"):
        build_matched_best_first_observations(
            frames=frames,
            controller=controller,
            limits=frozen,
            token_counter=lambda text, images: 100,
            output_dir=tmp_path / "observations",
        )


@pytest.mark.parametrize("algorithm", ["best_first_add_w3", "best_first_add_greedy"])
def test_each_decision_replays_with_exact_membership_and_distinct_state_frames(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    algorithm: str,
) -> None:
    actions = ("(move a b)", "(move b c)")
    backend(monkeypatch, actions)
    frames = render_replayed_plan(request(tmp_path, actions))
    controller = BestFirstController(frames.authority, BEST_FIRST_SETTINGS[algorithm])
    records = []
    while not frames.authority.is_goal(controller.node_state(controller.frontier_head_state_id() or "")):
        controller.start_expansion()
        for candidate in controller.current_candidates():
            observations = build_matched_best_first_observations(
                frames=frames,
                controller=controller,
                limits=limits(),
                token_counter=lambda text, images: 100,
                output_dir=tmp_path / "observations",
            )
            operation = BestFirstOperation(controller.active_state_ref or "", candidate.action)
            records.append((observations, operation))
            assert controller.apply_operation(operation).accepted
        controller.finish_expansion()

    assert len(records) == 3
    assert records[0][0][1].images[0].path != records[1][0][1].images[0].path
    memory = json.loads(records[1][0][1].prompt)["search_memory"]
    assert memory["successor_candidates"][0]["closed"] is True
    assert memory["successor_candidates"][0]["dominated"] is True
    assert memory["successor_candidates"][0]["target_state_id"] == "s0"
    replay = BestFirstController(frames.authority, BEST_FIRST_SETTINGS[algorithm])
    for observations, operation in records:
        if replay.active_state_id is None:
            replay.start_expansion()
        assert validate_modality_parity(observations, controller=replay) == 3
        assert replay.apply_operation(operation).accepted
        if not replay.current_candidates():
            replay.finish_expansion()


@pytest.mark.parametrize("defect", ["static", "goal", "membership", "capacity", "goal_meaning", "replay_capacity"])
def test_replay_rejects_modality_specific_semantic_omission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    defect: str,
) -> None:
    actions = ("(move a b)", "(move b c)")
    backend(monkeypatch, actions)
    frames = render_replayed_plan(request(tmp_path, actions))
    controller = BestFirstController(frames.authority, BEST_FIRST_SETTINGS["best_first_add_greedy"])
    controller.start_expansion()
    observations = list(
        build_matched_best_first_observations(
            frames=frames,
            controller=controller,
            limits=limits(),
            token_counter=lambda text, images: 100,
            output_dir=tmp_path / "observations",
        )
    )
    visual = observations[1]
    if defect == "static":
        state_image = replace(
            visual.images[0], relations=tuple(row for row in visual.images[0].relations if row[0] != "static")
        )
        observations[1] = replace(visual, images=(state_image, visual.images[1]))
    elif defect == "goal":
        observations[1] = replace(visual, images=(visual.images[0], replace(visual.images[1], relations=())))
    elif defect == "membership":
        payload = json.loads(visual.prompt)
        payload["search_memory"]["successor_candidates"][0].pop("closed")
        observations[1] = replace(visual, prompt=json.dumps(payload))
    elif defect == "capacity":
        observations[1] = replace(visual, limits=replace(limits(), max_memory_bytes=16384))
    elif defect == "goal_meaning":
        payload = json.loads(visual.prompt)
        payload["relation_legend"] = "Unlisted goal facts are false."
        observations[1] = replace(visual, prompt=json.dumps(payload))
    else:
        observations = [replace(item, limits=replace(item.limits, accepted_delta_limit=1)) for item in observations]
    with pytest.raises(ModalityParityError, match=r"replay|capacit|interpretation"):
        validate_modality_parity(observations, controller=controller)


def test_render_interpretation_must_follow_supplied_actions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    backend(monkeypatch, ("(move b c)", "(move a b)"))
    with pytest.raises(ModalityParityError, match="Plan Interpretation"):
        render_replayed_plan(request(tmp_path, ("(move a b)", "(move b c)")))


def test_frame_binding_uses_action_semantics_not_casing_or_whitespace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend(monkeypatch, ("( MOVE  a b )",))
    frames = render_replayed_plan(request(tmp_path, ("(move a b)",)))
    assert frames.states[-1].atoms == ("at(b)",)


def test_branch_catalog_binds_states_outside_the_solution_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = request(tmp_path, ("(move a b)", "(move b c)"))
    base.problem_path.write_text(PROBLEM.replace("a b c)", "a b c d)").replace("(at a)", "(at a) (link a d)"))

    def post(*args: object, **kwargs: object) -> object:
        files = kwargs["files"]
        assert isinstance(files, dict)
        actions = str(files["plan"][1]).splitlines()
        payload = {"visualStages": [{"stageName": name, "visualSprites": []} for name in ("Initial Stage", *actions)]}
        return SimpleNamespace(
            status_code=200, text=json.dumps(payload), content=json.dumps(payload).encode(), json=lambda: payload
        )

    monkeypatch.setattr("scripts.planimation_phase1_client.requests.post", post)
    frames = render_replayed_paths(base, (("(move a d)",), ("(move a b)", "(move b c)")))
    branch = frames.authority.canonical_state(("at(d)",))
    goal = frames.authority.canonical_state(("at(c)",))
    assert frames.frame_for(branch).name == "frame_001.png"
    assert frames.frame_for(goal).name == "frame_002.png"
    assert frames.frame_for(branch).parent != frames.frame_for(goal).parent
