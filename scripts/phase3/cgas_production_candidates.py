from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from .cgas_candidate_accounting import AccountingRow, PlannerInput, accounting_slice
from .cgas_candidate_contracts import CandidateContractError, JsonValue
from .cgas_candidate_graph import (
    CanonicalGraph,
    CanonicalizationResult,
    Edge,
    Relation,
    canonical_leaf_bytes,
    canonicalize_graph,
    identity_graph,
    individualize_colors,
    initial_color_descriptors,
    initial_colors,
    refine_colors,
)
from .cgas_candidate_publication import materialize_slice, range_root
from .cgas_candidate_reports import BootstrapResult, bootstrap
from .cgas_candidate_space import (
    Candidate,
    Family,
    LehmerStep,
    build_candidate,
    integer_partitions,
    lehmer_steps,
    lehmer_unrank,
    ordered_families,
    partial_goal_atoms,
    problem_pddl,
    stable_initial_atoms,
    stream_capacity,
)

__all__ = (
    "AccountingRow",
    "BootstrapResult",
    "Candidate",
    "CandidateContractError",
    "CanonicalGraph",
    "CanonicalizationResult",
    "Edge",
    "Family",
    "LehmerStep",
    "PlannerInput",
    "Relation",
    "accounting_slice",
    "bootstrap",
    "build_candidate",
    "canonical_leaf_bytes",
    "canonicalize_graph",
    "identity_graph",
    "individualize_colors",
    "initial_color_descriptors",
    "initial_colors",
    "integer_partitions",
    "lehmer_steps",
    "lehmer_unrank",
    "main",
    "materialize_slice",
    "ordered_families",
    "partial_goal_atoms",
    "problem_pddl",
    "range_root",
    "refine_colors",
    "stable_initial_atoms",
    "stream_capacity",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Materialize exact finite CGAS production candidates.")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--emit-prefix", required=True, type=int)
    parser.add_argument("--report-root", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    return parser


def _slice_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Materialize one pure CGAS candidate range.")
    parser.add_argument("slice")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--object-count", required=True, type=int)
    parser.add_argument("--start-rank", required=True, type=int)
    parser.add_argument("--count", required=True, type=int)
    parser.add_argument("--json", action="store_true")
    return parser


def _terminal(payload: dict[str, JsonValue]) -> None:
    print(json.dumps(payload, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True))


def main(arguments: Sequence[str] | None = None) -> int:
    raw = tuple(arguments) if arguments is not None else tuple(sys.argv[1:])
    try:
        if raw and raw[0] == "slice":
            parsed = _slice_parser().parse_args(raw)
            receipt = materialize_slice(
                parsed.config,
                parsed.output,
                parsed.object_count,
                parsed.start_rank,
                parsed.count,
            )
            if parsed.json:
                _terminal({"range": receipt.record(), "status": "ok"})
        else:
            parsed = _parser().parse_args(raw)
            result = bootstrap(parsed.config, parsed.output, parsed.emit_prefix, parsed.report_root)
            if parsed.json:
                frontiers: dict[str, JsonValue] = {str(key): value for key, value in result.frontiers.items()}
                _terminal({"frontiers": frontiers, "range_count": len(result.ranges), "status": "ok"})
    except CandidateContractError as error:
        _terminal({"error": error.code, "status": "error"})
        return 1
    except OSError:
        _terminal({"error": "filesystem_publication_failed", "status": "error"})
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
