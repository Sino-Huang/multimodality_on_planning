from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Sequence

from .cgas_certificates import verify_steps
from .cgas_qwenvl_contracts import JsonRecord, QwenContractError, build_manifest, convert_steps, validate_records
from .cgas_qwenvl_publication import publish_candidate


SPLITS = ("train", "dev", "test")
OUTPUT_FILES = frozenset({"train.jsonl", "dev.jsonl", "test.jsonl", "manifest.json"})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build or verify the accepted CGAS Qwen-VL corpus.")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--alignment-root", type=Path, required=True)
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    return parser


def build_corpus(source_root: Path, alignment_root: Path, corpus_root: Path, output: Path | None = None) -> dict[str, object]:
    destination = output or corpus_root / "qwenvl"
    report, steps = _accepted_steps(source_root, alignment_root, corpus_root)
    if report["rejections"]:
        return report
    candidate = Path(tempfile.mkdtemp(prefix=f".{destination.name}-candidate-", dir=destination.parent))
    try:
        try:
            _write_candidate(candidate, steps, source_root, alignment_root, corpus_root)
        except QwenContractError as error:
            return _report(0, [_reason(error.reason)])
        candidate_report = verify_corpus(source_root, alignment_root, corpus_root, candidate)
        if candidate_report["rejections"]:
            return candidate_report
        publish_candidate(candidate, destination)
    finally:
        if candidate.exists():
            shutil.rmtree(candidate)
    return _complete_report(len(steps), [], steps)


def verify_corpus(source_root: Path, alignment_root: Path, corpus_root: Path, output: Path | None = None) -> dict[str, object]:
    destination = output or corpus_root / "qwenvl"
    report, steps = _accepted_steps(source_root, alignment_root, corpus_root)
    if report["rejections"]:
        return report
    rejections: list[str] = []
    try:
        manifest = _read_json(destination / "manifest.json")
        records = {split: _read_jsonl(destination / f"{split}.jsonl") for split in SPLITS}
    except (OSError, json.JSONDecodeError, QwenContractError):
        return _report(0, ["schema_error"])
    expected_inputs = _input_digests(source_root, alignment_root, corpus_root)
    if manifest.get("inputs") != expected_inputs:
        rejections.append("stale_input_digest")
    for split in SPLITS:
        split_steps = sorted((row for row in steps if row["split"] == split), key=lambda row: str(row["step_id"]))
        if (destination / f"{split}.jsonl").read_bytes() != "".join(_json(row) + "\n" for row in records[split]).encode("utf-8"):
            rejections.append("schema_error")
        try:
            validate_records(split_steps, records[split], destination / "images", split)
        except QwenContractError as error:
            rejections.append(_reason(error.reason))
    ids = [str(row.get("id")) for rows in records.values() for row in rows]
    if len(ids) != len(set(ids)):
        rejections.append("duplicate_record")
    images = [str(row.get("image")) for rows in records.values() for row in rows]
    if len(images) != len(set(images)):
        rejections.append("duplicate_image")
    expected_manifest = _manifest(expected_inputs, records, destination / "images")
    if manifest != expected_manifest:
        rejections.append("manifest_mismatch")
    files = {path.name for path in destination.iterdir() if path.is_file()} if destination.is_dir() else set()
    if files != OUTPUT_FILES:
        rejections.append("output_file_set_mismatch")
    rejections.extend(_tree_errors(destination, records))
    return _complete_report(len(steps) if not rejections else 0, rejections, steps)


def _accepted_steps(source_root: Path, alignment_root: Path, corpus_root: Path) -> tuple[dict[str, object], list[JsonRecord]]:
    certificate_report = verify_steps(source_root, alignment_root, corpus_root)
    if certificate_report["rejections"]:
        return _report(0, ["steps_not_accepted"]), []
    try:
        steps = [row for split in SPLITS for row in _read_jsonl(corpus_root / "steps" / f"{split}.jsonl")]
    except (OSError, json.JSONDecodeError):
        return _report(0, ["missing_accepted_steps"]), []
    return _report(len(steps), []), steps


def _write_candidate(candidate: Path, steps: list[JsonRecord], source_root: Path, alignment_root: Path, corpus_root: Path) -> None:
    images = candidate / "images"
    images.mkdir()
    alignments = {str(row["source_transition_id"]): row for split in SPLITS for row in _read_jsonl(alignment_root / "alignment" / f"{split}.jsonl")}
    records: dict[str, list[JsonRecord]] = {}
    for split in SPLITS:
        split_steps = sorted((row for row in steps if row["split"] == split), key=lambda row: str(row["step_id"]))
        for step in split_steps:
            alignment = alignments.get(str(step["source_transition_id"]))
            if alignment is None:
                raise QwenContractError("missing_alignment")
            source = Path(str(alignment["png_path"]))
            alignment_data = step["alignment"]
            if not isinstance(alignment_data, dict):
                raise QwenContractError("invalid_step_alignment")
            expected_hash = alignment_data.get("png_sha256")
            if not isinstance(expected_hash, str) or source.is_symlink() or not source.is_file() or _sha256(source) != expected_hash:
                raise QwenContractError("invalid_source_image")
            target = images / split / f"{step['step_id']}.png"
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(source, target)
            if target.is_symlink() or not target.is_file() or _sha256(target) != expected_hash:
                raise QwenContractError("invalid_copied_image")
        records[split] = convert_steps(split_steps, images, split)
        _write_jsonl(candidate / f"{split}.jsonl", records[split])
    _write_json(candidate / "manifest.json", _manifest(_input_digests(source_root, alignment_root, corpus_root), records, images))


