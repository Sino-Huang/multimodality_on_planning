from __future__ import annotations

import json
import shutil
from collections import Counter
from pathlib import Path

import pytest

from scripts.phase3.cgas_certificates import build_steps
from scripts.phase3.cgas_provenance import build_corpus as build_source_corpus
from scripts.phase3.cgas_qwenvl import build_corpus, verify_corpus
from scripts.phase3.cgas_qwenvl_contracts import JsonRecord, QwenContractError, convert_steps
from scripts.phase3.cgas_serialization import canonical, digest, digest_text, read_jsonl, write_json, write_jsonl


FIXTURE_ROOT = Path(__file__).resolve().parents[2] / ".omo/evidence/task-4-cgas-dataloader-and-experiment-support/fixture"


def test_build_corpus_projects_only_accepted_steps_with_exact_split_images_and_manifest(tmp_path: Path) -> None:
    # Given: copied accepted Todo4 source, alignment, and steps fixture roots.
    source, alignment, steps = _inputs(tmp_path)
    output = tmp_path / "qwenvl"

    # When: the conversion CLI surface builds a native Qwen corpus.
    report = build_corpus(source, alignment, steps, output)

    # Then: every accepted step is sorted into one split with one copied image.
    assert report["accepted_rows"] == 12
    assert report["rejections"] == []
    assert verify_corpus(source, alignment, steps, output)["accepted_rows"] == 12
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["splits"]) == {"train", "dev", "test"}
    assert sum(item["count"] for item in manifest["splits"].values()) == 12
    assert set(manifest["images"]) == {
        str(path.relative_to(output / "images"))
        for path in (output / "images").rglob("*.png")
    }
    for split in ("train", "dev", "test"):
        records = _jsonl(output / f"{split}.jsonl")
        ids = _strings(records, "id")
        images = _strings(records, "image")
        assert ids == sorted(ids)
        assert all(value.startswith(f"{split}/") for value in images)


def test_verify_corpus_rejects_stale_todo4_binding_split_leakage_and_duplicate_records(tmp_path: Path) -> None:
    # Given: a published corpus made from the accepted fixture roots.
    source, alignment, steps = _inputs(tmp_path)
    output = tmp_path / "qwenvl"
    assert build_corpus(source, alignment, steps, output)["rejections"] == []

    # When: its source binding, split ownership, and row identity are each corrupted.
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    manifest["inputs"]["source"] = "stale-source-digest"
    (output / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    stale = verify_corpus(source, alignment, steps, output)
    assert build_corpus(source, alignment, steps, output)["rejections"] == []
    train = _jsonl(output / "train.jsonl")
    leaked = [dict(row) for row in train]
    (output / "images" / "dev" / Path(str(leaked[0]["image"])).name).write_bytes(
        (output / "images" / str(leaked[0]["image"])).read_bytes()
    )
    leaked[0]["image"] = str(leaked[0]["image"]).replace("train/", "dev/")
    (output / "train.jsonl").write_text("".join(json.dumps(row) + "\n" for row in leaked), encoding="utf-8")
    leaked_report = verify_corpus(source, alignment, steps, output)
    assert build_corpus(source, alignment, steps, output)["rejections"] == []
    (output / "train.jsonl").write_text(
        (output / "train.jsonl").read_text(encoding="utf-8") * 2,
        encoding="utf-8",
    )
    duplicate = verify_corpus(source, alignment, steps, output)

    # Then: all corruptions fail closed with specific counters/reasons.
    assert stale["accepted_rows"] == 0
    assert stale["stale_input_digest_count"] == 1
    assert leaked_report["split_leakage_count"] == 1
    assert duplicate["duplicate_record_count"] == 1


def test_invalid_rebuild_preserves_prior_approved_output(tmp_path: Path) -> None:
    # Given: a valid published fixture corpus and an invalid replacement source image.
    source, alignment, steps = _inputs(tmp_path)
    output = tmp_path / "qwenvl"
    assert build_corpus(source, alignment, steps, output)["rejections"] == []
    before = _tree(output)
    first = json.loads((alignment / "alignment" / "train.jsonl").read_text(encoding="utf-8").splitlines()[0])
    first["png_sha256"] = "stale-image-digest"
    (alignment / "alignment" / "train.jsonl").write_text(json.dumps(first) + "\n", encoding="utf-8")

    # When: candidate preflight rejects the invalid rebuild.
    report = build_corpus(source, alignment, steps, output)

    # Then: the approved tree remains byte-identical and no candidate remains.
    assert report["accepted_rows"] == 0
    assert report["rejections"] == [{"reason": "steps_not_accepted"}]
    assert _tree(output) == before
    assert not list(output.parent.glob(".qwenvl-candidate-*"))


def test_verify_rejects_malformed_rows_and_orphan_output_tree_even_with_manifest_recomputed(tmp_path: Path) -> None:
    # Given: a valid fixture-derived output with an attacker-created non-PNG residue.
    source, alignment, steps = _inputs(tmp_path)
    output = tmp_path / "qwenvl"
    assert build_corpus(source, alignment, steps, output)["rejections"] == []
    (output / "images" / "orphan.txt").write_text("unexpected", encoding="utf-8")

    # When: the output tree is verified without trusting its declared manifest.
    residue = verify_corpus(source, alignment, steps, output)
    assert build_corpus(source, alignment, steps, output)["rejections"] == []
    (output / "train.jsonl").write_text("[]\n", encoding="utf-8")
    malformed = verify_corpus(source, alignment, steps, output)

    # Then: tree and row boundary failures use stable counters rather than runtime errors.
    assert residue["path_errors"] == 1
    assert malformed["schema_errors"] == 1
    assert malformed["accepted_rows"] == 0


def test_verify_rejects_extra_image_token_absolute_path_and_denied_human_fields(tmp_path: Path) -> None:
    # Given: a valid fixture-derived output with independently corrupted native rows.
    source, alignment, steps = _inputs(tmp_path)
    output = tmp_path / "qwenvl"
    assert build_corpus(source, alignment, steps, output)["rejections"] == []
    baseline = _jsonl(output / "train.jsonl")

    # When: media-token cardinality, destination path, or human oracle policy is violated.
    extra_token = [dict(row) for row in baseline]
    extra_human = _conversation(extra_token[0], 0)
    extra_value = extra_human["value"]
    assert isinstance(extra_value, str)
    extra_human["value"] = f"<image>\n<image>\n{extra_value.split(chr(10), 1)[1]}"
    _write_jsonl_raw(output / "train.jsonl", extra_token)
    token_report = verify_corpus(source, alignment, steps, output)
    assert build_corpus(source, alignment, steps, output)["rejections"] == []

    absolute_path = [dict(row) for row in baseline]
    absolute_path[0]["image"] = "/tmp/leaked.png"
    _write_jsonl_raw(output / "train.jsonl", absolute_path)
    path_report = verify_corpus(source, alignment, steps, output)
    assert build_corpus(source, alignment, steps, output)["rejections"] == []

    leak = [dict(row) for row in baseline]
    human = _conversation(leak[0], 0)
    human["value"] = '<image>\n{"domain":"blocksworld","planner":"breadth_first_search","replay_transitions":[],"task_text":"Execute the next action."}'
    _write_jsonl_raw(output / "train.jsonl", leak)
    leak_report = verify_corpus(source, alignment, steps, output)

    # Then: each failure is named before the row can be accepted.
    assert token_report["token_errors"] == 1
    assert _report_int(path_report, "path_errors") >= 1
    assert leak_report["input_policy_errors"] == 1
    assert "denied_human_field:replay_transitions" in _rejection_reasons(leak_report)


def test_converter_fails_closed_when_model_input_contains_denied_fields(tmp_path: Path) -> None:
    # Given: accepted steps with a target-only field injected into the future model input.
    _source, _alignment, steps = _inputs(tmp_path)
    rows = _json_records(steps / "steps" / "train.jsonl")
    model_input = rows[0]["model_input"]
    assert isinstance(model_input, dict)
    model_input["planner_trace"] = {"frontier": []}
    image_root = tmp_path / "images"
    image_path = image_root / "train" / f"{rows[0]['step_id']}.png"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"png")

    # When: the converter preflights the future model input projection.
    with pytest.raises(QwenContractError) as error:
        convert_steps(rows, image_root, "train")

    # Then: the exact target-only policy violation is reported before any output row exists.
    assert error.value.reason == "denied_model_input_field:planner_trace"
    assert not (tmp_path / "qwenvl").exists()


