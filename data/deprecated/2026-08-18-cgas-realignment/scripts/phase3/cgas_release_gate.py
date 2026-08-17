from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Sequence

from .cgas_alignment import verify_persisted_alignment
from .cgas_certificates import verify_steps
from .cgas_provenance import verify_corpus as verify_source_corpus
from .cgas_qwenvl import verify_corpus as verify_qwenvl_corpus
from .cgas_serialization import canonical, digest, digest_text


RELEASE_SCHEMA_VERSION = "planning_cgas_release_v1"
PREFLIGHT_ZERO_COUNTERS = (
    "row_identity_mismatches",
    "message_build_failures",
    "tokenization_failures",
    "empty_assistant_label_rows",
    "null_image_tensor_rows",
    "null_image_grid_rows",
)


def verify_release_inputs(corpus_root: Path, preflight_report: dict[str, object]) -> dict[str, object]:
    rejections: list[dict[str, str]] = []
    source = verify_source_corpus(corpus_root, withdraw=False)
    if source["rejections"]:
        rejections.append(_rejection("provenance_failed"))
        return _release_report(rejections, source, {}, {})
    _alignment_rows, alignment_failures = verify_persisted_alignment(corpus_root, corpus_root)
    if alignment_failures:
        rejections.append(_rejection("alignment_failed"))
        return _release_report(rejections, source, {}, {})
    certificates = verify_steps(corpus_root, corpus_root, corpus_root)
    if certificates["rejections"]:
        rejections.append(_rejection("certificates_failed"))
        return _release_report(rejections, source, certificates, {})
    qwen = verify_qwenvl_corpus(corpus_root, corpus_root, corpus_root, corpus_root / "qwenvl")
    if qwen["rejections"]:
        rejections.append(_rejection("conversion_failed"))
    if not _preflight_clean(preflight_report):
        rejections.append(_rejection("loader_preflight_failed"))
    return _release_report(rejections, source, certificates, qwen)


def publish_release_manifest(corpus_root: Path, preflight_report: dict[str, object], output_path: Path | None = None) -> dict[str, object]:
    report = verify_release_inputs(corpus_root, preflight_report)
    destination = output_path or corpus_root / "release_manifest.json"
    if not report["accepted"]:
        return report
    manifest = _release_manifest(corpus_root, preflight_report)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, candidate_name = tempfile.mkstemp(prefix=f".{destination.name}-", dir=destination.parent)
    candidate = Path(candidate_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(canonical(manifest) + "\n")
        os.replace(candidate, destination)
    except OSError:
        if candidate.exists():
            candidate.unlink()
        raise
    return {**report, "release_manifest": str(destination), "manifest_sha256": digest(destination)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish the CGAS release manifest after strict prerequisite checks.")
    parser.add_argument("--corpus-root", type=Path, default=Path("data/planning_cgas_v1"))
    parser.add_argument("--preflight-report", type=Path, required=True)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    try:
        preflight = json.loads(args.preflight_report.read_text(encoding="utf-8"))
        if not isinstance(preflight, dict):
            raise ValueError("preflight_report_not_object")
        report = publish_release_manifest(args.corpus_root, preflight)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(canonical(report))
    return 0 if report["accepted"] else 1


def _preflight_clean(report: dict[str, object]) -> bool:
    return bool(report.get("accepted")) and report.get("records_checked") == report.get("records_emitted") and all(report.get(counter) == 0 for counter in PREFLIGHT_ZERO_COUNTERS)


def _release_report(rejections: list[dict[str, str]], source: object, certificates: object, qwen: object) -> dict[str, object]:
    return {"accepted": not rejections, "rejections": rejections, "prerequisites": {"source": source, "certificates": certificates, "qwenvl": qwen}}


def _release_manifest(corpus_root: Path, preflight_report: dict[str, object]) -> dict[str, object]:
    artifacts = {
        "source": _artifact(corpus_root, ("source_manifest.jsonl", "manifest.json", "approved.json")),
        "alignment": _artifact(corpus_root / "alignment", ("manifest.json", "train.jsonl", "dev.jsonl", "test.jsonl")),
        "steps": _artifact(corpus_root, ("steps_manifest.json", "schema/planning_cgas_v1.schema.json", "steps/train.jsonl", "steps/dev.jsonl", "steps/test.jsonl")),
        "qwenvl": _artifact(corpus_root / "qwenvl", ("manifest.json", "train.jsonl", "dev.jsonl", "test.jsonl")),
    }
    return {"schema_version": RELEASE_SCHEMA_VERSION, "artifacts": artifacts, "preflight": preflight_report}


def _artifact(root: Path, names: tuple[str, ...]) -> dict[str, object]:
    files = {name: digest(root / name) for name in names}
    return {"files": files, "digest": digest_text(canonical(files))}


def _rejection(reason: str) -> dict[str, str]:
    return {"reason": reason}


if __name__ == "__main__":
    raise SystemExit(main())