def _manifest(inputs: dict[str, str], records: dict[str, list[JsonRecord]], images: Path) -> dict[str, object]:
    base = build_manifest(records)
    return {"schema_version": base["schema_version"], "inputs": inputs, "splits": {split: {"count": len(records[split]), "ids": [str(row["id"]) for row in records[split]], "sha256": hashlib.sha256(_jsonl_bytes(records[split])).hexdigest()} for split in SPLITS}, "images": {str(path.relative_to(images)): _sha256(path) for path in sorted(images.rglob("*.png"))}}


def _input_digests(source: Path, alignment: Path, corpus: Path) -> dict[str, str]:
    return {"source": _tree_digest(source / "source"), "alignment": _tree_digest(alignment / "alignment"), "steps": _tree_digest(corpus / "steps"), "steps_manifest": _sha256(corpus / "steps_manifest.json")}


def _report(accepted: int, reasons: list[str]) -> dict[str, object]:
    unique = sorted(set(reasons))
    counters = {"source_acceptance_errors": 0, "path_errors": 0, "token_errors": 0, "schema_errors": 0, "input_policy_errors": 0, "target_errors": 0, "split_leakage_errors": 0, "duplicate_errors": 0, "manifest_errors": 0}
    for reason in unique:
        if reason in {"steps_not_accepted", "missing_accepted_steps"}:
            counters["source_acceptance_errors"] += 1
        elif reason in {"split_leakage"}:
            counters["split_leakage_errors"] += 1
        elif reason.startswith("duplicate"):
            counters["duplicate_errors"] += 1
        elif reason in {"manifest_mismatch", "stale_input_digest"}:
            counters["manifest_errors"] += 1
        elif reason in {"image_error", "output_tree_error", "output_file_set_mismatch"}:
            counters["path_errors"] += 1
        elif reason == "token_error":
            counters["token_errors"] += 1
        elif reason in {"schema_error"}:
            counters["schema_errors"] += 1
        elif reason.startswith("invalid_human") or reason.startswith("denied_human") or reason.startswith("denied_model_input") or reason == "malformed_human_payload":
            counters["input_policy_errors"] += 1
        elif reason.startswith("assistant") or reason.endswith("target_mismatch") or reason.startswith("malformed_assistant") or reason.startswith("invalid_assistant"):
            counters["target_errors"] += 1
        else:
            counters["schema_errors"] += 1
    return {"accepted_rows": accepted, "records_checked": accepted, "records_emitted": accepted, "split_counts": {split: 0 for split in SPLITS}, "rejections": [{"reason": reason} for reason in unique], **counters, "stale_input_digest_count": unique.count("stale_input_digest"), "split_leakage_count": unique.count("split_leakage"), "duplicate_record_count": unique.count("duplicate_record"), "duplicate_image_count": unique.count("duplicate_image"), "image_error_count": unique.count("image_error")}


def _complete_report(accepted: int, reasons: list[str], steps: list[JsonRecord]) -> dict[str, object]:
    report = _report(accepted, reasons)
    report["split_counts"] = {split: sum(row["split"] == split for row in steps) if accepted else 0 for split in SPLITS}
    return report


def _reason(reason: str) -> str:
    if reason in {"split_mismatch", "image_path_mismatch"}:
        return "split_leakage"
    if reason in {"duplicate_record_id", "duplicate_step_id"}:
        return "duplicate_record"
    if reason in {"missing_image_path", "symlink_image_path", "invalid_source_image", "invalid_copied_image", "absolute_image_path", "traversal_image_path"}:
        return "image_error"
    if reason in {"invalid_image_token_count", "assistant_media_token", "invalid_human_media"}:
        return "token_error"
    return reason


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise json.JSONDecodeError("expected object", "", 0)
    return value


def _read_jsonl(path: Path) -> list[JsonRecord]:
    rows: list[JsonRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        if not isinstance(value, dict):
            raise QwenContractError("invalid_jsonl_row")
        rows.append(value)
    return rows


def _tree_errors(destination: Path, records: dict[str, list[JsonRecord]]) -> list[str]:
    expected = {Path("manifest.json"), *(Path(f"{split}.jsonl") for split in SPLITS)}
    expected.update(Path("images") / str(row["image"]) for rows in records.values() for row in rows)
    actual: set[Path] = set()
    directories: set[Path] = set()
    for path in destination.rglob("*"):
        relative = path.relative_to(destination)
        if path.is_symlink() or (path.is_file() and (path.suffix != ".png" and relative.name not in OUTPUT_FILES)):
            return ["output_tree_error"]
        if path.is_file():
            actual.add(relative)
        elif path.is_dir():
            directories.add(relative)
    expected_dirs = {Path("images"), *(Path("images") / split for split in SPLITS)}
    return [] if actual == expected and directories == expected_dirs else ["output_tree_error"]


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.write_text(_json(value) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[JsonRecord]) -> None:
    path.write_bytes(_jsonl_bytes(rows))


def _jsonl_bytes(rows: list[JsonRecord]) -> bytes:
    return "".join(_json(row) + "\n" for row in rows).encode("utf-8")


def _tree_digest(root: Path) -> str:
    return _sha256_text("|".join(f"{path.relative_to(root)}:{_sha256(path)}" for path in sorted(root.rglob("*")) if path.is_file()))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def main(arguments: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    try:
        report = verify_corpus(args.source_root, args.alignment_root, args.corpus_root) if args.verify else build_corpus(args.source_root, args.alignment_root, args.corpus_root)
    except (OSError, QwenContractError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(_json(report))
    return int(bool(report["rejections"]))


if __name__ == "__main__":
    raise SystemExit(main())
