"""Release permission, semantic isolation, and model-facing page boundaries."""

import copy
import gzip
import json

import pytest

from examples.planning_benchmark_slice.modality_corpus import (
    CorpusStop,
    audit_release,
    project_record,
    release_permission,
)
from scripts.release_visual_corpus import main
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, ReceiptBinding, StopOutcome


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def request(tmp_path, outcome=StopOutcome.PASS):
    output = tmp_path / "release-001"
    contract = {"contract_id": "test-visual-corpus", "output_root": "release-001"}
    binding = ReceiptBinding(contract["contract_id"], output.name, output)
    ancestor = "retained-predecessor-stop" if outcome is StopOutcome.ANCESTOR_STOP else None
    gate = GateReceipt(binding, outcome, ancestor)
    authorization: dict = AuthorizationReceipt(binding, gate.receipt_id).to_dict()
    authorization["contract"] = contract
    return contract, authorization, gate.to_dict(), output


@pytest.mark.parametrize("outcome", [StopOutcome.VALID_STOP, StopOutcome.INVALID, StopOutcome.ANCESTOR_STOP])
def test_stopped_gate_never_opens_corpus_or_claims_completion(tmp_path, outcome):
    contract, authorization, gate, output = request(tmp_path, outcome)
    receipt = release_permission(tmp_path, contract, authorization, gate, output)
    assert receipt.outcome is outcome
    assert not receipt.start_permitted and not receipt.scientific_completion
    assert receipt.run_state == ("invalid-not-run" if outcome is StopOutcome.INVALID else "gated-not-run")
    assert not output.exists()


@pytest.mark.parametrize("field", ["attempt_id", "contract_id", "output_root", "gate_receipt_id", "contract"])
def test_mismatched_authorization_cannot_start(tmp_path, field):
    contract, authorization, gate, output = request(tmp_path)
    if field in ("attempt_id", "contract_id"):
        authorization["binding"][field] = "other"
    elif field == "output_root":
        authorization["binding"][field] = str(tmp_path / "other")
    elif field == "gate_receipt_id":
        authorization[field] = "other"
    else:
        authorization[field] = {**contract, "context_tokens": 65536}
    receipt = release_permission(tmp_path, contract, authorization, gate, output)
    assert receipt.outcome is StopOutcome.INVALID
    assert not receipt.start_permitted
    assert not output.exists()


@pytest.mark.parametrize("outcome", [StopOutcome.VALID_STOP, StopOutcome.INVALID, StopOutcome.ANCESTOR_STOP])
def test_cli_retains_stopped_receipt_without_any_data_work(tmp_path, monkeypatch, capsys, outcome):
    monkeypatch.setattr("scripts.release_visual_corpus.ROOT", tmp_path)
    contract, authorization, gate, output = request(tmp_path, outcome)
    args = ["--materialize"]
    for name, value in (("contract", contract), ("authorization", authorization), ("gate", gate)):
        path = tmp_path / f"{name}.json"
        write(path, value)
        args += [f"--{name}", str(path)]
    assert main(args) == 1
    report = json.loads((output / "report.json").read_text())
    assert report["outcome"] == outcome.value
    assert not report["complete_selected_coverage"] and not report["scientific_completion"]
    assert not (output / "tasks").exists()
    assert json.loads(capsys.readouterr().out)["outcome"] == outcome.value
    before = (output / "report.json").read_text()
    assert main(args) == 1
    assert (output / "report.json").read_text() == before


