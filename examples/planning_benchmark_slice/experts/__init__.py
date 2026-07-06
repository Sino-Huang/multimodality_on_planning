from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from ..blocksworld import BlocksworldProblem
from .bfs import generate_bfs_trajectory
from .fast_forward import generate_fast_forward_trajectory
from .graphplan import generate_graphplan_trajectory
from .iterated_width import generate_iterated_width_trajectory


ExpertGenerator = Callable[[BlocksworldProblem, str, Path], list[dict[str, Any]]]

SUPPORTED_EXPERT_ALGORITHMS: tuple[str, ...] = ("bfs", "fast_forward", "iterated_width", "graphplan")


def generate_expert_records(
    *,
    algorithm: str,
    problem: BlocksworldProblem,
    instance_id: str,
    fixture_path: Path,
) -> list[dict[str, Any]]:
    if algorithm == "bfs":
        return generate_bfs_trajectory(problem=problem, instance_id=instance_id, fixture_path=fixture_path)
    if algorithm == "fast_forward":
        return generate_fast_forward_trajectory(problem=problem, instance_id=instance_id, fixture_path=fixture_path)
    if algorithm == "iterated_width":
        return generate_iterated_width_trajectory(problem=problem, instance_id=instance_id, fixture_path=fixture_path)
    if algorithm == "graphplan":
        return generate_graphplan_trajectory(problem=problem, instance_id=instance_id, fixture_path=fixture_path)
    raise ValueError(f"unsupported expert algorithm: {algorithm}")


def validate_supported_expert_algorithms(algorithms: Sequence[str]) -> tuple[str, ...]:
    unsupported = sorted(set(algorithms) - set(SUPPORTED_EXPERT_ALGORITHMS))
    if unsupported:
        raise ValueError(
            "expert generators are not implemented for: "
            + ", ".join(unsupported)
            + "; supported algorithms: "
            + ", ".join(SUPPORTED_EXPERT_ALGORITHMS)
        )
    return tuple(algorithms)


__all__ = [
    "SUPPORTED_EXPERT_ALGORITHMS",
    "ExpertGenerator",
    "generate_bfs_trajectory",
    "generate_expert_records",
    "generate_fast_forward_trajectory",
    "generate_graphplan_trajectory",
    "generate_iterated_width_trajectory",
    "validate_supported_expert_algorithms",
]
