from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from examples.planning_benchmark_slice import expanded_successor_collection as collection
from examples.planning_benchmark_slice.expanded_successor import (
    SCHEMA_VERSION,
    accept_verified_prediction,
    parse_prediction,
    prediction_record,
    prediction_target,
    project_successor_example,
    replay_prediction_record,
    select_transition_records,
    state_payload,
    static_context_id,
    successor_contract,
    verify_prediction,
)
from examples.planning_benchmark_slice.modality_corpus_replay import canonical
from examples.planning_benchmark_slice.pddl_state import (
    CanonicalState,
    GroundedAction,
    PDDLStateAuthority,
    PDDLTransition,
    TransitionProvenance,
)
from examples.planning_benchmark_slice.scene_assets import read_json as read_scene_json

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/planning/blocksworld_nontrivial.json"


def _authority() -> PDDLStateAuthority:
    payload = json.loads(FIXTURE.read_text())
    return PDDLStateAuthority.from_pddl(payload["domain_pddl"], payload["problem_pddl"])


def _source_record(
    authority: PDDLStateAuthority,
    action: GroundedAction | None = None,
    source: CanonicalState | None = None,
) -> dict:
    source = source or authority.initial_state
    action = action or authority.applicable_actions(source)[0]
    transition = authority.preview_apply(source, action)
    serialized = {
        "source_state": state_payload(transition.source_state),
        "action": {"name": action.name, "args": list(action.args)},
        "target_state": state_payload(transition.target_state),
        "provenance": transition.provenance.to_dict(),
    }
    return {
        "algorithm": "bfs",
        "split": "train",
        "record_id": "bfs/task:bfs:0",
        "task_id": "bfs/task",
        "view_manifest": "view.json.gz",
        "state": 0,
        "input_pages": [["task-context", None, 0], ["current-state", 0, 0], ["goal", None, 0]],
        "authoritative_input": {
            "observation": {
                "state_id": source.state_id,
                "state_atoms": list(source.atoms),
            },
            "search_memory": {
                "successor_candidates": [
                    {
                        "grounded_action": {"name": action.name, "args": list(action.args)},
                        "target_state_id": transition.target_state.state_id,
                        "visited": False,
                    }
                ]
            },
            "task_context": authority.task_context(),
        },
        "after_operation": {"runtime_result": {"status": "accepted", "transition": serialized}},
    }


def _contract(authority: PDDLStateAuthority) -> dict:
    return successor_contract(_source_record(authority))


def test_contract_exposes_complete_dynamic_target_without_target_leakage() -> None:
    authority = _authority()
    contract = _contract(authority)

    assert "target_state_id" not in canonical(contract["model_input"])
    assert contract["model_input"]["successor_prediction_query"] == contract["query"]
    assert contract["target"]["predicted_state"] == {
        "atoms": contract["trusted_transition"]["target_state"]["atoms"],
        "fluents": contract["trusted_transition"]["target_state"]["fluents"],
        "state_id": contract["trusted_transition"]["target_state"]["state_id"],
    }
    assert not set(authority.static_initial_facts).intersection(contract["target"]["predicted_state"]["atoms"])


def test_exact_prediction_is_verified_and_only_then_registered() -> None:
    authority = _authority()
    contract = _contract(authority)
    raw = canonical(contract["target"])
    predicted = contract["target"]["predicted_state"]
    unknown = authority.canonical_state(tuple(predicted["atoms"]), tuple(predicted["fluents"]))

    with pytest.raises(ValueError, match="not known"):
        authority.applicable_actions(unknown)
    verification = verify_prediction(authority, authority.initial_state, contract["query"], raw)
    assert verification["status"] == "accepted"
    assert verification["prediction_applied"] is False
    assert verification["trusted_state_substituted"] is False

    accepted, committed = accept_verified_prediction(authority, authority.initial_state, contract["query"], raw)
    assert accepted == unknown
    assert committed["prediction_applied"] is True
    authority.applicable_actions(accepted)