def fixture_task(tmp_path, task_id="task-a", split="train", target=None):
    manifest_path = f"{task_id}/views.json"
    catalog_path = f"{task_id}/catalog.json"
    pages = [["task-context", None, 0], ["current-state", 0, 0], ["goal", None, 0]]
    manifest = {
        "source": {"source_goal": ["atom", "done", []], "objects_by_type": {}, "type_parents": {}},
        "scene_catalog": catalog_path,
        "decisions": [{"algorithm": "bfs", "index": 0, "state": 0, "input_pages": pages}],
    }
    catalog = {
        "task_context": {
            "static_initial_facts": [],
            "initial_dynamic_atoms": ["ready()"],
            "initial_dynamic_fluents": [],
        },
        "states": [{"atoms": ["ready()"], "fluents": []}],
    }
    raw = {
        "observation": {"state_atoms": ["ready()"], "state_id": "s0"},
        "search_memory": {"accepted_deltas": [], "successor_candidates": [{"action": "finish", "visited": False}]},
    }
    record = {
        "task_id": task_id,
        "algorithm": "bfs",
        "decision_index": 0,
        "state": 0,
        "split": split,
        "authoritative_input": raw,
        "target": target or {"typed_operation": "finish"},
        "input_pages": pages,
        "after_operation": {"successor_state": 1},
        "view_manifest": manifest_path,
    }
    write(tmp_path / manifest_path, manifest)
    write(tmp_path / catalog_path, catalog)
    shard = f"{task_id}/records.jsonl.gz"
    with gzip.open(tmp_path / shard, "wt") as stream:
        stream.write(json.dumps(record) + "\n")
    return {"task_id": task_id, "split": split, "view_manifest": manifest_path, "path": shard}, record, manifest, catalog


def test_same_semantics_in_train_and_dev_is_rejected_even_with_different_asset_paths(tmp_path):
    a, *_ = fixture_task(tmp_path)
    b, *_ = fixture_task(tmp_path, "task-b", "dev")
    with pytest.raises(ValueError, match=r"cross-split .*task overlap"):
        audit_release(tmp_path, [a, b])


def test_identical_model_inputs_cannot_have_different_targets(tmp_path):
    a, *_ = fixture_task(tmp_path)
    b, *_ = fixture_task(tmp_path, "task-b", target={"typed_operation": "retire"})
    with pytest.raises(ValueError, match="conflicting teacher"):
        audit_release(tmp_path, [a, b])


def test_matched_projections_preserve_memory_and_keep_results_out_of_input(tmp_path):
    result, record, manifest, catalog = fixture_task(tmp_path)
    inputs = {}
    for modality in ("text-state", "visual-state", "multimodal-state"):
        messages = project_record(record, manifest, catalog, modality)
        content = messages[1]["content"]
        inputs[modality] = json.loads(content[0]["text"])
        assert inputs[modality]["search_memory"] == record["authoritative_input"]["search_memory"]
        assert "after_operation" not in inputs[modality]
        assert "target" not in inputs[modality]
        images = [part for part in content if part["type"] == "image"]
        assert len(images) == (0 if modality == "text-state" else 3)
        assert all("current-state/0/" in part["image"] for part in images if "current-state" in part["image"])
    assert "semantic_blocks" not in inputs["visual-state"]
    assert inputs["text-state"]["semantic_blocks"] == inputs["multimodal-state"]["semantic_blocks"]
    audit = audit_release(tmp_path, [result])
    assert audit["decisions_by_algorithm_split"] == {"bfs/train": 1}


@pytest.mark.parametrize("defect", ["future", "omitted", "wrong_state"])
def test_projector_refuses_future_or_incomplete_images_and_wrong_current_facts(tmp_path, defect):
    _, record, manifest, catalog = fixture_task(tmp_path)
    record = copy.deepcopy(record)
    if defect == "future":
        record["input_pages"][1][1] = 1
    elif defect == "omitted":
        record["input_pages"].pop()
    else:
        record["authoritative_input"]["observation"]["state_atoms"] = ["done()"]
    with pytest.raises(ValueError):
        project_record(record, manifest, catalog, "visual-state")


def test_resource_stop_crosses_worker_boundary():
    import pickle

    error = pickle.loads(pickle.dumps(CorpusStop(StopOutcome.VALID_STOP, "context exceeded")))
    assert error.outcome is StopOutcome.VALID_STOP
    assert str(error) == "context exceeded"


