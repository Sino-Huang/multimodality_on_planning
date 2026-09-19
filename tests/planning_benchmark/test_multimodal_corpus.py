"""Matched release gates and the shared text/image training interface."""

import copy
import json
import tempfile
from dataclasses import replace
from pathlib import Path

import pytest

from examples.planning_benchmark_slice.modality_corpus import ROOT, ModalityCorpus, VisualCorpus, release_permission
from examples.planning_benchmark_slice.scene_assets import read_json
from scripts.release_visual_corpus import main
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, ReceiptBinding, StopOutcome


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


@pytest.fixture
def attempt():
    contract = read_json(ROOT / "configs/experiments/issue74/contract.json")
    if not (ROOT / contract["source_release"]).is_file():
        pytest.skip("retained #73 source release is needed for this integration seam")
    with tempfile.TemporaryDirectory(dir=ROOT / "outputs", prefix="test-multimodal-") as temporary:
        output = Path(temporary) / "release-test"
        contract["output_root"] = str(output.relative_to(ROOT))
        yield contract, output


def authorize(contract, output):
    binding = ReceiptBinding(contract["contract_id"], output.name, output)
    gate = GateReceipt(binding, StopOutcome.PASS)
    auth: dict = AuthorizationReceipt(binding, gate.receipt_id).to_dict()
    auth.update(
        contract=copy.deepcopy(contract),
        parent_gate_receipt_id=read_json(ROOT / "configs/experiments/issue71/v2/authorization.json")["receipt_id"],
    )
    return auth, gate.to_dict()


def fixture_report(contract, output):
    source = read_json(ROOT / contract["source_release"])
    auth, gate = authorize(contract, output)
    permission = release_permission(ROOT, contract, auth, gate, output)
    assert permission.start_permitted
    report = {
        **source,
        "schema_version": "matched_modality_corpus_release_v1",
        "contract": contract,
        "authorization": auth,
        "gate": gate,
        "released_modalities": contract["released_modalities"],
        "receipt": (
            replace(permission, run_state="completed", start_permitted=False, scientific_completion=True).to_dict()
        ),
    }
    write(output / "report.json", report)
    return report


def test_successor_is_authorized_but_old_release_cannot_expose_multimodal(attempt):
    contract, output = attempt
    auth, gate = authorize(contract, output)
    receipt = release_permission(ROOT, contract, auth, gate, output)
    assert receipt.start_permitted and not receipt.scientific_completion
    assert not output.exists()
    old = VisualCorpus(ROOT, ROOT / contract["source_release"])
    record = next(old.records(algorithm="bfs", split="train"))
    with pytest.raises(ValueError, match="not part of this release"):
        old.training_example(record, "multimodal-state")


@pytest.mark.parametrize(
    "defect,expected",
    [
        ("missing", "VALID_STOP"),
        ("VALID_STOP", "ANCESTOR_STOP"),
        ("ANCESTOR_STOP", "ANCESTOR_STOP"),
        ("INVALID", "INVALID"),
        ("incomplete", "VALID_STOP"),
        ("memory", "INVALID"),
        ("wrong_source", "INVALID"),
    ],
)
def test_predecessor_stops_or_mismatches_prevent_processing(attempt, defect, expected):
    contract, output = attempt
    source = read_json(ROOT / contract["source_release"])
    path = output.parent / "source.json"
    contract["source_release"] = str(path.relative_to(ROOT))
    if defect != "missing":
        if defect in ("VALID_STOP", "ANCESTOR_STOP", "INVALID"):
            source["outcome"] = defect
        elif defect == "incomplete":
            source["complete_selected_coverage"] = False
        elif defect == "memory":
            source["contract"]["search_memory"]["accepted_delta_limit"] = 15
        else:
            source["contract"]["source_issue"] = 74
        write(path, source)
    auth, gate = authorize(contract, output)
    receipt = release_permission(ROOT, contract, auth, gate, output)
    assert receipt.outcome.value == expected
    assert not receipt.start_permitted and not receipt.scientific_completion
    assert not output.exists()
    if defect == "memory":
        assert receipt.reason == "matched corpus setting differs: search_memory"


@pytest.mark.parametrize("defect", ["receipt", "checks", "modalities", "counts", "source_shard"])
def test_loader_rejects_false_completion_or_changed_shared_shards(attempt, defect):
    contract, output = attempt
    report = fixture_report(contract, output)
    if defect == "receipt":
        report["receipt"]["binding"]["attempt_id"] = "wrong"
    elif defect == "checks":
        report["checks"]["teacher_live_semantic_parity"] = False
    elif defect == "modalities":
        report["released_modalities"] = ["multimodal-state"]
    elif defect == "counts":
        report["counts"]["decisions"] -= 1
    else:
        report["results"][0]["path"] = "unbound-shard.jsonl.gz"
    write(output / "report.json", report)
    with pytest.raises(ValueError):
        ModalityCorpus(ROOT, output / "report.json")


def test_all_algorithms_load_matching_text_and_images_with_same_memory(attempt):
    contract, output = attempt
    fixture_report(contract, output)
    corpus = ModalityCorpus(ROOT, output / "report.json")
    for algorithm in ("bfs", "best_first_width", "best_first_add_w3", "best_first_add_greedy"):
        record = next(corpus.records(algorithm=algorithm, split="train"))
        examples = {m: corpus.training_example(record, m) for m in contract["released_modalities"]}
        payloads = {m: json.loads(e["messages"][1]["content"][0]["text"]) for m, e in examples.items()}
        text, visual, multi = (examples[m] for m in contract["released_modalities"])
        assert text["images"] == []
        assert visual["page_roles"] == multi["page_roles"] == [p[0] for p in record["input_pages"]]
        assert all(
            v is m or v.size == m.size == (768, 1024) for v, m in zip(visual["images"], multi["images"], strict=True)
        )
        assert all(e["messages"][-1] == text["messages"][-1] for e in examples.values())
        assert payloads["text-state"]["semantic_blocks"] == payloads["multimodal-state"]["semantic_blocks"]
        for payload in payloads.values():
            assert payload["search_memory"] == record["authoritative_input"]["search_memory"]
            assert "after_operation" not in payload and "target" not in payload
        assert "semantic_blocks" not in payloads["visual-state"]
        with pytest.raises(ValueError, match="held-out"):
            next(corpus.records(algorithm=algorithm, split="test"))


def test_cli_checks_reused_shards_without_copying_or_completing_partial_panel(attempt):
    contract, output = attempt
    auth, gate = authorize(contract, output)
    args = ["--materialize", "--workers", "1", "--limit-tasks", "1"]
    for name, value in (("contract", contract), ("authorization", auth), ("gate", gate)):
        path = output.parent / f"{name}.json"
        write(path, value)
        args.extend([f"--{name}", str(path)])
    source = read_json(ROOT / contract["source_release"])
    first = ROOT / source["results"][0]["path"]
    timestamp = first.stat().st_mtime_ns
    assert main(args, issue=74) == 1
    report = read_json(output / "report.json")
    assert report["outcome"] == "VALID_STOP" and not report["scientific_completion"]
    assert report["results"][0]["path"] == source["results"][0]["path"]
    assert first.stat().st_mtime_ns == timestamp
    assert not (output / "tasks").exists()
