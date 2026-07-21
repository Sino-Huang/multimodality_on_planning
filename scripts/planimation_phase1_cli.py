"""Command-line parser and process boundary for Phase 1 utilities."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

import requests

from .planimation_phase1_client import DEFAULT_BASE_URL
from .planimation_phase1_manifest import sync_assets
from .planimation_phase1_runner import render_entries, verify_output_dir


def build_parser() -> argparse.ArgumentParser:
    """Build the stable Phase 1 CLI parser."""
    parser = argparse.ArgumentParser(description="Phase 1 Planimation asset sync and rendering utilities.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    sync_parser = subparsers.add_parser("sync-assets", help="Download the curated Planimation PDDL/AP corpus.")
    sync_parser.add_argument("--manifest", type=Path, required=True)
    sync_parser.add_argument("--timeout", type=int, default=30)
    sync_parser.add_argument("--force", action="store_true")
    render_parser = subparsers.add_parser("render", help="Render curated Planimation PDDL/AP instances.")
    render_parser.add_argument("--manifest", type=Path, required=True)
    render_parser.add_argument("--output-dir", type=Path, required=True)
    render_parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    render_parser.add_argument("--pddl-url")
    render_parser.add_argument("--vfg-url")
    render_parser.add_argument("--format", dest="output_format", choices=["png", "gif", "webm", "mp4", "vfg"], default="png")
    render_parser.add_argument("--start-step", type=int, default=0)
    render_parser.add_argument("--stop-step", type=int, default=3)
    render_parser.add_argument("--quality", type=int, default=1)
    render_parser.add_argument("--max-per-domain", type=int, default=None)
    render_parser.add_argument("--domains", nargs="*", default=None)
    render_parser.add_argument("--timeout", type=int, default=60)
    render_parser.add_argument("--sleep-seconds", type=float, default=1.0)
    render_parser.add_argument("--min-successes", type=int, default=1)
    render_parser.add_argument("--preflight-only", action="store_true")
    verify_parser = subparsers.add_parser("verify-output", help="Inspect a render output directory.")
    verify_parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one Phase 1 CLI command and classify operational failures."""
    args = build_parser().parse_args(argv)
    try:
        if args.command == "sync-assets":
            summary = sync_assets(args.manifest, args.timeout, args.force)
        elif args.command == "render":
            summary = render_entries(
                args.manifest, args.output_dir, args.base_url, args.pddl_url, args.vfg_url,
                args.output_format, args.start_step, args.stop_step, args.quality, args.max_per_domain,
                set(args.domains) if args.domains else None, args.timeout, args.sleep_seconds,
                args.min_successes, args.preflight_only,
            )
        else:
            summary = verify_output_dir(args.output_dir)
    except (OSError, RuntimeError, ValueError, requests.RequestException) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0
