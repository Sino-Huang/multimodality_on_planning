from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from scripts.phase3.cgas_certificates import build_steps, verify_steps
from test_cgas_alignment import _build_cgas_source, _write_render_manifest
from scripts.phase3.cgas_alignment import build_alignment


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_builds_schema_valid_bfs_and_iw_step_records_from_accepted_manifests(tmp_path: Path) -> None:
    # Given: accepted source and replay-proven alignment manifests for every split.
    source_root = _build_cgas_source(tmp_path)
    render_manifest = _write_render_manifest(source_root, tmp_path / "renders")
    alignment_root = tmp_path / "alignment-output"
    assert not build_alignment(source_root, render_manifest, alignment_root)["rejections"]
    output_root = tmp_path / "steps"

    # When: the deterministic certificate builder emits planning_cgas_v1 records.
    report = build_steps(source_root, alignment_root, output_root)

    # Then: every transition has one typed, verifier-backed planner certificate.
    assert report["accepted_rows"] == 12
    assert (output_root / "schema" / "planning_cgas_v1.schema.json").is_file()
    records = _records(output_root)
    planners = [_mapping(record, "planner") for record in records]
    assert {planner["algorithm"] for planner in planners} == {
        "breadth_first_search",
        "iterated_width",
    }
    assert all(_mapping(record, "replay_evidence")["replay_ok"] is True for record in records)
    assert all(_mapping(record, "alignment")["vision_status"] == "vision_available_step_aligned" for record in records)
    assert all(set(_mapping(record, "model_input")) == {"domain", "image_path", "planner", "task_text"} for record in records)
    verification = verify_steps(source_root, alignment_root, output_root)
    assert verification["accepted_rows"] == 12
    assert verification["valid_certificate_failures"] == 0


