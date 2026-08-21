from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from .config import DEFAULT_CURRICULUM_CONFIG_PATH, load_curriculum_config
from .generate import GenerationRequest, run_governed_generation
from .governance import AuthorizationReceipt, GateReceipt, ReceiptBinding
from .merge import merge_shards
from .rendering import FakeRenderer, PlanimationRenderer
from .structural import (
    StructuralCell,
    StructuralProfile,
    StructuralRange,
    StructuralRequirement,
    StructuralStrataPolicy,
)
from .tools import inspect_tools


def _parse_csv_values(raw_value: str) -> tuple[str, ...]:
    values = tuple(part.strip() for part in raw_value.split(",") if part.strip())
    if not values:
        raise argparse.ArgumentTypeError("expected at least one comma-separated value")
    return values


def _parse_quota_override(raw_value: str) -> dict[str, int]:
    parsed: dict[str, int] = {}
    for chunk in raw_value.split(","):
        item = chunk.strip()
        if not item:
            raise argparse.ArgumentTypeError(f"invalid quota override {raw_value!r}: empty bucket assignment")
        if "=" not in item:
            raise argparse.ArgumentTypeError(
                f"invalid quota override {raw_value!r}: expected bucket=count pairs"
            )
        bucket, raw_count = (part.strip() for part in item.split("=", 1))
        if not bucket:
            raise argparse.ArgumentTypeError(f"invalid quota override {raw_value!r}: missing bucket name")
        if bucket in parsed:
            raise argparse.ArgumentTypeError(f"invalid quota override {raw_value!r}: duplicate bucket {bucket!r}")
        try:
            count = int(raw_count)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f"invalid quota override {raw_value!r}: {raw_count!r} is not an integer"
            ) from exc
        if count < 0:
            raise argparse.ArgumentTypeError(f"invalid quota override {raw_value!r}: counts must be non-negative")
        parsed[bucket] = count
    if not parsed:
        raise argparse.ArgumentTypeError(f"invalid quota override {raw_value!r}: no buckets parsed")
    return parsed


def _build_quotas_by_split(
    selected_splits: Sequence[str],
    quota_overrides: Sequence[Mapping[str, int]] | None,
) -> dict[str, dict[str, int]] | None:
    if not quota_overrides:
        return None
    merged: dict[str, int] = {}
    for override in quota_overrides:
        merged.update({str(bucket): int(count) for bucket, count in override.items()})
    return {split: dict(merged) for split in selected_splits}


def _build_renderer(*, require_rendering: bool, dry_run: bool):
    if dry_run:
        return None
    if require_rendering:
        return PlanimationRenderer()
    return FakeRenderer(frame_count=1)


def _print_json(payload: Mapping[str, object]) -> None:
    print(json.dumps(dict(payload), indent=2, sort_keys=True))


def _load_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_gate(path: str) -> tuple[GateReceipt, ReceiptBinding]:
    payload = _load_json(path)
    binding = ReceiptBinding(**payload["binding"])
    return (
        GateReceipt(
            binding=binding,
            outcome=payload["outcome"],
            ancestor_receipt_id=payload.get("ancestor_receipt_id"),
        ),
        binding,
    )


def _load_authorization(path: str | None, binding: ReceiptBinding) -> AuthorizationReceipt | None:
    if path is None:
        return None
    payload = _load_json(path)
    return AuthorizationReceipt(
        binding=ReceiptBinding(**payload["binding"]),
        gate_receipt_id=str(payload["gate_receipt_id"]),
    )


def _load_structural_policy(path: str) -> StructuralStrataPolicy:
    payload = _load_json(path)

    def load_range(item: Mapping[str, Any]) -> StructuralRange:
        return StructuralRange(str(item["name"]), int(item["minimum"]), int(item["maximum"]))

    def load_cell(item: Mapping[str, Any]) -> StructuralCell:
        return StructuralCell(str(item["horizon"]), str(item["branching"]), str(item["object_count"]))

    return StructuralStrataPolicy(
        version=str(payload["version"]),
        horizon_ranges=tuple(load_range(item) for item in payload["horizon_ranges"]),
        branching_ranges=tuple(load_range(item) for item in payload["branching_ranges"]),
        object_count_ranges=tuple(load_range(item) for item in payload["object_count_ranges"]),
        required_cells=tuple(
            StructuralRequirement(
                split=str(item["split"]),
                cell=load_cell(item["cell"]),
                minimum_count=int(item["minimum_count"]),
            )
            for item in payload["required_cells"]
        ),
    )