def test_wrong_effect_is_retained_and_never_applied_or_repaired() -> None:
    authority = _authority()
    contract = _contract(authority)
    wrong = copy.deepcopy(contract["target"])
    wrong["predicted_state"]["atoms"] = ["invented"]
    wrong_state = authority.canonical_state(("invented",))
    wrong["predicted_state"]["state_id"] = wrong_state.state_id
    raw = canonical(wrong)

    accepted, verification = accept_verified_prediction(
        authority, authority.initial_state, contract["query"], raw
    )

    assert accepted is None
    assert verification["failure_kind"] == "effect"
    assert verification["predicted_state"] == wrong["predicted_state"]
    assert verification["trusted_successor"]["target_state"] != verification["predicted_state"]
    assert verification["prediction_applied"] is False
    assert verification["trusted_state_substituted"] is False
    with pytest.raises(ValueError, match="not known"):
        authority.applicable_actions(wrong_state)


def test_verifier_separates_schema_context_source_action_applicability_and_identity_failures() -> None:
    authority = _authority()
    contract = _contract(authority)
    cases = []

    bad_context = copy.deepcopy(contract["target"])
    bad_context["static_context_id"] = "sha256:wrong"
    cases.append((canonical(bad_context), "static_context"))

    bad_source = copy.deepcopy(contract["target"])
    bad_source["source_state_id"] = "wrong"
    cases.append((canonical(bad_source), "source_identity"))

    other_action = authority.applicable_actions(authority.initial_state)[1]
    other_transition = authority.preview_apply(authority.initial_state, other_action)
    bad_action = prediction_target(authority.task_context(), other_transition)
    cases.append((canonical(bad_action), "action_identity"))

    inapplicable = copy.deepcopy(contract["target"])
    inapplicable["action"] = {"name": "stack", "args": ["a", "b"]}
    query = {**contract["query"], "action": inapplicable["action"]}
    result = verify_prediction(authority, authority.initial_state, query, canonical(inapplicable))
    assert result["failure_kind"] == "applicability"
    assert result["checks"]["action_applicable"] is False

    bad_identity = copy.deepcopy(contract["target"])
    bad_identity["predicted_state"]["state_id"] = "wrong"
    cases.append((canonical(bad_identity), "state_identity"))

    for raw, expected in cases:
        assert verify_prediction(authority, authority.initial_state, contract["query"], raw)["failure_kind"] == expected


@pytest.mark.parametrize(
    "raw,error",
    (
        ("not json", "invalid JSON"),
        ("[]", "top-level"),
        (canonical({"schema_version": SCHEMA_VERSION}), "top-level"),
    ),
)
def test_malformed_predictions_are_explicit_schema_failures(raw: str, error: str) -> None:
    parsed, result = parse_prediction(raw)
    assert parsed is None
    assert result["status"] == "rejected"
    assert error in result["error"]


def test_unsorted_or_duplicate_full_states_are_rejected_without_normalization() -> None:
    authority = _authority()
    contract = _contract(authority)
    malformed = copy.deepcopy(contract["target"])
    malformed["predicted_state"]["atoms"] = list(reversed(malformed["predicted_state"]["atoms"]))
    parsed, result = parse_prediction(canonical(malformed))
    assert parsed is None
    assert "sorted and duplicate-free" in result["error"]


def test_replay_rechecks_raw_prediction_and_rejects_tampering() -> None:
    authority = _authority()
    contract = _contract(authority)
    retained = prediction_record(
        authority,
        contract,
        canonical(contract["target"]),
        modality="text-state",
        view={"state": 0},
    )
    retained["model_input"]["search_memory"]["accepted_deltas"] = [{"target_state_id": "past-state"}]

    assert replay_prediction_record(authority, retained)["status"] == "accepted"
    retained["raw_prediction"] = "not json"
    with pytest.raises(ValueError, match="differs on replay"):
        replay_prediction_record(authority, retained)


def test_replay_supports_rejected_predictions_without_substituting_teacher_state() -> None:
    authority = _authority()
    contract = _contract(authority)
    retained = prediction_record(
        authority,
        contract,
        "not json",
        modality="visual-state",
        view={"state": 0},
    )

    replayed = replay_prediction_record(authority, retained)
    assert replayed["failure_kind"] == "schema"
    assert replayed["trusted_state_substituted"] is False


