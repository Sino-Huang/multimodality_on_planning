"""Governed matched Modality Observation execution behind the Search Episode Harness."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, TypeAlias

from src.data_collect.governance import (
    AuthorizationReceipt,
    GateReceipt,
    ReceiptBinding,
    RunReceipt,
    StopOutcome,
    evaluate_execution_permission,
)

from .best_first_controller import BEST_FIRST_SETTINGS, BestFirstController
from .modality_observation import (
    MODALITIES,
    Modality,
    ModalityInputLimits,
    ModalityObservation,
    RelationImage,
    TokenCounter,
    build_matched_best_first_observations,
    render_replayed_paths,
    validate_modality_parity,
)
from .pddl_state import GroundedAction, PDDLStateAuthority
from .planimation_render import PlanimationRenderRequest

MessagePolicy: TypeAlias = Callable[[list[dict[str, Any]]], str]
Progress: TypeAlias = Callable[[dict[str, Any]], None]
SCHEMA_VERSION = "matched_modality_episode_v1"


@dataclass(frozen=True)
class MatchedEpisodeRequest:
    binding: ReceiptBinding
    algorithm: str
    max_expansions: int
    max_decisions: int
    render: PlanimationRenderRequest
    supplied_paths: tuple[tuple[str, ...], ...]
    limits: ModalityInputLimits


def run_matched_modality_episode(
    request: MatchedEpisodeRequest,
    *,
    gate_receipt: GateReceipt,
    authorization_receipt: AuthorizationReceipt | None,
    policies: Mapping[Modality, MessagePolicy],
    token_counter: TokenCounter,
    progress: Progress | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Execute independent modality policies only after permission for this output binding."""
    permission = evaluate_execution_permission(
        binding=request.binding,
        gate_receipt=gate_receipt,
        authorization_receipt=authorization_receipt,
        ancestor_receipt_id=gate_receipt.ancestor_receipt_id,
    )
    if not permission.start_permitted:
        return _stopped(permission)
    episodes: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "permission": permission.to_dict(),
        "episodes": episodes,
        "execution_started": False,
        "scientific_completion": False,
    }
    try:
        if request.algorithm not in {"best_first_add_w3", "best_first_add_greedy"}:
            raise ValueError("matched episode requires an active additive best-first setting")
        if min(request.max_expansions, request.max_decisions) <= 0:
            raise ValueError("episode budgets must be positive")
        if set(policies) != set(MODALITIES):
            raise ValueError("one independent policy is required for each modality")
        domain = request.render.domain_path.read_text()
        problem = request.render.problem_path.read_text()
        # Preflight replays the supplied paths without HTTP or policy/tokenizer calls.
        _replay_paths(domain, problem, request.supplied_paths)
        request.render.animation_profile_path.read_text()
        report["header"] = {
            "request": json.loads(json.dumps(asdict(request), default=str)),
            "gate_receipt": gate_receipt.to_dict(),
            "authorization_receipt": authorization_receipt.to_dict() if authorization_receipt else None,
            "domain_pddl": domain,
            "problem_pddl": problem,
            "policy_role": "matched_infrastructure_episode",
        }
        if dry_run:
            return {**report, "outcome": "PASS", "status": "dry_run", "planned_modalities": list(MODALITIES)}
        root = Path(request.binding.output_root)
        report["execution_started"] = True
        _progress(progress, "render_started", paths=len(request.supplied_paths))
        frames = render_replayed_paths(replace(request.render, output_dir=root / "render"), request.supplied_paths)
        report["header"]["frame_bindings"] = [
            {"atoms": list(state.atoms), "fluents": list(state.fluents), "frame": str(path.relative_to(root))}
            for state, path in zip(frames.states, frames.frame_paths, strict=True)
        ]
        _progress(progress, "render_complete", frames=len(frames.states))
        for modality in MODALITIES:
            controller = _controller(domain, problem, request.algorithm, request.max_expansions, request.limits)
            events: list[dict[str, Any]] = []
            _progress(progress, "episode_started", modality=modality)
            while (termination := _advance(controller, request.max_decisions)) is None:
                matched = build_matched_best_first_observations(
                    frames=frames,
                    controller=controller,
                    limits=request.limits,
                    token_counter=token_counter,
                    output_dir=root / "observations" / modality,
                )
                observation = matched[MODALITIES.index(modality)]
                raw_output = policies[modality](observation.messages())
                result = controller.apply_raw_output(raw_output)
                events.append(
                    {
                        "index": len(events),
                        "observation": _observation_record(observation, root),
                        "raw_output": raw_output,
                        "runtime": dict(result.runtime_result),
                    }
                )
                _progress(
                    progress,
                    "decision",
                    modality=modality,
                    completed=len(events),
                    decision_limit=request.max_decisions,
                    accepted=result.accepted,
                    expansions=controller.expansion_count,
                    budget_used=controller.budget_used,
                )
            episodes.append({"modality": modality, "events": events, "result": _result(controller, termination)})
            _progress(progress, "episode_complete", modality=modality, **episodes[-1]["result"])
        outcome = _outcome(episodes)
        report.update(outcome=outcome.value, scientific_completion=outcome is StopOutcome.PASS)
        report["aligned_decisions"] = len(episodes[0]["events"])
        replay = replay_matched_modality_episode(report)
        report["replayed_episodes"] = replay["replayed_episodes"]
        if outcome is StopOutcome.VALID_STOP:
            report["gated_not_run_receipt"] = _terminal_receipt(
                permission, outcome, "episode budget or frontier exhausted"
            )
        report["run_receipt"] = _terminal_receipt(permission, outcome, None)
        _progress(progress, "replay_complete", **replay)
        return report
    except (ValueError, RuntimeError, OSError) as error:
        report.update(outcome="INVALID", scientific_completion=False, reason=str(error))
        report.pop("aligned_decisions", None)
        report["run_receipt"] = _terminal_receipt(permission, StopOutcome.INVALID, str(error))
        return report


