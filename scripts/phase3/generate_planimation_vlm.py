from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.phase3.planimation_pairing import CORE_BUCKETS, CORE_DOMAINS, CURRENT_TRACE_ROOTS, PairingConfig, RenderConfig, build_pairing_manifest, build_vlm_records, render_replay_states, validate_pairing_output
from scripts.phase3.planimation_pairing_contracts import JSONRecord


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Planimation-aligned Phase 3 VLM datasets from immutable trace roots.")
    parser.add_argument("--dataset-root", type=Path, action="append", default=[], help="Phase 3 trace root. Defaults to the frozen four-root output snapshot.")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--max-trace-chars", type=int, default=1_000_000)
    parser.add_argument("--max-plan-length", type=int, default=64)
    parser.add_argument("--reasoning-budget-chars", type=int, default=8192)
    parser.add_argument("--base-url", default="https://planimation.planning.domains")
    parser.add_argument("--timeout-seconds", type=int, default=90)
    parser.add_argument("--request-delay-seconds", type=float, default=1.0)
    parser.add_argument("--domain", action="append", default=[])
    parser.add_argument("--bucket", action="append", default=[])
    parser.add_argument("--render-limit", type=int, default=None, help="Render at most this many replay states; intended for bounded smoke tests.")
    parser.add_argument("--progress-every", type=int, default=100, help="Emit a replay progress event after this many state renders.")
    parser.add_argument("--quiet", action="store_true", help="Suppress replay progress events on stderr.")
    parser.add_argument("--mode", choices=("production", "bounded-smoke"), default="production")
    parser.add_argument("--manifest-only", action="store_true")
    parser.add_argument("--render-only", action="store_true", help="Build the manifest and state renders but do not emit VLM JSONL records.")
    parser.add_argument("--selection-file", type=Path, help="Frozen Todo 9 selection JSON emitted by rollout_gates.py prepare.")
    args = parser.parse_args()
    if args.max_trace_chars < 1 or args.max_plan_length < 0 or args.timeout_seconds < 1 or args.request_delay_seconds < 0 or args.progress_every < 1 or (args.render_limit is not None and args.render_limit < 1):
        parser.error("resource limits must be non-negative and timeout must be positive")
    if args.mode == "production" and args.render_limit is not None:
        parser.error("--render-limit is only allowed with --mode bounded-smoke")
    domains = frozenset(args.domain or CORE_DOMAINS)
    buckets = frozenset(args.bucket or CORE_BUCKETS)
    selected_pair_ids = None
    if args.selection_file is not None:
        selection = json.loads(args.selection_file.read_text(encoding="utf-8"))
        pair_ids = selection.get("selected_pair_ids")
        if not isinstance(pair_ids, list) or not pair_ids or not all(isinstance(pair_id, str) for pair_id in pair_ids):
            parser.error("--selection-file must contain a nonempty selected_pair_ids string list")
        selected_pair_ids = frozenset(pair_ids)
    result = build_pairing_manifest(args.dataset_root or CURRENT_TRACE_ROOTS, args.output_root, config=PairingConfig(max_trace_chars=args.max_trace_chars, max_plan_length=args.max_plan_length, domains=domains, buckets=buckets, selected_pair_ids=selected_pair_ids))
    if args.manifest_only:
        print(json.dumps(result["summary"], indent=2, sort_keys=True))
        return 0
    render_replay_states(
        args.output_root,
        config=RenderConfig(base_url=args.base_url, timeout_seconds=args.timeout_seconds, request_delay_seconds=args.request_delay_seconds),
        max_states=args.render_limit,
        output_mode=args.mode,
        progress_callback=None if args.quiet else _log_progress,
        progress_every=args.progress_every,
    )
    if args.render_only:
        print(json.dumps(validate_pairing_output(args.output_root), indent=2, sort_keys=True))
        return 0
    records = build_vlm_records(args.output_root, reasoning_budget_chars=args.reasoning_budget_chars)
    print(json.dumps({"records": records, "validation": validate_pairing_output(args.output_root)}, indent=2, sort_keys=True))
    return 0


def _log_progress(event: JSONRecord) -> None:
    print(json.dumps(event, sort_keys=True), file=sys.stderr, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