def _inputs(root: Path) -> tuple[Path, Path, Path]:
    source = root / "source"
    alignment = root / "alignment"
    steps = root / "steps"
    build_source_corpus(FIXTURE_ROOT / "planning_cgas_v1" / "source_manifest.jsonl", source)
    shutil.copytree(FIXTURE_ROOT / "alignment", alignment)
    _rebind_alignment(source, alignment)
    assert build_steps(source, alignment, steps)["rejections"] == []
    return source, alignment, steps


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _json_records(path: Path) -> list[JsonRecord]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _write_jsonl_raw(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _tree(root: Path) -> dict[Path, bytes]:
    return {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def _strings(records: list[dict[str, object]], field: str) -> list[str]:
    values = [row[field] for row in records]
    assert all(isinstance(value, str) for value in values)
    return [value for value in values if isinstance(value, str)]


def _rejection_reasons(report: dict[str, object]) -> set[str]:
    rejections = report["rejections"]
    assert isinstance(rejections, list)
    reasons: set[str] = set()
    for item in rejections:
        assert isinstance(item, dict)
        reason = item["reason"]
        assert isinstance(reason, str)
        reasons.add(reason)
    return reasons


def _report_int(report: dict[str, object], field: str) -> int:
    value = report[field]
    assert isinstance(value, int)
    return value


def _conversation(record: dict[str, object], index: int) -> dict[str, object]:
    conversations = record["conversations"]
    assert isinstance(conversations, list)
    turn = conversations[index]
    assert isinstance(turn, dict)
    return turn


def _rebind_alignment(source: Path, alignment: Path) -> None:
    templates = {
        (str(row["split"]), str(row["action"]), str(row["state_before_hash"])): row
        for split in ("train", "dev", "test")
        for row in read_jsonl(alignment / "alignment" / f"{split}.jsonl")
    }
    all_rows: list[dict[str, object]] = []
    for split in ("train", "dev", "test"):
        rows: list[dict[str, object]] = []
        for source_row in read_jsonl(source / "source" / f"{split}.jsonl"):
            key = (split, str(source_row["selected_action"]), str(source_row["state_before_id"]))
            template = dict(templates[key])
            template["source_transition_id"] = source_row["record_id"]
            template["split"] = split
            template["vfg_action_index"] = source_row["step_index"]
            rows.append(template)
        all_rows.extend(rows)
        write_jsonl(alignment / "alignment" / f"{split}.jsonl", rows)
    write_json(
        alignment / "alignment" / "manifest.json",
        {
            "schema_version": "planning_cgas_alignment_v1",
            "source_digest": digest_text("|".join(digest(source / "source" / f"{split}.jsonl") for split in ("train", "dev", "test"))),
            "render_manifest_digest": "0" * 64,
            "alignment_digest": digest_text(canonical(all_rows)),
            "counts": dict(sorted(Counter(str(row["split"]) for row in all_rows).items())),
        },
    )