def exact_candidate_policy(messages: list[dict[str, Any]]) -> str:
    """A programmatic reference that reads only the declared model-facing memory."""
    payload = json.loads(messages[0]["content"][0]["text"])
    return json.dumps(
        {
            "source_state_id": payload["current"]["state_id"],
            "action": payload["search_memory"]["successor_candidates"][0]["action"],
        }
    )


def replay_matched_modality_episode(report: Mapping[str, Any]) -> dict[str, Any]:
    """Replay ordered observations and operations offline; no rendering or policy calls."""
    if report.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported matched episode schema")
    header = report["header"]
    request = header["request"]
    binding = ReceiptBinding(**request["binding"])
    gate_payload = header["gate_receipt"]
    gate = GateReceipt(
        ReceiptBinding(**gate_payload["binding"]),
        StopOutcome(gate_payload["outcome"]),
        gate_payload["ancestor_receipt_id"],
    )
    authorization = header["authorization_receipt"]
    permission = evaluate_execution_permission(
        binding=binding,
        gate_receipt=gate,
        authorization_receipt=(
            AuthorizationReceipt(ReceiptBinding(**authorization["binding"]), authorization["gate_receipt_id"])
            if authorization
            else None
        ),
    )
    if not permission.start_permitted or not report["execution_started"]:
        raise ValueError("matched replay requires authorized execution evidence")
    episodes = report["episodes"]
    if [episode["modality"] for episode in episodes] != list(MODALITIES):
        raise ValueError("matched replay requires all three modality episodes")
    if len({len(episode["events"]) for episode in episodes}) != 1:
        raise ValueError("modality operation counts are not aligned")
    limits = _limits(request["limits"])
    frames = _replay_paths(header["domain_pddl"], header["problem_pddl"], request["supplied_paths"])
    bindings = header["frame_bindings"]
    if [(list(state.atoms), list(state.fluents)) for state in frames] != [
        (row["atoms"], row["fluents"]) for row in bindings
    ]:
        raise ValueError("frame binding states differ from PDDL replay")
    results = []
    for episode in episodes:
        controller = _controller(
            header["domain_pddl"], header["problem_pddl"], request["algorithm"], request["max_expansions"], limits
        )
        for index, event in enumerate(episode["events"]):
            if event["index"] != index or _advance(controller, request["max_decisions"]) is not None:
                raise ValueError("recorded operation is outside its episode position or budget")
            observations = tuple(_observation_from_record(other["events"][index]["observation"]) for other in episodes)
            if any(item.limits != limits for item in observations):
                raise ValueError("observation differs from the frozen input contract")
            for item in observations:
                if not 0 < item.input_tokens <= limits.max_input_tokens:
                    raise ValueError("recorded input exceeds the frozen token budget")
                if item.input_size_bin != next(bound for bound in limits.input_size_bins if item.input_tokens <= bound):
                    raise ValueError("recorded token size bin differs from the frozen bins")
            validate_modality_parity(observations, controller=controller)
            state = controller.node_state(controller.active_state_id or "")
            state_index = frames.index(state)
            source_frame = Path(bindings[state_index]["frame"])
            for item in observations[1:]:
                if item.images[0].source_frame != source_frame or item.images[1].source_frame is not None:
                    raise ValueError("observation frame is bound to a different replay state or partial goal")
                image_root = Path("observations") / item.modality
                if (
                    item.images[0].path != image_root / f"state-{state_index:06d}.png"
                    or item.images[1].path != image_root / "goal.png"
                ):
                    raise ValueError("model-facing image path differs from the state-frame binding")
            runtime = controller.apply_raw_output(event["raw_output"])
            if dict(runtime.runtime_result) != event["runtime"]:
                raise ValueError("recorded runtime result differs from semantic replay")
            if any(
                _operation(other["events"][index]["raw_output"]) != _operation(event["raw_output"]) for other in episodes
            ):
                raise ValueError("modality operations are not aligned")
        termination = _advance(controller, request["max_decisions"])
        if termination is None:
            raise ValueError("episode evidence stops before its terminal result")
        result = _result(controller, termination)
        if result != episode["result"]:
            raise ValueError("episode result differs from semantic replay")
        results.append({"result": result})
    outcome = _outcome(results)
    if report["outcome"] != outcome.value or report["scientific_completion"] != (outcome is StopOutcome.PASS):
        raise ValueError("completion claim differs from replayed outcome")
    return {"outcome": outcome.value, "replayed_episodes": 3, "aligned_decisions": len(episodes[0]["events"])}


