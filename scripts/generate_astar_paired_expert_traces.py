"""Generate or audit issue-63 paired exact A* expert traces."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from examples.planning_benchmark_slice.astar_paired_generation import (  # noqa: E402
    generate_frozen_astar_pair,
    preflight_frozen_astar_pair_generation,
    run_frozen_astar_pair_generation,
    verify_frozen_astar_pair_release,
)
from examples.planning_benchmark_slice.astar_paired_trace_audit import (  # noqa: E402
    audit_astar_pair_items_release,
    select_astar_teacher_snapshots,
)
from examples.planning_benchmark_slice.astar_phase import (  # noqa: E402
    ASTAR_GENERATION_BUDGET_POLICY,
    ASTAR_PAIRED_ADAPTERS,
    AStarPairedPhaseGate,
    build_astar_paired_generation_request,
    load_astar_paired_phase_gate,
    validate_astar_generation_budget,
)
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority  # noqa: E402
from src.data_collect.generate import GenerationRequest  # noqa: E402
from src.data_collect.governance import ReceiptBinding, StopOutcome  # noqa: E402

_DEFAULT_FREEZE = _REPO_ROOT / "configs/experiments/astar-paired-freeze-v1.json"
_DEFAULT_AUTHORIZATION = _REPO_ROOT / "configs/experiments/astar-paired-authorization-v1.json"
_DEFAULT_OUTPUT = _REPO_ROOT / "data/astar_paired_phase_v1/exact-traces"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-dry-run", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--attempt-id", default="issue-63-attempt-001")
    parser.add_argument("--output-root", type=Path, default=_DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    modes = sum((args.fixture_dry_run, args.dry_run, args.check))
    if modes > 1:
        parser.error("--fixture-dry-run, --dry-run, and --check are mutually exclusive")
    if args.fixture_dry_run:
        return _fixture_dry_run()

    # Ancestor products are loaded and checked before output or receipt creation.
    preflight_started = time.monotonic()
    _print_preflight_progress(completed=0, elapsed_seconds=0.0, status="started")
    try:
        gate = load_astar_paired_phase_gate(_DEFAULT_FREEZE, _DEFAULT_AUTHORIZATION, repo_root=_REPO_ROOT)
        rows = preflight_frozen_astar_pair_generation(gate)
    except Exception:
        print(
            json.dumps(
                {
                    "fixture_only": False,
                    "scientific_authorization": False,
                    "status": "ancestor_authorization_absent",
                    "writes": 0,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            flush=True,
        )
        return 2
    _print_preflight_progress(
        completed=1,
        elapsed_seconds=time.monotonic() - preflight_started,
        status="complete",
    )
    if args.dry_run:
        print(json.dumps({
            "pair_count": len(rows),
            "scientific_authorization": False,
            "status": "authorized_dry_run",
            "writes": 0,
        }, sort_keys=True, separators=(",", ":")), flush=True)
        return 0
    output_root = args.output_root.resolve()
    if args.check:
        verify_frozen_astar_pair_release(
            output_root / "manifests/astar-paired-expert-traces.json",
            phase_gate=gate,
            progress=_print_progress,
        )
        print(json.dumps({"status": "checked", "writes": 0}, sort_keys=True, separators=(",", ":")), flush=True)
        return 0
    request = _request(gate, output_root, args.attempt_id)
    receipt = run_frozen_astar_pair_generation(
        request=request,
        phase_gate=gate,
        resume=args.resume,
        progress=_print_progress,
    )
    print(receipt.canonical_json(), flush=True)
    return 0 if receipt.outcome in {StopOutcome.PASS, StopOutcome.VALID_STOP, StopOutcome.ANCESTOR_STOP} else 1


def _fixture_dry_run() -> int:
    with tempfile.TemporaryDirectory(prefix="astar-paired-issue63-fixture-") as temporary:
        root = Path(temporary)
        gate = _fixture_gate()
        request = _request(gate, root / "output", "fixture-contract-only", fixture_only=True)
        items = []
        rows = preflight_frozen_astar_pair_generation(gate)
        for row in rows:
            items.append(
                generate_frozen_astar_pair(
                    row=row,
                    request=request,
                    phase_gate=gate,
                    resume=False,
                    fixture_only=True,
                    progress=_print_progress,
                )
            )
        manifest = {
            "canonical_tie_break": ["f", "generation_serial"],
            "evidence_schema": "search_episode_evidence_v4",
            "pair_count": len(items),
            "pairs": items,
            "phase_receipt": gate.receipt(stage="trace_generation"),
            "schema_version": "astar_paired_expert_trace_generation_v1",
            "source_issue": 63,
            "trace_schema": "astar_trace_view_v1",
        }
        audit_astar_pair_items_release(
            manifest=manifest,
            output_root=root / "output",
            phase_gate=gate,
            progress=_print_progress,
            fixture_only=True,
        )
        # Fixture coverage is deliberately not represented as production snapshot coverage.
        synthetic = [
            {
                "adapter": "astar_hmax",
                "decision_index": index,
                "difficulty": difficulty,
                "expansion_index": index // 2,
                "input_tokens": 10 + index,
                "input": {"fixture_only": index},
                "pair_id": f"synthetic-{index:02d}",
                "target": {"typed_operation": index},
                "target_tokens": 8,
            }
            for index, difficulty in enumerate(("easy", "medium", "hard", "easy", "medium", "hard"))
        ]
        if len(select_astar_teacher_snapshots(synthetic)) != 6:
            raise AssertionError("fixture snapshot-selector contract failed")
    print(
        json.dumps(
            {
                "fixture_only": True,
                "scientific_authorization": False,
                "status": "contract_validation_only",
                "writes": 0,
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        flush=True,
    )
    return 0


def _fixture_gate() -> AStarPairedPhaseGate:
    rows: list[dict[str, Any]] = []
    for index, (name, difficulty) in enumerate(
        (("blocksworld_nontrivial.json", "easy"), ("landmark_progression.json", "medium"))
    ):
        path = _REPO_ROOT / "tests/fixtures/planning" / name
        payload = path.read_bytes()
        task = json.loads(payload)
        identity = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"]).semantic_task_identity()
        rows.append(
            {
                "astar_outcome_used_for_selection": False,
                "difficulty": difficulty,
                "domain_id": "fixture-only",
                "eligible_adapters": ["astar_hmax", "astar_landmark_count"],
                "generation_max_expansions": 16,
                "instance_id": f"fixture-contract-{index}",
                "normalized_domain_hash": "fixture-only",
                "normalized_problem_hash": "fixture-only",
                "pair_id": f"astar-fixture-pair-{index}",
                "schema_version": "astar_paired_task_row_v1",
                "selection_rule": "fixture-contract-only",
                "semantic_task_identity": identity,
                "split": "train" if index == 0 else "dev",
                "task_bytes": len(payload),
                "task_path": path.relative_to(_REPO_ROOT).as_posix(),
                "task_sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    authorization = {
        "authorization_id": "fixture-only-issue-62",
        "authorized_stages": ["trace_generation", "corpus_release"],
        "contract_id": "issue-62-astar-paired-development-v1",
        "outcome": "PASS",
        "phase_id": "issue-62-astar-paired-development-v1",
        "scientific_completion": False,
    }
    generation_budget = validate_astar_generation_budget(
        {
            "adapters": list(ASTAR_PAIRED_ADAPTERS),
            "decision_outcome_blind": True,
            "frozen_before_astar_execution": True,
            "max_expansions_by_difficulty": {"easy": 16, "hard": 16, "medium": 16},
            "policy": ASTAR_GENERATION_BUDGET_POLICY,
            "task_specific_overrides_allowed": False,
        },
        rows,
    )
    return AStarPairedPhaseGate(
        freeze={"phase_id": "issue-62-astar-paired-development-v1", "component_manifests": {}},
        components={
            "task": {"pairs": rows},
            "trace": {},
            "budget": {"generation_budget": generation_budget},
            "corpus": {"input_token_limit": 7808, "output_token_limit": 384},
            "model": {"model_revision": "fixture-only-no-tokenizer-claim"},
            "analysis": {},
        },
        authorization=authorization,
        freeze_manifest_path=_REPO_ROOT / "scripts/generate_astar_paired_expert_traces.py",
        authorization_manifest_path=_REPO_ROOT / "scripts/generate_astar_paired_expert_traces.py",
        repo_root=_REPO_ROOT,
    )


def _request(
    gate: AStarPairedPhaseGate,
    output_root: Path,
    attempt_id: str,
    *,
    fixture_only: bool = False,
) -> GenerationRequest:
    binding = ReceiptBinding(gate.phase_id, attempt_id, output_root.resolve())
    return build_astar_paired_generation_request(
        gate,
        binding=binding,
        receipt_root=(output_root.parent / "governance-receipts").resolve(),
        fixture_only=fixture_only,
    )


def _print_progress(value: str) -> None:
    print(value, flush=True)


def _print_preflight_progress(*, completed: int, elapsed_seconds: float, status: str) -> None:
    _print_progress(
        json.dumps(
            {
                "completed": completed,
                "elapsed_seconds": round(elapsed_seconds, 6),
                "estimated_remaining_seconds": None if completed == 0 else 0.0,
                "pair_id": None,
                "stage": "ancestor_preflight",
                "status": status,
                "total": 1,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
