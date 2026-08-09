from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from .cgas_pilot_expansion_index import build_render_coverage, publish_once


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()


def audit(index: Path, repository: Path, output: Path) -> dict[str, object]:
    manifests = tuple(sorted(repository.glob("outputs/image_frames/**/diagnostics/state_render_manifest.jsonl")))
    report, missing = build_render_coverage(index, manifests, repository)
    missing_contents = b"".join(_canonical_bytes(row) + b"\n" for row in missing)
    import hashlib

    report["missing_render_request_path"] = (output / "missing-render-request.jsonl").relative_to(repository).as_posix()
    report["missing_render_request_sha256"] = hashlib.sha256(missing_contents).hexdigest()
    report_contents = _canonical_bytes(report) + b"\n"
    publish_once(output / "render-coverage.json", report_contents)
    publish_once(output / "missing-render-request.jsonl", missing_contents)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit Phase 3 pilot render coverage without rendering.")
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    report = audit(args.index.resolve(), args.repository.resolve(), args.output.resolve())
    print(
        json.dumps(
            {
                "covered_unique_state_count": report["covered_unique_state_count"],
                "missing_unique_state_count": report["missing_unique_state_count"],
                "required_unique_state_count": report["required_unique_state_count"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