def _controller(
    domain: str, problem: str, algorithm: str, budget: int, limits: ModalityInputLimits
) -> BestFirstController:
    return BestFirstController(
        PDDLStateAuthority.from_pddl(domain, problem),
        BEST_FIRST_SETTINGS[algorithm],
        max_budget=budget,
        accepted_delta_limit=limits.accepted_delta_limit,
    )


def _advance(controller: BestFirstController, max_decisions: int) -> str | None:
    while True:
        if controller.active_state_id is not None:
            if controller.current_candidates():
                if controller.budget_exhausted or controller.decision_count >= max_decisions:
                    return "budget_exhausted"
                return None
            controller.finish_expansion()
        head = controller.frontier_head_state_id()
        if head is None:
            return "frontier_exhausted"
        if controller.authority.is_goal(controller.node_state(head)):
            return "goal_reached"
        if controller.budget_exhausted or controller.decision_count >= max_decisions:
            return "budget_exhausted"
        controller.start_expansion()


def _result(controller: BestFirstController, termination: str) -> dict[str, Any]:
    return {
        "termination": termination,
        "goal_reached": termination == "goal_reached",
        "expansions": controller.expansion_count,
        "decisions": controller.decision_count,
        "budget_used": controller.budget_used,
        "invalid_operations": controller.invalid_operation_count,
    }


def _outcome(episodes: list[dict[str, Any]]) -> StopOutcome:
    if any(episode["result"]["invalid_operations"] for episode in episodes):
        return StopOutcome.INVALID
    return StopOutcome.PASS if all(episode["result"]["goal_reached"] for episode in episodes) else StopOutcome.VALID_STOP


def _terminal_receipt(permission: RunReceipt, outcome: StopOutcome, reason: str | None) -> dict[str, object]:
    return RunReceipt(
        permission.binding,
        outcome,
        (
            "completed"
            if outcome is StopOutcome.PASS
            else ("invalid-not-run" if outcome is StopOutcome.INVALID else "gated-not-run")
        ),
        False,
        outcome is StopOutcome.PASS,
        permission.gate_receipt_id,
        permission.authorization_receipt_id,
        reason=reason,
    ).to_dict()


def _limits(value: Mapping[str, Any]) -> ModalityInputLimits:
    return ModalityInputLimits(**{**value, "input_size_bins": tuple(value["input_size_bins"])})


def _observation_record(observation: ModalityObservation, root: Path) -> dict[str, Any]:
    payload = asdict(observation)
    for image in payload["images"]:
        image["path"] = str(image["path"].relative_to(root))
        image["source_frame"] = str(image["source_frame"].relative_to(root)) if image["source_frame"] else None
    return json.loads(json.dumps(payload))


def _observation_from_record(record: Mapping[str, Any]) -> ModalityObservation:
    return ModalityObservation(
        record["modality"],
        record["prompt"],
        tuple(
            RelationImage(
                Path(image["path"]),
                tuple((section, predicate, tuple(args)) for section, predicate, args in image["relations"]),
                Path(image["source_frame"]) if image["source_frame"] else None,
            )
            for image in record["images"]
        ),
        record["input_tokens"],
        record["input_size_bin"],
        _limits(record["limits"]),
    )


def _replay_paths(domain: str, problem: str, paths: Any) -> list[Any]:
    from .planimation_render import canonical_supplied_actions

    authority = PDDLStateAuthority.from_pddl(domain, problem)
    states = []
    for path in sorted({canonical_supplied_actions(tuple(path)) for path in paths}, key=lambda path: (len(path), path)):
        state = authority.initial_state
        states.append(state)
        for action in path:
            parts = action[1:-1].split()
            state = authority.apply(state, GroundedAction(parts[0], tuple(parts[1:]))).target_state
            states.append(state)
    if not states:
        raise ValueError("at least one supplied path is required")
    return states


def _operation(raw: str) -> Any:
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def _progress(callback: Progress | None, stage: str, **fields: Any) -> None:
    if callback:
        callback({"stage": stage, **fields})


def _stopped(receipt: RunReceipt) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "outcome": receipt.outcome.value,
        "reason": receipt.reason,
        "scientific_completion": False,
        "episodes": [],
        "permission": receipt.to_dict(),
        "execution_started": False,
    }
    if receipt.outcome in (StopOutcome.VALID_STOP, StopOutcome.ANCESTOR_STOP):
        report["gated_not_run_receipt"] = receipt.to_dict()
    return report