def test_replay_registers_a_noninitial_source_only_through_its_complete_action_path() -> None:
    authority = _authority()
    first_action = authority.applicable_actions(authority.initial_state)[0]
    source = authority.apply(authority.initial_state, first_action).target_state
    second_action = authority.applicable_actions(source)[0]
    contract = successor_contract(_source_record(authority, second_action, source))
    source_path = [{"name": first_action.name, "args": list(first_action.args)}]
    fresh = _authority()

    retained = prediction_record(
        fresh,
        contract,
        canonical(contract["target"]),
        modality="multimodal-state",
        view={"state": 1},
        source_path=source_path,
    )

    assert retained["source_path"] == source_path
    assert replay_prediction_record(_authority(), retained)["status"] == "accepted"
    retained["source_path"] = []
    with pytest.raises(ValueError, match="source path differs"):
        replay_prediction_record(_authority(), retained)


def test_projection_preserves_view_parts_but_replaces_prompt_target_and_leakage() -> None:
    authority = _authority()
    contract = _contract(authority)
    image = {"pixels": "retained"}
    payload = {
        "search_memory": {
            "successor_candidates": [
                {"grounded_action": contract["query"]["action"], "target_state_id": "secret", "visited": False}
            ]
        }
    }
    example = {
        "messages": [
            {"role": "system", "content": "old"},
            {
                "role": "user",
                "content": [{"type": "image", "image": image}, {"type": "text", "text": canonical(payload)}],
            },
            {"role": "assistant", "content": "old target"},
        ],
        "images": [image],
    }

    projected = project_successor_example(example, contract)
    user = json.loads(projected["messages"][1]["content"][1]["text"])
    assert projected["messages"][1]["content"][0]["image"] == image
    assert "target_state_id" not in canonical(user)
    assert user["successor_prediction_query"] == contract["query"]
    assert projected["messages"][-1]["content"] == canonical(contract["target"])


def test_membership_keeps_original_transitions_then_fills_in_task_round_robin_order() -> None:
    def row(task: str, index: int, accepted: bool = True) -> dict:
        return {
            "record_id": f"{task}:{index}",
            "task_id": task,
            "algorithm": "bfs",
            "split": "train",
            "after_operation": {
                "runtime_result": {
                    "status": "accepted" if accepted else "retired",
                    "transition": {"target_state": {}} if accepted else None,
                }
            },
        }

    rows = [row("a", 0), row("a", 1), row("a", 2), row("b", 0, False), row("b", 1), row("b", 2)]
    selected = select_transition_records(rows, ["a:0", "b:0"], ["a", "b"], size=4)
    assert [item["record_id"] for item in selected] == ["a:0", "a:1", "b:1", "a:2"]


def test_target_schema_preserves_complete_numeric_fluents() -> None:
    source = CanonicalState(("ready",), "authority", ("fuel=2",))
    target = CanonicalState(("done",), "authority", ("fuel=1", "score=3"))
    action = GroundedAction("finish", ())
    transition = PDDLTransition(
        source,
        action,
        target,
        TransitionProvenance("authority", source.state_id, action, target.state_id),
    )
    context = {"static_initial_facts": ["connected(a,b)"], "initial_dynamic_fluents": ["fuel=2"]}

    prediction = prediction_target(context, transition)

    assert prediction["predicted_state"]["fluents"] == ["fuel=1", "score=3"]
    assert prediction["predicted_state"]["state_id"] == target.state_id
    assert prediction["static_context_id"] == static_context_id(context)


