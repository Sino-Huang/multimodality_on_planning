from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from .cgas_candidate_characterization_contracts import CandidateCharacterizationError
from .cgas_candidate_characterization_runner import NextRoundRequest, RoundReport, RunnerExecution
from .cgas_candidate_characterization_runner import run_next_round as _run_next_round
from .cgas_candidate_contracts import CandidateContractError

__all__ = (
    "CandidateCharacterizationError",
    "NextRoundRequest",
    "RoundReport",
    "RunnerExecution",
    "main",
    "run_next_round",
)


def run_next_round(request: NextRoundRequest, execution: RunnerExecution | None = None) -> RoundReport:
    try:
        return _run_next_round(request, execution)
    except CandidateContractError as error:
        raise CandidateCharacterizationError(error.code, error.path or request.candidate_config) from error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Characterize exact immutable CGAS candidate batches.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    next_round = subparsers.add_parser("next-round")
    next_round.add_argument("--round", required=True, type=int)
    next_round.add_argument("--checkpoint", type=Path)
    next_round.add_argument("--feedback", type=Path)
    next_round.add_argument("--approved-trace-contract", required=True, type=Path)
    next_round.add_argument("--candidate-config", required=True, type=Path)
    next_round.add_argument("--candidate-root", required=True, type=Path)
    next_round.add_argument("--output", required=True, type=Path)
    next_round.add_argument("--json", action="store_true")
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    parsed = build_parser().parse_args(arguments)
    request = NextRoundRequest(
        Path.cwd(),
        parsed.round,
        parsed.approved_trace_contract,
        parsed.candidate_config,
        parsed.candidate_root,
        parsed.output,
        parsed.checkpoint,
        parsed.feedback,
    )
    try:
        report = run_next_round(request)
    except (CandidateCharacterizationError, OSError) as error:
        _terminal({"error": str(error), "status": "error"})
        return 1
    if parsed.json:
        _terminal(
            {
                "checkpoint": report.checkpoint_path.as_posix(),
                "read_only": report.read_only,
                "receipt": report.receipt_path.as_posix() if report.receipt_path else None,
                "status": report.status,
            }
        )
    return 0


def _terminal(record: dict[str, str | bool | None]) -> None:
    print(json.dumps(record, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
