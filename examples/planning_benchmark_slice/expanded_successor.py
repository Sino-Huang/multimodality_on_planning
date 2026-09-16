"""Full-state successor prediction contract for the expanded BFS study."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from .modality_corpus_replay import canonical
from .pddl_state import CanonicalState, GroundedAction, InvalidActionError, PDDLStateAuthority, PDDLTransition

SCHEMA_VERSION = "expanded_successor_prediction_v1"
RECORD_SCHEMA_VERSION = "expanded_successor_record_v1"
SYSTEM_PROMPT = """You predict the complete dynamic PDDL successor for one supplied grounded action.
Return exactly one JSON object with these fields:
- schema_version: \"expanded_successor_prediction_v1\"
- source_state_id: copy the supplied source_state_id
- action: copy the supplied {name,args} action
- static_context_id: copy the supplied immutable static_context_id
- predicted_state: {\"atoms\":[...],\"fluents\":[...],\"state_id\":\"...\"}
atoms and fluents must be complete, sorted, duplicate-free string lists. state_id must be the canonical JSON
identity of those exact lists. Static facts stay in the task context and must not be copied into dynamic atoms. Do
not use Markdown fences or add text outside the JSON object. The trusted runtime checks schema, static context,
source/action identity, applicability, state identity and effects; it never repairs or replaces an incorrect
prediction."""

_TOP_LEVEL_FIELDS = {"schema_version", "source_state_id", "action", "static_context_id", "predicted_state"}
_ACTION_FIELDS = {"name", "args"}
_STATE_FIELDS = {"atoms", "fluents", "state_id"}


def static_context_id(task_context: Mapping[str, Any]) -> str:
    """Content identity for immutable task facts kept separate from dynamic state."""

    return "sha256:" + hashlib.sha256(canonical(task_context).encode()).hexdigest()


def state_payload(state: CanonicalState) -> dict[str, Any]:
    return {
        "atoms": list(state.atoms),
        "authority_id": state.authority_id,
        "fluents": list(state.fluents),
        "state_id": state.state_id,
    }


def prediction_target(
    task_context: Mapping[str, Any],
    transition: PDDLTransition | Mapping[str, Any],
) -> dict[str, Any]:
    """Build the one canonical teacher target used by corpus and live execution."""

    if isinstance(transition, PDDLTransition):
        source_id = transition.source_state.state_id
        action = {"name": transition.action.name, "args": list(transition.action.args)}
        target = transition.target_state
        atoms, fluents, target_id = list(target.atoms), list(target.fluents), target.state_id
    else:
        source = transition["source_state"]
        action = transition["action"]
        target = transition["target_state"]
        source_id = source["state_id"]
        atoms = list(target["atoms"])
        fluents = list(target.get("fluents", []))
        target_id = target["state_id"]
    return {
        "schema_version": SCHEMA_VERSION,
        "source_state_id": source_id,
        "action": {"name": action["name"], "args": list(action["args"])},
        "static_context_id": static_context_id(task_context),
        "predicted_state": {"atoms": atoms, "fluents": fluents, "state_id": target_id},
    }


def successor_contract(record: Mapping[str, Any]) -> dict[str, Any]:
    """Convert one accepted BFS transition record without leaking its target state."""

    if record.get("algorithm") != "bfs" or record.get("split") != "train":
        raise ValueError("successor source must be a BFS training record")
    runtime = record.get("after_operation", {}).get("runtime_result", {})
    transition = runtime.get("transition")
    if runtime.get("status") != "accepted" or not isinstance(transition, Mapping):
        raise ValueError("successor source must contain an accepted transition")
    model_input = copy.deepcopy(record["authoritative_input"])
    task_context = model_input["task_context"]
    action = transition["action"]
    source_id = transition["source_state"]["state_id"]
    if model_input["observation"]["state_id"] != source_id:
        raise ValueError("successor source observation differs from the transition")
    candidates = model_input["search_memory"]["successor_candidates"]
    if not any(candidate.get("grounded_action") == action for candidate in candidates):
        raise ValueError("successor action is absent from observable candidate actions")
    for candidate in candidates:
        candidate.pop("target_state_id", None)
        candidate.pop("target_state", None)
        candidate.pop("evaluation", None)
    query = {
        "source_state_id": source_id,
        "action": {"name": action["name"], "args": list(action["args"])},
        "static_context_id": static_context_id(task_context),
    }
    model_input["successor_prediction_query"] = query
    target = prediction_target(task_context, transition)
    if transition["target_state"]["state_id"] in canonical(model_input):
        raise ValueError("successor model input leaks the target-state identity")
    return {
        "record_id": record["record_id"],
        "task_id": record["task_id"],
        "split": record["split"],
        "source_record_id": record["record_id"],
        "model_input": model_input,
        "query": query,
        "source_state": copy.deepcopy(transition["source_state"]),
        "trusted_transition": copy.deepcopy(transition),
        "target": target,
        "view_manifest": record["view_manifest"],
        "state": record["state"],
        "input_pages": copy.deepcopy(record["input_pages"]),
    }


def select_transition_records(
    records: Sequence[Mapping[str, Any]],
    original_record_ids: Sequence[str],
    task_order: Sequence[str],
    *,
    size: int = 512,
) -> list[Mapping[str, Any]]:
    """Keep original accepted rows, then fill by fixed task-round-robin order."""

    by_id = {row["record_id"]: row for row in records}
    if len(by_id) != len(records) or any(record_id not in by_id for record_id in original_record_ids):
        raise ValueError("successor source records are missing or duplicated")

    def accepted(row: Mapping[str, Any]) -> bool:
        runtime = row.get("after_operation", {}).get("runtime_result", {})
        return (
            row.get("algorithm") == "bfs"
            and row.get("split") == "train"
            and row.get("task_id") in task_order
            and runtime.get("status") == "accepted"
            and isinstance(runtime.get("transition"), Mapping)
        )

    selected = [by_id[record_id] for record_id in original_record_ids if accepted(by_id[record_id])]
    selected_ids = {row["record_id"] for row in selected}
    pools = {
        task_id: [
            row
            for row in records
            if row.get("task_id") == task_id and accepted(row) and row["record_id"] not in selected_ids
        ]
        for task_id in task_order
    }
    positions = {task_id: 0 for task_id in task_order}
    while len(selected) < size:
        added = False
        for task_id in task_order:
            position = positions[task_id]
            if position < len(pools[task_id]):
                row = pools[task_id][position]
                positions[task_id] += 1
                selected.append(row)
                selected_ids.add(row["record_id"])
                added = True
                if len(selected) == size:
                    break
        if not added:
            raise ValueError("fewer accepted training transitions than the frozen successor membership")
    if len(selected_ids) != size:
        raise ValueError("successor membership contains duplicate records")
    return selected


def project_successor_example(example: Mapping[str, Any], contract: Mapping[str, Any]) -> dict[str, Any]:
    """Reuse the retained modality view while switching to the successor target."""

    projected = copy.deepcopy(dict(example))
    messages = projected["messages"]
    if len(messages) != 3 or messages[0]["role"] != "system" or messages[-1]["role"] != "assistant":
        raise ValueError("source training example has an unexpected message contract")
    messages[0] = {"role": "system", "content": SYSTEM_PROMPT}
    content = messages[1]["content"]
    parts = content if isinstance(content, list) else [{"type": "text", "text": content}]
    text_parts = [part for part in parts if part.get("type") == "text"]
    if len(text_parts) != 1:
        raise ValueError("source training example must contain one semantic text payload")
    payload = json.loads(text_parts[0]["text"])
    memory = payload["search_memory"]
    for candidate in memory["successor_candidates"]:
        candidate.pop("target_state_id", None)
        candidate.pop("target_state", None)
        candidate.pop("evaluation", None)
    payload["successor_prediction_query"] = copy.deepcopy(contract["query"])
    text_parts[0]["text"] = canonical(payload)
    messages[-1] = {"role": "assistant", "content": canonical(contract["target"])}
    return projected


def parse_prediction(raw_prediction: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Strictly parse a prediction without normalizing or repairing it."""

    if not isinstance(raw_prediction, str):
        return None, {"status": "rejected", "error": "prediction must be text"}
    try:
        parsed = json.loads(raw_prediction)
    except json.JSONDecodeError as error:
        return None, {"status": "rejected", "error": f"invalid JSON: {error.msg}"}
    if not isinstance(parsed, dict) or set(parsed) != _TOP_LEVEL_FIELDS:
        return None, {"status": "rejected", "error": "prediction has incorrect top-level fields"}
    action = parsed.get("action")
    predicted = parsed.get("predicted_state")
    if (
        parsed.get("schema_version") != SCHEMA_VERSION
        or not isinstance(parsed.get("source_state_id"), str)
        or not isinstance(parsed.get("static_context_id"), str)
        or not isinstance(action, dict)
        or set(action) != _ACTION_FIELDS
        or not isinstance(action.get("name"), str)
        or not isinstance(action.get("args"), list)
        or not all(isinstance(arg, str) for arg in action["args"])
        or not isinstance(predicted, dict)
        or set(predicted) != _STATE_FIELDS
        or not isinstance(predicted.get("state_id"), str)
    ):
        return None, {"status": "rejected", "error": "prediction field type or schema version is invalid"}
    for field in ("atoms", "fluents"):
        values = predicted.get(field)
        if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
            return None, {"status": "rejected", "error": f"predicted_state.{field} must be a string list"}
        if values != sorted(set(values)):
            return None, {
                "status": "rejected",
                "error": f"predicted_state.{field} must be sorted and duplicate-free",
            }
    return parsed, {"status": "accepted", "error": None}


def verify_prediction(
    authority: PDDLStateAuthority,
    source_state: CanonicalState,
    query: Mapping[str, Any],
    raw_prediction: str,
) -> dict[str, Any]:
    """Check schema, immutable context, applicability, identity and exact effects."""

    parsed, strict = parse_prediction(raw_prediction)
    checks: dict[str, bool | None] = {
        "static_context_holds": None,
        "source_identity_holds": None,
        "action_identity_holds": None,
        "action_applicable": None,
        "state_identity_holds": None,
        "effect_holds": None,
    }
    predicted_payload = None
    trusted = None
    if parsed is not None:
        action = GroundedAction(parsed["action"]["name"], tuple(parsed["action"]["args"]))
        expected_action = GroundedAction(query["action"]["name"], tuple(query["action"]["args"]))
        checks["static_context_holds"] = (
            parsed["static_context_id"] == query["static_context_id"] == static_context_id(authority.task_context())
        )
        checks["source_identity_holds"] = (
            parsed["source_state_id"] == query["source_state_id"] == source_state.state_id
        )
        checks["action_identity_holds"] = action == expected_action
        try:
            transition = authority.preview_apply(source_state, action)
            checks["action_applicable"] = True
            trusted = {
                "action": {"name": action.name, "args": list(action.args)},
                "target_state": state_payload(transition.target_state),
                "provenance": transition.provenance.to_dict(),
            }
        except (InvalidActionError, ValueError):
            transition = None
            checks["action_applicable"] = False
        predicted = authority.canonical_state(
            tuple(parsed["predicted_state"]["atoms"]), tuple(parsed["predicted_state"]["fluents"])
        )
        predicted_payload = copy.deepcopy(parsed["predicted_state"])
        checks["state_identity_holds"] = parsed["predicted_state"]["state_id"] == predicted.state_id
        checks["effect_holds"] = transition is not None and predicted == transition.target_state
    order = (
        (parsed is not None, "schema"),
        (checks["static_context_holds"] is True, "static_context"),
        (checks["source_identity_holds"] is True, "source_identity"),
        (checks["action_identity_holds"] is True, "action_identity"),
        (checks["action_applicable"] is True, "applicability"),
        (checks["state_identity_holds"] is True, "state_identity"),
        (checks["effect_holds"] is True, "effect"),
    )
    failure_kind = next((name for passed, name in order if not passed), None)
    return {
        "status": "accepted" if failure_kind is None else "rejected",
        "failure_kind": failure_kind,
        "strict_parse_result": strict,
        "checks": checks,
        "predicted_state": predicted_payload,
        "trusted_successor": trusted,
        "downstream_search": {"status": "not_evaluated", "failure": None},
        "prediction_applied": False,
        "trusted_state_substituted": False,
    }


def accept_verified_prediction(
    authority: PDDLStateAuthority,
    source_state: CanonicalState,
    query: Mapping[str, Any],
    raw_prediction: str,
) -> tuple[CanonicalState | None, dict[str, Any]]:
    """Register only an exact prediction; rejected predictions leave state unchanged."""

    verification = verify_prediction(authority, source_state, query, raw_prediction)
    if verification["status"] != "accepted":
        return None, verification
    action = GroundedAction(query["action"]["name"], tuple(query["action"]["args"]))
    target = authority.apply(source_state, action).target_state
    parsed = verification["predicted_state"]
    predicted = authority.canonical_state(tuple(parsed["atoms"]), tuple(parsed["fluents"]))
    if target != predicted:
        raise AssertionError("accepted prediction changed between preview and commit")
    return target, {**verification, "prediction_applied": True}


def prediction_record(
    authority: PDDLStateAuthority,
    contract: Mapping[str, Any],
    raw_prediction: str,
    *,
    modality: str,
    view: Mapping[str, Any],
) -> dict[str, Any]:
    source = contract["source_state"]
    source_state = authority.canonical_state(tuple(source["atoms"]), tuple(source.get("fluents", [])))
    return {
        "schema_version": RECORD_SCHEMA_VERSION,
        "record_id": contract["record_id"],
        "task_id": contract["task_id"],
        "split": contract["split"],
        "modality": modality,
        "model_input": copy.deepcopy(contract["model_input"]),
        "view": copy.deepcopy(dict(view)),
        "query": copy.deepcopy(contract["query"]),
        "source_state": state_payload(source_state),
        "raw_prediction": raw_prediction,
        "verification": verify_prediction(authority, source_state, contract["query"], raw_prediction),
        "trusted_target": copy.deepcopy(contract["target"]),
    }


def replay_prediction_record(authority: PDDLStateAuthority, record: Mapping[str, Any]) -> dict[str, Any]:
    """Re-run strict verification from raw prediction without a model call."""

    if record.get("schema_version") != RECORD_SCHEMA_VERSION or record.get("split") != "train":
        raise ValueError("unsupported successor record or split")
    model_input = record["model_input"]
    if model_input.get("successor_prediction_query") != record["query"]:
        raise ValueError("successor record query differs from its model input")
    candidates = model_input["search_memory"]["successor_candidates"]
    if any({"target_state_id", "target_state", "evaluation"}.intersection(candidate) for candidate in candidates):
        raise ValueError("successor record candidates contain target-state leakage")
    if record["trusted_target"]["predicted_state"]["state_id"] in canonical(model_input):
        raise ValueError("successor record model input contains its trusted target identity")
    source = record["source_state"]
    source_state = authority.canonical_state(tuple(source["atoms"]), tuple(source.get("fluents", [])))
    if state_payload(source_state) != source:
        raise ValueError("successor record source state is not canonical")
    actual = verify_prediction(authority, source_state, record["query"], record["raw_prediction"])
    if actual != record["verification"]:
        raise ValueError("successor prediction verification differs on replay")
    action = GroundedAction(record["query"]["action"]["name"], tuple(record["query"]["action"]["args"]))
    expected = authority.preview_apply(source_state, action)
    if prediction_target(authority.task_context(), expected) != record["trusted_target"]:
        raise ValueError("successor trusted target differs on replay")
    return actual
