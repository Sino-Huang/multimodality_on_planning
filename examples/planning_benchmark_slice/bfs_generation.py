"""Issue-49-gated entry point for governed BFS generation."""

from __future__ import annotations

from pathlib import Path

from src.data_collect.generate import GenerationRequest, GenerationRunReceipt

from .bfs_phase import BFSPhaseGate
from .generation_orchestrator import run_bfs_generation_smoke


def run_frozen_bfs_generation_smoke(
    *,
    task_path: str | Path,
    request: GenerationRequest,
    phase_gate: BFSPhaseGate,
    difficulty: str,
) -> GenerationRunReceipt:
    """Run the T10 smoke only with the authorized issue-49 expansion budget."""

    max_expansions = phase_gate.require_run(
        stage="trace_generation",
        contract_id=request.binding.contract_id,
        difficulty=difficulty,
    )
    assert max_expansions is not None
    return run_bfs_generation_smoke(
        task_path=task_path,
        request=request,
        max_expansions=max_expansions,
    )


__all__ = ["run_frozen_bfs_generation_smoke"]
