"""Compatibility facade and CLI for fail-closed Planimation rollout gates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.phase3 import rollout_gate_promotion as _promotion
from scripts.phase3.rollout_gate_contracts import PromotionDecision, STAGES, Stage
from scripts.phase3.rollout_gate_selection import prepare_selection
from scripts.phase3.verify_planimation_vlm import verify_output


def assess_promotion(
    output_root: Path, stage: Stage, selection_file: Path, prior_receipt: Path | None = None
) -> PromotionDecision:
    """Assess promotion while preserving the public verifier monkeypatch seam."""
    return _promotion.assess_promotion(output_root, stage, selection_file, prior_receipt, verifier=verify_output)


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze and assess fail-closed Planimation rollout stages.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    assess = subparsers.add_parser("assess")
    for command in (prepare, assess):
        command.add_argument("--output-root", type=Path, required=True)
        command.add_argument("--stage", choices=STAGES, required=True)
    prepare.add_argument("--domain")
    assess.add_argument("--selection-file", type=Path, required=True)
    assess.add_argument("--prior-receipt", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        print(json.dumps(prepare_selection(args.output_root, args.stage, args.domain), indent=2, sort_keys=True))
        return 0
    decision = assess_promotion(args.output_root, args.stage, args.selection_file, args.prior_receipt)
    print(json.dumps(decision.to_record(), indent=2, sort_keys=True))
    return 0 if decision.approved else 1


if __name__ == "__main__":
    raise SystemExit(main())