def _load_structural_profiles(path: str) -> tuple[StructuralProfile, ...]:
    payload = _load_json(path)
    profiles = []
    for item in payload:
        metadata = item.get("metadata", {})
        legacy_bucket = metadata.get("legacy_bucket")
        profiles.append(
            StructuralProfile(
                instance_id=str(item["instance_id"]),
                split=str(item["split"]),
                horizon=int(item["horizon"]),
                branching_factor=int(item["branching_factor"]),
                object_count=int(item["object_count"]),
                legacy_bucket=None if legacy_bucket is None else str(legacy_bucket),
            )
        )
    return tuple(profiles)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Data collection utilities. Accepted final manifests require rendering.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser(
        "generate",
        help="Generate curriculum manifests and rendered outputs.",
        description="Generate curriculum manifests and rendered outputs. Accepted final manifests require rendering.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    generate_parser.add_argument(
        "--config",
        type=str,
        default=str(DEFAULT_CURRICULUM_CONFIG_PATH),
        help="Path to the curriculum config.",
    )
    generate_parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="Output directory for manifests and accepted instances.",
    )
    generate_parser.add_argument(
        "--domains",
        type=_parse_csv_values,
        default=None,
        help="Comma-separated domain ids to generate.",
    )
    generate_parser.add_argument(
        "--splits",
        type=_parse_csv_values,
        default=None,
        help="Comma-separated split names to generate.",
    )
    generate_parser.add_argument(
        "--quota",
        action="append",
        type=_parse_quota_override,
        default=None,
        metavar="BUCKET=COUNT[,BUCKET=COUNT...]",
        help="Override bucket quotas for every selected split.",
    )
    generate_parser.add_argument(
        "--seed",
        type=int,
        required=True,
        help="Deterministic seed for candidate generation.",
    )
    generate_parser.add_argument(
        "--max-attempts-per-bucket",
        type=int,
        default=1000,
        help="Maximum generator attempts to spend on each bucket.",
    )
    generate_parser.add_argument(
        "--candidate-multiplier",
        type=int,
        default=None,
        help="Candidate pool multiplier for each remaining bucket quota; defaults to the config value.",
    )
    generate_parser.add_argument(
        "--require-rendering",
        action="store_true",
        help="Require rendering before accepting final outputs. Accepted final manifests require rendering.",
    )
    generate_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the command and print the resolved plan without generating outputs.",
    )
    generate_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite any existing output directory.",
    )
    generate_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable output.",
    )
    generate_parser.add_argument("--gate-receipt", required=True, help="Signed gate receipt JSON.")
    generate_parser.add_argument("--authorization-receipt", default=None, help="Signed authorization receipt JSON.")
    generate_parser.add_argument("--receipt-root", required=True, help="Absolute root for durable run receipts.")
    generate_parser.add_argument("--split-ledger", required=True, help="Append-only split ledger path.")
    generate_parser.add_argument("--structural-policy", required=True, help="Structural strata policy JSON.")
    generate_parser.add_argument(
        "--structural-profiles",
        default=None,
        help="Optional asserted structural profiles JSON.",
    )

    inspect_parser = subparsers.add_parser("inspect-tools", help="Inspect available tools and adapters.")
    inspect_parser.add_argument(
        "--config",
        type=str,
        default=str(DEFAULT_CURRICULUM_CONFIG_PATH),
        help="Path to the curriculum config to inspect.",
    )
    inspect_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the inspection report as JSON.",
    )

    merge_parser = subparsers.add_parser(
        "merge-shards",
        help="Merge finalized per-domain shard outputs into one dataset root.",
        description="Merge finalized per-domain shard outputs that contain summary.json into one dataset root.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    merge_parser.add_argument(
        "--shards-root",
        type=str,
        required=True,
        help="Directory containing finalized shard directories.",
    )
    merge_parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="Final merged dataset root.",
    )
    merge_parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume an interrupted merge into an existing output root.",
    )
    merge_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite any existing merged output directory.",
    )
    merge_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable output.",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "generate":
        if args.dry_run and args.require_rendering:
            parser.error("--require-rendering cannot be combined with --dry-run")
        if args.candidate_multiplier is not None and args.candidate_multiplier <= 0:
            parser.error("--candidate-multiplier must be positive")

        curriculum_config = load_curriculum_config(args.config)
        if args.require_rendering and not curriculum_config.require_rendering:
            curriculum_config = replace(curriculum_config, require_rendering=True)
        selected_domains = args.domains
        selected_splits = args.splits
        resolved_splits = selected_splits or tuple(curriculum_config.splits)
        quotas_by_split = _build_quotas_by_split(resolved_splits, args.quota)

        if args.dry_run:
            payload = {
                "command": "generate",
                "config": str(Path(args.config).resolve()),
                "output": str(Path(args.output).resolve()),
                "domains": list(selected_domains or curriculum_config.selected_domain_ids),
                "splits": list(resolved_splits),
                "quotas_by_split": quotas_by_split,
                "seed": args.seed,
                "max_attempts_per_bucket": args.max_attempts_per_bucket,
                "candidate_multiplier": args.candidate_multiplier
                if args.candidate_multiplier is not None
                else curriculum_config.candidate_multiplier,
                "require_rendering": bool(args.require_rendering or curriculum_config.require_rendering),
                "force": args.force,
                "dry_run": True,
            }
            if args.json:
                _print_json(payload)
            else:
                print(
                    "Dry run: "
                    f"domains={payload['domains']} splits={payload['splits']} "
                    f"quotas={payload['quotas_by_split']} output={payload['output']}"
                )
            return 0

        try:
            gate, binding = _load_gate(args.gate_receipt)
            authorization = _load_authorization(args.authorization_receipt, binding)
            structural_policy = _load_structural_policy(args.structural_policy)
            structural_profiles = (
                None if args.structural_profiles is None else _load_structural_profiles(args.structural_profiles)
            )
            renderer = _build_renderer(
                require_rendering=bool(args.require_rendering or curriculum_config.require_rendering),
                dry_run=False,
            )
            request = GenerationRequest(
                binding=binding,
                gate_receipt=gate,
                authorization_receipt=authorization,
                receipt_root=Path(args.receipt_root),
                ancestor_receipt_id=gate.ancestor_receipt_id,
            )
            receipt = run_governed_generation(
                request,
                curriculum_config,
                output_root=Path(args.output),
                renderer=renderer,
                max_attempts_per_bucket=args.max_attempts_per_bucket,
                seed=args.seed,
                force=args.force,
                domains=selected_domains,
                splits=selected_splits,
                quotas_by_split=quotas_by_split,
                candidate_multiplier=args.candidate_multiplier,
                split_ledger_path=Path(args.split_ledger),
                structural_policy=structural_policy,
                structural_profiles=structural_profiles,
                structural_policy_path=Path(args.structural_policy),
            )
        except (RuntimeError, ValueError, OSError, KeyError) as error:
            parser.exit(status=1, message=f"{error}\n")

        if args.json:
            _print_json(receipt.to_dict())
        else:
            print(f"Generation outcome {receipt.outcome.value}: {receipt.status}")
        return 0

    if args.command == "inspect-tools":
        report = inspect_tools(args.config)
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
        return 0

    if args.command == "merge-shards":
        if args.force and args.resume:
            parser.error("--force cannot be combined with --resume")

        try:
            result = merge_shards(
                shards_root=Path(args.shards_root),
                output_root=Path(args.output),
                force=args.force,
                resume=args.resume,
            )
        except (RuntimeError, ValueError) as error:
            parser.exit(status=1, message=f"{error}\n")

        if args.json:
            _print_json(
                {
                    "accepted_manifest_path": str(result.accepted_manifest_path),
                    "output_root": str(result.output_root),
                    "rejections_path": str(result.rejections_path),
                    "summary": result.summary.to_dict(),
                    "summary_path": str(result.summary_path),
                }
            )
        else:
            shard_roots = result.summary.extra.get("merge", {}).get("shard_roots", [])
            print(
                "Merged "
                f"{result.summary.accepted_total} accepted / {result.summary.rejected_total} rejected "
                f"from {len(shard_roots)} shards to {result.output_root}"
            )
        return 0

    parser.error(f"{args.command} is not implemented yet")
