"""Resumable held-out evaluation of generated versus trusted BFS successors."""

from __future__ import annotations

import copy
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .expanded_dagger_evaluation import _task_name
from .expanded_successor import (
    accept_verified_prediction,
    prediction_target,
    project_successor_example,
    replay_source_path,
    state_payload,
    static_context_id,
    verify_prediction,
)
from .expanded_views import ExpandedTaskViews
from .modality_corpus_replay import canonical
from .modality_view_preparation import frozen_processor, write_json
from .pddl_state import GroundedAction
from .scene_assets import read_json
from .visual_episode import VisualSession, VisualTaskViews

SCHEMA_VERSION = "expanded_successor_evaluation_v1"
EPISODE_SCHEMA = "expanded_successor_evaluation_episode_v1"
JOURNAL_SCHEMA = "expanded_successor_evaluation_journal_v1"
ARMS = ("model_generated_successor", "trusted_successor")
_CUTOFF = object()
CHECK_NAMES = (
    "schema",
    "static_context",
    "source_identity",
    "action_identity",
    "applicability",
    "state_identity",
    "effect",
)


def panels(root: Path, protocol: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Load the three development tasks and the frozen 12-task fallback panel."""

    development = read_json(root / protocol["evaluation"]["development_panel"])
    unseen_panel = read_json(root / protocol["evaluation"]["unseen_panel"])
    unseen_views = read_json(root / unseen_panel["view_report"])
    selected = set(protocol["qualification"]["coverage_admission"]["fallback_unseen_task_ids"])
    unseen = [task for task in unseen_views["tasks"] if task["row"]["task_id"] in selected]
    if (
        development.get("outcome") != "PASS"
        or len(development.get("tasks", [])) != 3
        or unseen_panel.get("panel_id") != "expanded-panel-v2-qualified"
        or len(selected) != 12
        or {task["row"]["task_id"] for task in unseen} != selected
    ):
        raise ValueError("successor evaluation panels differ from the frozen fallback contract")
    return {"development": development["tasks"], "unseen": unseen}


def exact_reference_counts(loaded: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    by_panel = {
        panel: {
            task["row"]["task_id"]: task["row"]["reference_costs"]["bfs"]["decisions"]
            for task in tasks
        }
        for panel, tasks in loaded.items()
    }
    total = sum(sum(rows.values()) for rows in by_panel.values())
    return {
        "source": "frozen panel row.reference_costs.bfs.decisions",
        "by_panel": by_panel,
        "per_modality_exact_reference_decisions": total,
        "model_call_allowance": 2 * total * 3,
    }


def evaluation_root(
    root: Path,
    protocol: Mapping[str, Any],
    panel: str,
    modality: str,
    task_id: str,
) -> Path:
    return root / protocol["output_root"] / "evaluation" / "episodes" / panel / modality / _task_name(task_id)


def episode_path(
    root: Path,
    protocol: Mapping[str, Any],
    panel: str,
    modality: str,
    task_id: str,
    arm: str,
) -> Path:
    return evaluation_root(root, protocol, panel, modality, task_id) / f"{arm}.json.gz"


def _views(root, protocol, panel, task, output, endpoint, *, read_only=False):
    if panel == "development":
        scene_views = task.get("study", {}).get("scene_views")
        return VisualTaskViews(
            root,
            task["row"],
            task["view_manifest"],
            output,
            endpoint,
            read_only=read_only,
            scene_views=scene_views,
        )
    return ExpandedTaskViews(root, task, output, endpoint, read_only=read_only)


def _identity(root, protocol, panel, modality, task, arm, output, view_output):
    try:
        checkpoint_sha256 = protocol["_successor_checkpoint_sha256"][modality]
        adapter_config_sha256 = protocol["_successor_adapter_config_sha256"][modality]
        trained_checkpoint = protocol["_successor_checkpoints"][modality]
        policy_identity = copy.deepcopy(protocol["_successor_policy_identity"][modality])
        producing_attempt = copy.deepcopy(protocol["_producing_attempt"])
        runtime_head = protocol["_runtime_head"]
    except KeyError as error:
        raise ValueError("successor episode identity lacks verified runtime provenance") from error
    checkpoint = (
        trained_checkpoint
        if arm == "model_generated_successor"
        else None
    )
    return {
        "schema_version": EPISODE_SCHEMA,
        "protocol_id": protocol["protocol_id"],
        "panel": panel,
        "task_id": task["row"]["task_id"],
        "modality": modality,
        "algorithm": "bfs",
        "arm": arm,
        "seed": protocol["evaluation"]["seed"],
        "output": str(output.relative_to(root)),
        "view_output": None if view_output is None else str(view_output.relative_to(root)),
        "checkpoint": checkpoint,
        "final_checkpoint_sha256": checkpoint_sha256,
        "final_adapter_config_sha256": adapter_config_sha256,
        "producing_attempt": producing_attempt,
        "policy_identity": policy_identity,
        "decoding": protocol["model"]["decoding"],
        "runtime_head": runtime_head,
        "model_id": protocol["model"]["id"],
        "model_revision": protocol["model"]["revision"],
        "reference_decisions": task["row"]["reference_costs"]["bfs"]["decisions"],
        "model_call_limit": 2 * task["row"]["reference_costs"]["bfs"]["decisions"],
    }


def _validate_producing_identity(protocol, report):
    producing = report.get("producing_attempt")
    if not isinstance(producing, dict) or set(producing) != {"job_id", "attempt", "directory"}:
        raise ValueError("successor episode lacks a scheduler producing attempt")
    key = (producing["job_id"], producing["attempt"], producing["directory"])
    status = protocol.get("_valid_producing_attempts", {}).get(key)
    if status not in {"succeeded", "failed", "cutoff", "interrupted"}:
        raise ValueError("successor episode producing attempt is unknown or non-terminal")
    modality = report.get("modality")
    worker_result_path = Path(producing["directory"]) / "worker-result.json"
    worker_result = read_json(worker_result_path) if worker_result_path.is_file() else None
    if worker_result is not None and worker_result.get("producing_attempt") != producing:
        raise ValueError("successor episode differs from its producing worker receipt")
    expected_policy = (
        worker_result.get("policy_identities", {}).get(modality)
        if worker_result is not None
        else protocol.get("_successor_policy_identity", {}).get(modality)
    )
    expected_runtime_head = (
        worker_result.get("runtime_head")
        if worker_result is not None
        else protocol.get("_runtime_head")
    )
    if (
        report.get("policy_identity") != expected_policy
        or report.get("decoding") != protocol["model"]["decoding"]
        or report.get("runtime_head") != expected_runtime_head
    ):
        raise ValueError("successor episode loaded-policy or runtime identity differs")
    return producing


def _operation(reference_output: str) -> dict[str, Any]:
    parsed = json.loads(reference_output)
    operation = parsed.get("typed_operation", parsed)
    if not isinstance(operation, dict):
        raise ValueError("canonical BFS reference output has no typed operation")
    return operation


def _action(operation: Mapping[str, Any]) -> dict[str, Any] | None:
    action = operation.get("action")
    if action is None:
        return None
    if (
        not isinstance(action, Mapping)
        or not isinstance(action.get("name"), str)
        or not isinstance(action.get("args"), list)
    ):
        raise ValueError("canonical BFS reference action is malformed")
    return {"name": action["name"], "args": list(action["args"])}


def successor_request(
    authority,
    source_state,
    source_path: Sequence[Mapping[str, Any]],
    bfs_input: Mapping[str, Any],
    action: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the same leak-free successor query/target contract used in collection."""

    model_input = copy.deepcopy(dict(bfs_input))
    for candidate in model_input["search_memory"]["successor_candidates"]:
        candidate.pop("target_state_id", None)
        candidate.pop("target_state", None)
        candidate.pop("evaluation", None)
    query = {
        "source_state_id": source_state.state_id,
        "action": {"name": action["name"], "args": list(action["args"])},
        "static_context_id": static_context_id(authority.task_context()),
    }
    model_input["successor_prediction_query"] = copy.deepcopy(query)
    grounded = GroundedAction(action["name"], tuple(action["args"]))
    transition = authority.preview_apply(source_state, grounded)
    return {
        "model_input": model_input,
        "query": query,
        "source_state": state_payload(source_state),
        "source_path": copy.deepcopy(list(source_path)),
        "trusted_target": prediction_target(authority.task_context(), transition),
        "target_state_id": transition.target_state.state_id,
    }


def project_request(
    views,
    bfs_input: Mapping[str, Any],
    request: Mapping[str, Any],
    modality: str,
    *,
    pixels: bool,
    token_counter: Callable[[Sequence[Mapping[str, Any]], Sequence[Any]], int] | None = None,
) -> dict[str, Any]:
    """Reuse the collection projection, changing only the held-out live view."""

    example = views.observe(dict(bfs_input), "bfs", modality=modality, pixels=pixels)
    example["messages"].append({"role": "assistant", "content": canonical(request["trusted_target"])})
    projected = project_successor_example(example, {"query": request["query"], "target": request["trusted_target"]})
    projected["messages"] = projected["messages"][:-1]
    if token_counter is not None:
        input_tokens = token_counter(projected["messages"], projected["images"])
    else:
        image_sizes = projected.get("image_sizes")
        input_tokens = frozen_processor().count(projected["messages"], image_sizes=image_sizes)
    projected["binding"]["input_tokens"] = input_tokens
    return projected


def _result(state: dict[str, Any]) -> dict[str, Any]:
    session_result = state["session"].result()
    reason = state.get("forced_termination") or session_result["termination_reason"]
    invalid = int(reason == "invalid_successor")
    normal = state.get("forced_termination") is None
    goal = bool(session_result["goal_reached"]) if normal else False
    success = bool(session_result["invariant_valid_success"]) if normal else False
    return {
        **session_result,
        "invariant_valid_success": success,
        "goal_reached": goal,
        "algorithm_invariants_hold": bool(session_result["algorithm_invariants_hold"]) and not invalid,
        "decision_count": len(state["saved"]["events"]),
        "invalid_operation_count": invalid,
        "invalid_operation_rate": invalid / max(1, len(state["saved"]["events"])),
        "model_calls": len(state["saved"]["call_measurements"]),
        "model_call_limit": state["identity"]["model_call_limit"],
        "invalid_successor_count": invalid,
        "termination_reason": reason,
        "downstream_search_status": "success" if success else "failure",
    }


def _finalize(state: dict[str, Any]) -> dict[str, Any]:
    result = _result(state)
    downstream = {
        "status": result["downstream_search_status"],
        "failure": None if result["invariant_valid_success"] else result["termination_reason"],
    }
    events = copy.deepcopy(state["saved"]["events"])
    for event in events:
        if event.get("verification") is not None:
            event["verification"]["downstream_search"] = copy.deepcopy(downstream)
    report = {
        **state["identity"],
        "outcome": "RECORDED",
        "events": events,
        "result": result,
        "call_measurements": copy.deepcopy(state["saved"]["call_measurements"]),
        "canonical_action_sequence": [event["action"] for event in events if event.get("action")],
        "canonical_operation_sequence": [event["reference_output"] for event in events],
        "raw_predictions_retained": sum(event.get("raw_prediction") is not None for event in events),
        "trusted_state_substitutions": sum(
            bool(event.get("verification", {}).get("trusted_state_substituted"))
            for event in events
            if event.get("verification") is not None
        ),
        "started": state["saved"]["started"],
        "finished": time.time(),
        "active_wall_seconds": state["saved"]["active_wall_seconds"],
    }
    if state["views"] is not None:
        state["views"].save()
    write_json(state["episode"], report)
    state["journal"].unlink(missing_ok=True)
    return report


def _write_journal(state: Mapping[str, Any]) -> None:
    write_json(state["journal"], state["saved"])


def _record_retirement(state, bfs_input, reference_output):
    state["session"].submit(reference_output, None)
    state["saved"]["events"].append(
        {
            "index": len(state["saved"]["events"]),
            "kind": "retirement",
            "bfs_input": copy.deepcopy(dict(bfs_input)),
            "reference_output": reference_output,
            "action": None,
            "model_input": None,
            "query": None,
            "source_state": None,
            "source_path": None,
            "trusted_target": None,
            "raw_prediction": None,
            "verification": None,
            "view": None,
            "accepted": True,
        }
    )


def _commit_successor(state, pending):
    request = pending["request"]
    action = request["query"]["action"]
    verification = None
    accepted = True
    if state["identity"]["arm"] == "model_generated_successor":
        target, verification = accept_verified_prediction(
            state["session"].authority,
            state["source_state"],
            request["query"],
            pending["raw_prediction"],
        )
        accepted = target is not None
        if target is not None and target.state_id != request["target_state_id"]:
            raise AssertionError("accepted generated successor differs from the canonical transition")
    if accepted:
        state["session"].submit(pending["reference_output"], pending.get("view"))
        state["paths"][request["target_state_id"]] = [*request["source_path"], action]
    else:
        state["forced_termination"] = "invalid_successor"
    event = {
        "index": len(state["saved"]["events"]),
        "kind": "successor",
        "bfs_input": pending["bfs_input"],
        "reference_output": pending["reference_output"],
        "action": copy.deepcopy(action),
        "model_input": copy.deepcopy(request["model_input"]),
        "query": copy.deepcopy(request["query"]),
        "source_state": copy.deepcopy(request["source_state"]),
        "source_path": copy.deepcopy(request["source_path"]),
        "trusted_target": copy.deepcopy(request["trusted_target"]),
        "raw_prediction": pending.get("raw_prediction"),
        "verification": verification,
        "view": copy.deepcopy(pending.get("view")),
        "accepted": accepted,
    }
    state["saved"]["events"].append(event)
    if pending.get("measurement") is not None:
        state["saved"]["call_measurements"].append(copy.deepcopy(pending["measurement"]))
    state["saved"]["pending"] = None
    if state["views"] is not None:
        state["views"].save()
    _write_journal(state)


def _restore(state):
    saved_events = copy.deepcopy(state["saved"]["events"])
    saved_calls = copy.deepcopy(state["saved"]["call_measurements"])
    pending = copy.deepcopy(state["saved"].get("pending"))
    state["saved"]["events"] = []
    state["saved"]["call_measurements"] = []
    state["saved"]["pending"] = None
    for expected in saved_events:
        request = state["session"].next_request()
        if request is None or dict(request.model_input) != expected["bfs_input"]:
            raise ValueError("successor evaluation journal BFS order differs on resume")
        if expected["kind"] == "retirement":
            _record_retirement(state, expected["bfs_input"], expected["reference_output"])
        else:
            source_path = expected["source_path"]
            source = replay_source_path(state["session"].authority, source_path)
            state["source_state"] = source
            rebuilt = successor_request(
                state["session"].authority,
                source,
                source_path,
                expected["bfs_input"],
                expected["action"],
            )
            state["saved"]["pending"] = {
                "bfs_input": expected["bfs_input"],
                "reference_output": expected["reference_output"],
                "request": rebuilt,
                "raw_prediction": expected["raw_prediction"],
                "view": expected["view"],
                "measurement": (
                    saved_calls[len(state["saved"]["call_measurements"])]
                    if expected["raw_prediction"] is not None
                    else None
                ),
            }
            _commit_successor(state, state["saved"]["pending"])
        if state.get("forced_termination"):
            break
    if state["saved"]["events"] != saved_events or state["saved"]["call_measurements"] != saved_calls:
        raise ValueError("successor evaluation journal changes on deterministic resume")
    state["saved"]["pending"] = pending
    if pending is not None:
        state["source_state"] = replay_source_path(
            state["session"].authority, pending["request"]["source_path"]
        )
        _commit_successor(state, pending)


def _initialize(
    root,
    protocol,
    panel,
    modality,
    task,
    arm,
    endpoint,
    *,
    session_factory=None,
    views_factory=None,
):
    output = episode_path(root, protocol, panel, modality, task["row"]["task_id"], arm)
    journal = output.with_name(output.name.removesuffix(".json.gz") + ".partial.json.gz")
    view_output = output.parent / f"{arm}-views" if arm == "model_generated_successor" else None
    identity = _identity(root, protocol, panel, modality, task, arm, output, view_output)
    factory = views_factory or _views
    views = (
        factory(root, protocol, panel, task, view_output, endpoint, read_only=False)
        if view_output is not None
        else None
    )
    session_cls = session_factory or VisualSession
    session = session_cls(
        root,
        task["row"],
        "bfs",
        "exact_reference",
        protocol["evaluation"]["seed"],
        output,
        protocol["protocol_id"],
        views=views,
    )
    if journal.exists():
        saved = read_json(journal)
        prior_attempt = _validate_producing_identity(protocol, saved)
        prior_protocol = dict(protocol)
        prior_protocol["_producing_attempt"] = prior_attempt
        prior_protocol["_runtime_head"] = saved["runtime_head"]
        prior_identity = _identity(
            root, prior_protocol, panel, modality, task, arm, output, view_output
        )
        if any(saved.get(key) != value for key, value in prior_identity.items()):
            raise ValueError("successor evaluation journal identity differs")
        saved.update(copy.deepcopy(identity))
    else:
        saved = {
            "schema_version": JOURNAL_SCHEMA,
            **identity,
            "events": [],
            "call_measurements": [],
            "pending": None,
            "started": time.time(),
            "active_wall_seconds": 0.0,
        }
    if any(saved.get(key) != value for key, value in identity.items()) or saved.get("schema_version") not in {
        JOURNAL_SCHEMA,
        EPISODE_SCHEMA,
    }:
        raise ValueError("successor evaluation journal identity differs")
    state = {
        "episode": output,
        "journal": journal,
        "identity": identity,
        "task": task,
        "views": views,
        "session": session,
        "saved": saved,
        "paths": {session.authority.initial_state.state_id: []},
        "source_state": None,
        "forced_termination": None,
    }
    _restore(state)
    _write_journal(state)
    return state


def _advance(
    state,
    modality,
    token_counter=None,
    *,
    cutoff_timestamp: float | None = None,
    clock: Callable[[], float] = time.time,
):
    while state.get("forced_termination") is None:
        if cutoff_timestamp is not None and clock() >= cutoff_timestamp:
            return _CUTOFF
        request = state["session"].next_request()
        if request is None:
            return None
        bfs_input = dict(request.model_input)
        reference_output = state["session"].reference_output()
        operation = _operation(reference_output)
        action = _action(operation)
        if action is None:
            _record_retirement(state, bfs_input, reference_output)
            _write_journal(state)
            continue
        if (
            state["identity"]["arm"] == "model_generated_successor"
            and len(state["saved"]["call_measurements"]) >= state["identity"]["model_call_limit"]
        ):
            state["forced_termination"] = "model_call_limit_exhausted"
            _write_journal(state)
            return None
        source_id = bfs_input["observation"]["state_id"]
        if source_id not in state["paths"]:
            raise ValueError("canonical BFS requested a state without accepted producing-path provenance")
        source_path = state["paths"][source_id]
        source = replay_source_path(state["session"].authority, source_path)
        if source.state_id != source_id:
            raise ValueError("successor producing path differs from the active BFS source")
        state["source_state"] = source
        successor = successor_request(
            state["session"].authority, source, source_path, bfs_input, action
        )
        if state["identity"]["arm"] == "trusted_successor":
            state["saved"]["pending"] = {
                "bfs_input": copy.deepcopy(bfs_input),
                "reference_output": reference_output,
                "request": successor,
                "raw_prediction": None,
                "view": None,
                "measurement": None,
            }
            _commit_successor(state, state["saved"]["pending"])
            continue
        example = project_request(
            state["views"],
            bfs_input,
            successor,
            modality,
            pixels=True,
            token_counter=token_counter,
        )
        return {
            "state": state,
            "example": example,
            "bfs_input": copy.deepcopy(bfs_input),
            "reference_output": reference_output,
            "request": successor,
        }
    return None


def run_cell(
    root: Path,
    protocol: Mapping[str, Any],
    *,
    panel: str,
    modality: str,
    arm: str,
    tasks: list[dict[str, Any]],
    endpoint: str,
    generate,
    progress,
    cutoff_timestamp: float | None = None,
    session_factory=None,
    views_factory=None,
    token_counter=None,
    clock: Callable[[], float] = time.time,
) -> list[dict[str, Any]]:
    """Run one modality/arm cell in resumable task pairs."""

    if arm not in ARMS:
        raise ValueError("successor evaluation arm is outside the frozen comparison")
    reports = []
    pending_tasks = []
    for task in tasks:
        path = episode_path(root, protocol, panel, modality, task["row"]["task_id"], arm)
        if path.exists():
            reports.append(
                verify_episode(
                    root,
                    protocol,
                    panel,
                    modality,
                    task,
                    arm,
                    endpoint,
                    session_factory=session_factory,
                    views_factory=views_factory,
                    token_counter=token_counter,
                )
            )
            progress(completed=len(reports), total=len(tasks), task_id=task["row"]["task_id"], retained=True)
        else:
            pending_tasks.append(task)
    for start in range(0, len(pending_tasks), 2):
        if cutoff_timestamp is not None and clock() >= cutoff_timestamp:
            break
        active = [
            _initialize(
                root,
                protocol,
                panel,
                modality,
                task,
                arm,
                endpoint,
                session_factory=session_factory,
                views_factory=views_factory,
            )
            for task in pending_tasks[start : start + 2]
        ]
        while active:
            prepared = []
            remaining = []
            cutoff_reached = False
            for state in active:
                if cutoff_timestamp is not None and clock() >= cutoff_timestamp:
                    cutoff_reached = True
                    break
                begun = time.monotonic()
                item = _advance(
                    state,
                    modality,
                    token_counter=token_counter,
                    cutoff_timestamp=cutoff_timestamp,
                    clock=clock,
                )
                state["saved"]["active_wall_seconds"] += time.monotonic() - begun
                if item is _CUTOFF:
                    cutoff_reached = True
                    break
                if item is None:
                    report = _finalize(state)
                    reports.append(report)
                    progress(
                        completed=len(reports),
                        total=len(tasks),
                        task_id=state["identity"]["task_id"],
                        retained=False,
                    )
                else:
                    prepared.append(item)
                    remaining.append(state)
            if cutoff_reached:
                for item in prepared:
                    for image in item["example"]["images"]:
                        close = getattr(image, "close", None)
                        if close is not None:
                            close()
                return sorted(
                    reports,
                    key=lambda report: next(
                        index
                        for index, task in enumerate(tasks)
                        if task["row"]["task_id"] == report["task_id"]
                    ),
                )
            active = remaining
            if not prepared:
                continue
            if generate is None:
                raise ValueError("model-generated successor arm requires a generator")
            examples = [item["example"] for item in prepared]
            if cutoff_timestamp is not None and clock() >= cutoff_timestamp:
                for example in examples:
                    for image in example["images"]:
                        close = getattr(image, "close", None)
                        if close is not None:
                            close()
                return sorted(
                    reports,
                    key=lambda report: next(
                        index
                        for index, task in enumerate(tasks)
                        if task["row"]["task_id"] == report["task_id"]
                    ),
                )
            called = time.monotonic()
            try:
                outputs, usage = generate(examples)
            finally:
                for example in examples:
                    for image in example["images"]:
                        close = getattr(image, "close", None)
                        if close is not None:
                            close()
            elapsed = time.monotonic() - called
            if len(outputs) != len(prepared):
                raise ValueError("successor evaluation generator returned incomplete output")
            input_tokens = usage.get("input_tokens", [e["binding"]["input_tokens"] for e in examples])
            generated = usage.get("generated_sequence_tokens")
            generated_tokens = generated if isinstance(generated, list) else [generated] * len(prepared)
            if len(input_tokens) != len(prepared) or len(generated_tokens) != len(prepared):
                raise ValueError("successor evaluation generator usage is incomplete")
            maximum_input = protocol.get("model", {}).get("maximum_input_tokens")
            maximum_output = protocol.get("model", {}).get("output_tokens")
            if any(
                not isinstance(value, int)
                or value <= 0
                or (maximum_input is not None and value > maximum_input)
                for value in input_tokens
            ) or any(
                not isinstance(value, int)
                or value <= 0
                or (maximum_output is not None and value > maximum_output)
                for value in generated_tokens
            ):
                raise ValueError("successor evaluation generator usage exceeds frozen allowances")
            for item, raw, in_tokens, out_tokens in zip(
                prepared, outputs, input_tokens, generated_tokens, strict=True
            ):
                state = item["state"]
                measurement = {
                    "event_index": len(state["saved"]["events"]),
                    "model_call": True,
                    "input_tokens": in_tokens,
                    "generated_sequence_tokens": out_tokens,
                    "call_wall_seconds": elapsed / len(prepared),
                    "batch_size": len(prepared),
                }
                state["saved"]["pending"] = {
                    "bfs_input": item["bfs_input"],
                    "reference_output": item["reference_output"],
                    "request": item["request"],
                    "raw_prediction": raw,
                    "view": copy.deepcopy(item["example"]["binding"]),
                    "measurement": measurement,
                }
                state["saved"]["active_wall_seconds"] += elapsed / len(prepared)
                _write_journal(state)
            for item in prepared:
                _commit_successor(item["state"], item["state"]["saved"]["pending"])
    order = {task["row"]["task_id"]: index for index, task in enumerate(tasks)}
    return sorted(reports, key=lambda report: order[report["task_id"]])


def _expected_verification(authority, source, query, raw_prediction, downstream):
    verification = verify_prediction(authority, source, query, raw_prediction)
    verification["prediction_applied"] = verification["status"] == "accepted"
    verification["downstream_search"] = copy.deepcopy(downstream)
    return verification


def verify_episode(
    root,
    protocol,
    panel,
    modality,
    task,
    arm,
    endpoint,
    *,
    session_factory=None,
    views_factory=None,
    token_counter=None,
):
    """Independently replay one retained episode with fresh runtime state."""

    path = episode_path(root, protocol, panel, modality, task["row"]["task_id"], arm)
    report = read_json(path)
    producing_attempt = _validate_producing_identity(protocol, report)
    identity_protocol = dict(protocol)
    identity_protocol["_producing_attempt"] = producing_attempt
    identity_protocol["_runtime_head"] = report["runtime_head"]
    view_output = None if report.get("view_output") is None else root / report["view_output"]
    expected_identity = _identity(
        root, identity_protocol, panel, modality, task, arm, path, view_output
    )
    if any(report.get(key) != value for key, value in expected_identity.items()):
        raise ValueError("successor evaluation episode identity differs")
    factory = views_factory or _views
    views = (
        factory(root, protocol, panel, task, view_output, endpoint, read_only=True)
        if view_output is not None
        else None
    )
    session_cls = session_factory or VisualSession
    session = session_cls(
        root,
        task["row"],
        "bfs",
        "exact_reference",
        protocol["evaluation"]["seed"],
        path,
        protocol["protocol_id"],
        views=views,
    )
    paths = {session.authority.initial_state.state_id: []}
    calls = 0
    forced = None
    downstream = {
        "status": report["result"]["downstream_search_status"],
        "failure": (
            None
            if report["result"]["invariant_valid_success"]
            else report["result"]["termination_reason"]
        ),
    }
    for index, event in enumerate(report["events"]):
        request = session.next_request()
        if request is None or dict(request.model_input) != event["bfs_input"]:
            raise ValueError("successor evaluation canonical BFS input/order differs on replay")
        reference_output = session.reference_output()
        if reference_output != event["reference_output"]:
            raise ValueError("successor evaluation canonical action order differs on replay")
        action = _action(_operation(reference_output))
        if action is None:
            if event["kind"] != "retirement" or event["action"] is not None:
                raise ValueError("successor evaluation retirement record differs")
            session.submit(reference_output, None)
            continue
        source_id = event["bfs_input"]["observation"]["state_id"]
        source_path = paths.get(source_id)
        if source_path is None or source_path != event["source_path"]:
            raise ValueError("successor evaluation source producing path differs on replay")
        source = replay_source_path(session.authority, source_path)
        expected_request = successor_request(
            session.authority, source, source_path, event["bfs_input"], action
        )
        for key, retained_key in (
            ("model_input", "model_input"),
            ("query", "query"),
            ("source_state", "source_state"),
            ("source_path", "source_path"),
            ("trusted_target", "trusted_target"),
        ):
            if expected_request[key] != event[retained_key]:
                raise ValueError(f"successor evaluation retained {retained_key} differs on replay")
        if arm == "model_generated_successor":
            calls += 1
            actual = _expected_verification(
                session.authority, source, event["query"], event["raw_prediction"], downstream
            )
            if actual != event["verification"] or event["accepted"] != (actual["status"] == "accepted"):
                raise ValueError("successor prediction verification/classification differs on replay")
            if actual["status"] != "accepted":
                forced = "invalid_successor"
                if index != len(report["events"]) - 1:
                    raise ValueError("rejected successor did not terminate its episode")
                break
            projected = project_request(
                views,
                event["bfs_input"],
                expected_request,
                modality,
                pixels=False,
                token_counter=token_counter,
            )
            try:
                if projected["binding"] != event["view"]:
                    raise ValueError("successor evaluation view binding differs on replay")
            finally:
                for image in projected["images"]:
                    close = getattr(image, "close", None)
                    if close is not None:
                        close()
        elif event["raw_prediction"] is not None or event["verification"] is not None:
            raise ValueError("trusted successor arm retained a model prediction")
        session.submit(reference_output, event["view"])
        paths[expected_request["target_state_id"]] = [*source_path, action]
    if calls != len(report["call_measurements"]) or calls > report["result"]["model_call_limit"]:
        raise ValueError("successor evaluation model-call accounting differs")
    if report["result"]["termination_reason"] == "model_call_limit_exhausted":
        forced = "model_call_limit_exhausted"
    if forced is None and session.next_request() is not None:
        raise ValueError("successor evaluation recorded events are incomplete")
    state = {
        "session": session,
        "identity": expected_identity,
        "saved": {"events": report["events"], "call_measurements": report["call_measurements"]},
        "forced_termination": forced,
    }
    if _result(state) != report["result"]:
        raise ValueError("successor evaluation downstream search outcome differs on replay")
    if report["trusted_state_substitutions"] != 0:
        raise ValueError("successor evaluation contains a forbidden trusted-state substitution")
    return report


def expected_bindings(protocol, loaded):
    return [
        {
            "panel": panel,
            "modality": modality,
            "task_id": task["row"]["task_id"],
            "arm": arm,
        }
        for panel, tasks in loaded.items()
        for modality in protocol["modalities"]
        for task in tasks
        for arm in ARMS
    ]


def summarize(reports, expected=None):
    expected = expected or [
        {
            "panel": row["panel"],
            "modality": row["modality"],
            "task_id": row["task_id"],
            "arm": row["arm"],
        }
        for row in reports
    ]
    grouped_expected = Counter((r["panel"], r["modality"], r["arm"]) for r in expected)
    grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = {}
    for report in reports:
        grouped.setdefault((report["panel"], report["modality"], report["arm"]), []).append(report)
    cells = []
    for key, expected_count in sorted(grouped_expected.items()):
        rows = grouped.get(key, [])
        failures = Counter()
        checks = {name: Counter() for name in CHECK_NAMES}
        calls = 0
        call_seconds = 0.0
        for row in rows:
            calls += row["result"]["model_calls"]
            call_seconds += sum(m["call_wall_seconds"] for m in row["call_measurements"])
            for event in row["events"]:
                verification = event.get("verification")
                if verification is None:
                    continue
                failures[verification["failure_kind"] or "accepted"] += 1
                checks["schema"]["valid" if verification["failure_kind"] != "schema" else "invalid"] += 1
                mapping = {
                    "static_context": "static_context_holds",
                    "source_identity": "source_identity_holds",
                    "action_identity": "action_identity_holds",
                    "applicability": "action_applicable",
                    "state_identity": "state_identity_holds",
                    "effect": "effect_holds",
                }
                for name, field in mapping.items():
                    value = verification["checks"][field]
                    checks[name]["not_evaluated" if value is None else "valid" if value else "invalid"] += 1
        panel, modality, arm = key
        cells.append(
            {
                "panel": panel,
                "modality": modality,
                "arm": arm,
                "expected_episodes": expected_count,
                "episodes": len(rows),
                "missing_episodes": expected_count - len(rows),
                "downstream_successes": sum(r["result"]["invariant_valid_success"] for r in rows),
                "downstream_failures": sum(not r["result"]["invariant_valid_success"] for r in rows),
                "termination_reasons": dict(sorted(Counter(r["result"]["termination_reason"] for r in rows).items())),
                "prediction_outcomes": dict(sorted(failures.items())),
                "validity_checks": {name: dict(sorted(counts.items())) for name, counts in checks.items()},
                "model_calls": calls,
                "model_call_allowance": sum(r["result"]["model_call_limit"] for r in rows),
                "model_call_wall_seconds": call_seconds,
                "active_wall_seconds": sum(r["active_wall_seconds"] for r in rows),
            }
        )
    return cells


def paired_rows(reports, expected):
    indexed = {(r["panel"], r["modality"], r["task_id"], r["arm"]): r for r in reports}
    triples = sorted({(r["panel"], r["modality"], r["task_id"]) for r in expected})
    rows = []
    for panel, modality, task_id in triples:
        arms = {}
        for arm in ARMS:
            report = indexed.get((panel, modality, task_id, arm))
            arms[arm] = (
                None
                if report is None
                else {
                    "downstream_success": report["result"]["invariant_valid_success"],
                    "termination_reason": report["result"]["termination_reason"],
                    "decisions": report["result"]["decision_count"],
                    "model_calls": report["result"]["model_calls"],
                    "invalid_successors": report["result"]["invalid_successor_count"],
                }
            )
        rows.append({"panel": panel, "modality": modality, "task_id": task_id, "arms": arms})
    return rows


__all__ = [
    "ARMS",
    "episode_path",
    "exact_reference_counts",
    "expected_bindings",
    "paired_rows",
    "panels",
    "project_request",
    "run_cell",
    "successor_request",
    "summarize",
    "verify_episode",
]