@pytest.mark.parametrize("prefix", ["bfs/", "best_first_width/", "astar-pair-"])
def test_complete_live_task_shard_checks_replay_and_refuses_changed_target(prefix):
    """Exercise real family runtimes and the pinned local processor on tiny tasks."""
    import tempfile
    from pathlib import Path

    from examples.planning_benchmark_slice.modality_corpus import ROOT, build_task, iter_shard
    from examples.planning_benchmark_slice.modality_pages import ModalityViewStore
    from examples.planning_benchmark_slice.scene_assets import read_json

    contract = read_json(ROOT / "configs/experiments/issue73/contract.json")
    if not (ROOT / contract["views_report"]).exists():
        pytest.skip("retained #72 assets are required for the bounded live regression")
    panel = read_json(ROOT / contract["panel_manifest"])["selected"]
    row = min(
        (r for r in panel if r["task_id"].startswith(prefix)),
        key=lambda r: sum(c["decisions"] for c in r["reference_costs"].values()),
    )
    report = read_json(ROOT / contract["views_report"])
    view = next(r for r in report["results"] if r["task_id"] == row["task_id"])
    with tempfile.TemporaryDirectory(dir=ROOT / "outputs", prefix="test-visual-corpus-") as temporary:
        output = Path(temporary)
        result = build_task(ROOT, row, view, contract, output)
        assert result["records"] == sum(c["decisions"] for c in row["reference_costs"].values())
        assert build_task(ROOT, row, view, contract, output, check=True)["records"] == result["records"]
        records = list(iter_shard(ROOT / result["path"]))
        record = records[0]
        store = ModalityViewStore(ROOT, ROOT / contract["views_report"])
        observations = store.observations(
            row["task_id"], record["algorithm"], record["decision_index"], record["authoritative_input"]
        )
        assert [o.modality for o in observations] == ["text-state", "visual-state", "multimodal-state"]
        assert [p.role for p in observations[1].pages] == [p[0] for p in record["input_pages"]]
        assert all(p.image.size == (768, 1024) for p in observations[1].pages)
        assert all(o.input_tokens == record["tokens"]["input"][o.modality] for o in observations)
        records[0]["target"] = {"invalid_operation": True}
        with gzip.open(ROOT / result["path"], "wt") as stream:
            for item in records:
                stream.write(json.dumps(item) + "\n")
        with pytest.raises(ValueError, match="released rows differ"):
            build_task(ROOT, row, view, contract, output, check=True)


def test_interrupted_attempt_reuses_shard_but_cannot_complete_partial_panel():
    import tempfile
    from pathlib import Path

    from examples.planning_benchmark_slice.modality_corpus import ROOT, build_task
    from examples.planning_benchmark_slice.scene_assets import read_json

    contract = read_json(ROOT / "configs/experiments/issue73/contract.json")
    if not (ROOT / contract["views_report"]).exists():
        pytest.skip("retained #72 assets are required for the bounded live regression")
    with tempfile.TemporaryDirectory(dir=ROOT / "outputs", prefix="test-corpus-resume-") as temporary:
        config = Path(temporary)
        output = config / "release-test"
        contract["output_root"] = str(output.relative_to(ROOT))
        binding = ReceiptBinding(contract["contract_id"], output.name, output)
        gate = GateReceipt(binding, StopOutcome.PASS)
        authorization = read_json(ROOT / "configs/experiments/issue73/authorization.json")
        authorization.update(AuthorizationReceipt(binding, gate.receipt_id).to_dict(), contract=contract)
        panel = read_json(ROOT / contract["panel_manifest"])["selected"]
        report = read_json(ROOT / contract["views_report"])
        view = next(r for r in report["results"] if r["task_id"] == panel[0]["task_id"])
        result = build_task(ROOT, panel[0], view, contract, output)
        shard = ROOT / result["path"]
        modified = shard.stat().st_mtime_ns
        write(output / "attempt.json", {"contract": contract, "authorization": authorization, "gate": gate.to_dict()})
        args = ["--materialize", "--resume", "--limit-tasks", "1", "--workers", "1"]
        for name, value in (("contract", contract), ("authorization", authorization), ("gate", gate.to_dict())):
            path = config / f"{name}.json"
            write(path, value)
            args += [f"--{name}", str(path)]
        assert main(args) == 1
        stopped = read_json(output / "report.json")
        assert stopped["outcome"] == "VALID_STOP"
        assert not stopped["scientific_completion"]
        assert not stopped["complete_selected_coverage"]
        assert shard.stat().st_mtime_ns == modified