def test_emitted_schema_validates_every_generated_step_with_draft_202012(tmp_path: Path) -> None:
    source_root, alignment_root, output_root = _build_steps(tmp_path)
    del source_root, alignment_root

    schema = json.loads((output_root / "schema" / "planning_cgas_v1.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)

    assert [
        error
        for split in ("train", "dev", "test")
        for line in (output_root / "steps" / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()
        for error in validator.iter_errors(json.loads(line))
    ] == []


def test_verify_rejects_a_stale_steps_manifest_digest(tmp_path: Path) -> None:
    # Given: a valid serialized corpus whose persisted manifest has stale steps.
    source_root, alignment_root, output_root = _build_steps(tmp_path)
    manifest_path = output_root / "steps_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["steps_digest"] = "stale-steps-digest"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")

    # When: verification reloads the persisted manifest boundary.
    report = verify_steps(source_root, alignment_root, output_root)

    # Then: the stale manifest fails closed even though every stored row is valid.
    assert report["accepted_rows"] == 0
    assert report["rejections"] == [{"record_id": "steps_manifest", "reason": "steps_manifest_mismatch"}]


def test_verify_rejects_a_missing_steps_manifest(tmp_path: Path) -> None:
    source_root, alignment_root, output_root = _build_steps(tmp_path)
    (output_root / "steps_manifest.json").unlink()

    report = verify_steps(source_root, alignment_root, output_root)

    assert report["accepted_rows"] == 0
    assert report["rejections"] == [{"record_id": "steps_manifest", "reason": "missing_steps_manifest"}]


def test_verify_rejects_a_malformed_steps_manifest(tmp_path: Path) -> None:
    source_root, alignment_root, output_root = _build_steps(tmp_path)
    (output_root / "steps_manifest.json").write_text("{not-json", encoding="utf-8")

    report = verify_steps(source_root, alignment_root, output_root)

    assert report["accepted_rows"] == 0
    assert report["rejections"] == [{"record_id": "steps_manifest", "reason": "malformed_steps_manifest"}]


def test_verify_counts_rows_rejected_by_the_emitted_json_schema(tmp_path: Path) -> None:
    source_root, alignment_root, output_root = _build_steps(tmp_path)
    records = _records(output_root)
    del _mapping(records[0], "model_input")["domain"]
    _write_records(output_root / "steps" / "train.jsonl", records[:4])

    report = verify_steps(source_root, alignment_root, output_root)

    assert report["accepted_rows"] == 0
    assert report["invalid_schema_rows"] == 1
    rejections = report["rejections"]
    assert isinstance(rejections, list)
    assert "invalid_schema:model_input" in {
        item["reason"] for item in rejections if isinstance(item, dict) and isinstance(item.get("reason"), str)
    }


def test_verify_rejects_stale_bfs_frontier_order_summary(tmp_path: Path) -> None:
    # Given: valid bounded steps containing a BFS certificate.
    source_root, alignment_root, output_root = _build_steps(tmp_path)
    records = _records(output_root)
    bfs = next(record for record in records if _mapping(record, "planner")["algorithm"] == "breadth_first_search")
    _mapping(bfs, "certificate")["frontier_order_summary"] = ["stale-frontier-order"]
    _write_records(output_root / "steps" / "train.jsonl", records[:4])

    # When: only the BFS frontier-order invariant becomes stale.
    report = verify_steps(source_root, alignment_root, output_root)

    # Then: verification rejects the row with exactly one certificate failure.
    assert report["accepted_rows"] == 0
    assert report["valid_certificate_failures"] == 1
    rejections = report["rejections"]
    assert isinstance(rejections, list)
    assert "frontier_order_summary" in {
        item["reason"] for item in rejections if isinstance(item, dict) and isinstance(item.get("reason"), str)
    }


def test_verify_rejects_an_exact_duplicate_step_id(tmp_path: Path) -> None:
    # Given: a valid bounded corpus with one exact duplicate in the train output.
    source_root, alignment_root, output_root = _build_steps(tmp_path)
    records = _records(output_root)
    _write_records(output_root / "steps" / "train.jsonl", [*records[:4], records[0]])

    # When: verification receives 13 stored rows for a 12-step expected corpus.
    report = verify_steps(source_root, alignment_root, output_root)

    # Then: the duplicate ID fails closed without replacing unique-set checks.
    assert report["accepted_rows"] == 0
    assert report["rejections"] == [{"record_id": "steps", "reason": "duplicate_step_id"}]


@pytest.mark.parametrize(
    "field",
    [
        "action_target",
        "source_hash",
        "planner",
        "alignment",
        "replay_evidence",
        "counterfactual_targets",
    ],
)
def test_verify_rejects_a_stale_deterministic_record_field(tmp_path: Path, field: str) -> None:
    # Given: valid bounded steps with one schema-valid non-certificate mutation.
    source_root, alignment_root, output_root = _build_steps(tmp_path)
    records = _records(output_root)
    record = records[0]
    match field:
        case "action_target":
            record["action_target"] = "(stale-action)"
        case "source_hash":
            record["source_hash"] = "stale-source-hash"
        case "planner":
            _mapping(record, "planner")["version"] = "stale-version"
        case "alignment":
            _mapping(record, "alignment")["png_sha256"] = "stale-alignment-hash"
        case "replay_evidence":
            _mapping(record, "replay_evidence")["replay_validation_id"] = "stale-replay-id"
        case "counterfactual_targets":
            variants = record["counterfactual_targets"]
            assert isinstance(variants, list)
            assert isinstance(variants[0], dict)
            variants[0]["counterfactual_id"] = "stale-counterfactual-id"
        case _:
            raise AssertionError(field)
    _write_records(output_root / "steps" / "train.jsonl", records[:4])

    # When: verification reloads the serialized record.
    report = verify_steps(source_root, alignment_root, output_root)

    # Then: every deterministic field mismatch rejects the stored corpus.
    assert report["accepted_rows"] == 0
    rejections = report["rejections"]
    assert isinstance(rejections, list)
    assert {item["reason"] for item in rejections if isinstance(item, dict)} == {f"record_mismatch:{field}"}


def test_cli_verify_rejects_stale_certificate_and_oracle_input(tmp_path: Path) -> None:
    # Given: a valid bounded corpus and its generated certificate steps.
    source_root, alignment_root, output_root = _build_steps(tmp_path)
    records = _records(output_root)
    _mapping(records[0], "certificate")["expanded_state"] = "stale-state"
    _write_records(output_root / "steps" / "train.jsonl", records[:4])

    # When: the stored target fails replay-derived certificate verification.
    stale = _run("--verify", "--source-root", str(source_root), "--alignment-root", str(alignment_root), "--output-root", str(output_root))

    # Then: verification fails closed with a field-specific certificate invariant.
    assert stale.returncode == 1
    assert json.loads(stale.stdout)["valid_certificate_failures"] == 1

    # Given: a restored valid corpus whose declared model input contains a forbidden oracle field.
    build_steps(source_root, alignment_root, output_root)
    records = _records(output_root)
    _mapping(records[0], "model_input")["gold_queue"] = ["oracle"]
    _write_records(output_root / "steps" / "train.jsonl", records[:4])

    # When: the CLI verifies the model-input policy.
    oracle = _run("--verify", "--source-root", str(source_root), "--alignment-root", str(alignment_root), "--output-root", str(output_root))

    # Then: it names oracle exposure rather than accepting diagnostic state as input.
    assert oracle.returncode == 1
    assert "oracle_field_in_input" in {item["reason"] for item in json.loads(oracle.stdout)["rejections"]}


def _build_steps(root: Path) -> tuple[Path, Path, Path]:
    source_root = _build_cgas_source(root)
    render_manifest = _write_render_manifest(source_root, root / "renders")
    alignment_root = root / "alignment-output"
    build_alignment(source_root, render_manifest, alignment_root)
    output_root = root / "steps"
    build_steps(source_root, alignment_root, output_root)
    return source_root, alignment_root, output_root


def _records(root: Path) -> list[dict[str, object]]:
    return [json.loads(line) for split in ("train", "dev", "test") for line in (root / "steps" / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()]


def _write_records(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in records), encoding="utf-8")


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "scripts.phase3.cgas_certificates", *arguments], cwd=REPOSITORY_ROOT, check=False, capture_output=True, text=True)


def _mapping(record: dict[str, object], field: str) -> dict[str, object]:
    value = record[field]
    assert isinstance(value, dict)
    return value