def test_collection_replays_fixed_records_and_publishes_separate_labels(tmp_path, monkeypatch) -> None:
    rows = []
    contracts = []
    for index in range(2):
        authority = _authority()
        row = _source_record(authority)
        row["record_id"] = f"bfs/task:bfs:{index}"
        row["decision_index"] = index
        row["trace_paths"] = {"bfs": "trace.json.gz"}
        contract = successor_contract(row)
        contract["source_path"] = []
        rows.append(row)
        contracts.append(contract)
    protocol = {
        "protocol_id": "expanded-successor-v1",
        "output_root": "successor",
        "modalities": ["text-state"],
        "source_record_ids": [row["record_id"] for row in rows],
        "collection": {"records_per_modality": 2},
        "model": {"id": "model", "revision": "revision", "context_tokens": 32768, "output_tokens": 512},
        "starting_checkpoints": {"text-state": "checkpoint"},
        "launch": {"master_port_pool": [18800]},
    }
    context = {
        "records": rows,
        "contracts": contracts,
        "membership_id": "sha256:membership",
    }

    class Views:
        def __init__(self):
            self.measurements = {
                row["record_id"]: {"tokens": {"text-state": {"input": 100 + index}}}
                for index, row in enumerate(rows)
            }

    views = Views()

    def example(_root, _protocol, _context, _views, index, modality, *, pixels=True):
        return {
            "messages": [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "input"},
                {"role": "assistant", "content": canonical(contracts[index]["target"])},
            ],
            "images": [],
            "binding": {
                "state": 0,
                "input_pages": contracts[index]["input_pages"],
                # SceneOnlyViews binds the source prompt before successor projection.
                "input_tokens": 90 + index,
                "state_representation": "scene-only-128-unlabelled-v1",
            },
        }

    monkeypatch.setattr(collection, "training_example", example)
    monkeypatch.setattr(collection, "_authority", lambda _root, _row: _authority())
    calls = []

    def generate(examples):
        calls.append(len(examples))
        return [canonical(contract["target"]) for contract in contracts], {
            "batch_size": 2,
            "input_tokens": [100, 101],
            "generated_sequence_tokens": 200,
        }

    provenance = {
        "runtime_head": "runner",
        "master_port": 18800,
        "checkpoint": "checkpoint",
        "model_identity": {
            "model_id": "model",
            "revision": "revision",
            "max_context_tokens": 32768,
            "max_new_tokens": 512,
            "max_batch_size": 2,
            "max_batch_input_tokens": 24000,
            "memoize_identical_inputs": False,
        },
    }
    report, retained = collection.collect_cell(
        tmp_path,
        protocol,
        context,
        views,
        modality="text-state",
        generate=generate,
        progress=lambda **_values: None,
        runtime_provenance=provenance,
    )
    assert calls == [2]
    assert retained is False
    assert report["records"] == 2
    assert report["verification_outcomes"] == {"accepted": 2}

    collection.cell_report_path(tmp_path, protocol, "text-state").unlink()
    collection.record_path(tmp_path, protocol, "text-state", 1).unlink()
    collection._write_gzip(
        collection.cell_root(tmp_path, protocol, "text-state") / "pending-batch.json.gz",
        {
            "schema_version": collection.JOURNAL_SCHEMA,
            "protocol_id": protocol["protocol_id"],
            "modality": "text-state",
            "indices": [0, 1],
            "model_call_id": "text-state:batch-000000",
            "raw_predictions": [canonical(contract["target"]) for contract in contracts],
            "input_tokens": [100, 101],
            "generated_sequence_tokens": 200,
            "runtime_provenance": provenance,
        },
    )
    resumed, retained = collection.collect_cell(
        tmp_path,
        protocol,
        context,
        views,
        modality="text-state",
        generate=lambda _examples: pytest.fail("pending output generated again"),
        progress=lambda **_values: None,
        runtime_provenance=provenance,
    )
    assert retained is False
    assert resumed == report

    report_again, retained = collection.collect_cell(
        tmp_path,
        protocol,
        context,
        views,
        modality="text-state",
        generate=lambda _examples: pytest.fail("completed cell generated again"),
        progress=lambda **_values: None,
        runtime_provenance=provenance,
    )
    assert retained is True
    assert report_again == report

    release = collection.publish_release(tmp_path, protocol, context, views)
    assert collection.verify_release(tmp_path, protocol, context, views) == release
    interaction_set = read_scene_json(
        tmp_path / release["artifacts"]["text-state"]["interactions"]["path"]
    )
    label_set = read_scene_json(tmp_path / release["artifacts"]["text-state"]["labels"]["path"])
    assert "raw_prediction" in interaction_set["records"][0]
    assert "raw_prediction" not in label_set["records"][0]
    assert label_set["records"][0]["target"] == interaction_set["records"][0]["trusted_target"]
