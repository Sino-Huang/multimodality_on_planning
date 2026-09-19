"""Run or semantically replay the bounded issue-70 development episode with progress logs."""

# Standalone invocation adds the repository root before project imports.
# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from examples.planning_benchmark_slice.matched_modality_episode import MatchedEpisodeRequest, exact_candidate_policy
from examples.planning_benchmark_slice.modality_observation import MODALITIES, ModalityInputLimits
from examples.planning_benchmark_slice.planimation_render import PlanimationRenderRequest
from examples.planning_benchmark_slice.search_episode import (
    replay_matched_modality_episode,
    run_matched_modality_episode,
)
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, ReceiptBinding, StopOutcome


class ProcessorTokenCounter:
    """Use the frozen local processor, including its chat template and image tokens."""

    def __init__(self, limits: ModalityInputLimits) -> None:
        self.limits = limits
        self.processor: Any = None

    def __call__(self, text: str, images: tuple[Path, ...]) -> int:
        if self.processor is None:
            from transformers import AutoProcessor

            print(json.dumps({"stage": "processor_loading", "model": self.limits.tokenizer_id}), flush=True)
            self.processor = AutoProcessor.from_pretrained(
                self.limits.tokenizer_id,
                revision=self.limits.tokenizer_revision,
                local_files_only=True,
            )
        content = [{"type": "text", "text": text}, *({"type": "image", "image": str(path)} for path in images)]
        encoded = self.processor.apply_chat_template(
            [{"role": "user", "content": content}],
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
        )
        return len(encoded["input_ids"][0])


def _binding(payload: dict[str, Any]) -> ReceiptBinding:
    return ReceiptBinding(payload["contract_id"], payload["attempt_id"], ROOT / payload["output_root"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/experiments/issue70/contract.json")
    parser.add_argument("--gate", type=Path, default=ROOT / "configs/experiments/issue70/gate.json")
    parser.add_argument("--authorization", type=Path, default=ROOT / "configs/experiments/issue70/authorization.json")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--dry-run", action="store_true", help="replay supplied paths; no HTTP, processor, policy calls, or writes"
    )
    modes.add_argument("--replay", type=Path, help="semantically replay an existing report offline")
    args = parser.parse_args(argv)
    started = time.monotonic()

    def progress(event: dict[str, Any]) -> None:
        print(json.dumps({**event, "elapsed_seconds": round(time.monotonic() - started, 3)}, sort_keys=True), flush=True)

    try:
        if args.replay:
            progress({"stage": "replay_started"})
            result = replay_matched_modality_episode(json.loads(args.replay.read_text()))
            progress({"stage": "replay_complete", **result})
            return 0 if result["outcome"] == "PASS" else 1
        config = json.loads(args.config.read_text())
        if (
            config["schema_version"] != "matched_modality_issue70_contract_v1"
            or config["policy"] != "exact_candidate_reference"
        ):
            raise ValueError("unsupported issue70 contract or policy")
        binding = _binding(config["binding"])
        gate_payload = json.loads(args.gate.read_text())
        gate = GateReceipt(
            _binding(gate_payload["binding"]), StopOutcome(gate_payload["outcome"]), gate_payload["ancestor_receipt_id"]
        )
        authorization_payload = json.loads(args.authorization.read_text()) if args.authorization.exists() else None
        authorization = (
            AuthorizationReceipt(_binding(authorization_payload["binding"]), authorization_payload["gate_receipt_id"])
            if authorization_payload
            else None
        )
        limits = ModalityInputLimits(
            **{**config["limits"], "input_size_bins": tuple(config["limits"]["input_size_bins"])}
        )
        root = Path(binding.output_root)
        request = MatchedEpisodeRequest(
            binding,
            config["algorithm"],
            config["max_expansions"],
            config["max_decisions"],
            PlanimationRenderRequest(
                config["base_url"],
                ROOT / config["domain_path"],
                ROOT / config["problem_path"],
                ROOT / config["animation_profile_path"],
                None,
                root / "render",
                config["timeout_seconds"],
            ),
            tuple(tuple(path) for path in config["supplied_paths"]),
            limits,
        )
        report_path = root / "report.json"
        if not args.dry_run and root.exists():
            raise ValueError("attempt output already exists; use --replay or a new contract/attempt/output binding")
        progress({"stage": "preflight", "dry_run": args.dry_run})
        report = run_matched_modality_episode(
            request,
            gate_receipt=gate,
            authorization_receipt=authorization,
            policies={modality: exact_candidate_policy for modality in MODALITIES},
            token_counter=ProcessorTokenCounter(limits),
            progress=progress,
            dry_run=args.dry_run,
        )
        if not args.dry_run:
            root.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2) + "\n")
        progress(
            {
                "stage": "complete",
                "outcome": report["outcome"],
                "reason": report.get("reason"),
                "scientific_completion": report["scientific_completion"],
                "aligned_decisions": report.get("aligned_decisions", 0),
                "output": str(report_path) if not args.dry_run else None,
            }
        )
        return 0 if report["outcome"] == "PASS" else 1
    except (OSError, ValueError, KeyError) as error:
        progress({"stage": "failed", "outcome": "INVALID", "scientific_completion": False, "reason": str(error)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
