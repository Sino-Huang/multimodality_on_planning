from __future__ import annotations

from pathlib import Path

import pytest

from src.data_collect.replay import CanonicalReplayMismatch, build_canonical_bundle, verify_canonical_replay


def _write_artifacts(root: Path, *, problem: bytes = b"(define (problem p))\n") -> dict[str, Path]:
    root.mkdir(parents=True)
    domain = root / "domain.pddl"
    problem_path = root / "problem.pddl"
    contract = root / "contracts" / "generation.json"
    contract.parent.mkdir()
    domain.write_bytes(b"(define (domain d))\n")
    problem_path.write_bytes(problem)
    contract.write_bytes(b'{"generator":"fixture","seed":7}\n')
    return {
        "pddl/problem.pddl": problem_path,
        "contracts/generation.json": contract,
        "pddl/domain.pddl": domain,
    }


def test_fresh_canonical_bundles_are_byte_identical_across_roots_and_input_order(tmp_path: Path) -> None:
    first_artifacts = _write_artifacts(tmp_path / "run-one")
    second_artifacts = _write_artifacts(tmp_path / "elsewhere" / "run-two")

    first = build_canonical_bundle(first_artifacts)
    second = build_canonical_bundle(dict(reversed(tuple(second_artifacts.items()))))

    assert first == second
    assert str(tmp_path).encode() not in first
    assert verify_canonical_replay(first_artifacts, second_artifacts) == first


def test_canonical_replay_detects_one_changed_pddl_byte(tmp_path: Path) -> None:
    expected = _write_artifacts(tmp_path / "expected")
    replayed = _write_artifacts(tmp_path / "replayed", problem=b"(define (problem q))\n")

    assert build_canonical_bundle(expected) != build_canonical_bundle(replayed)
    with pytest.raises(CanonicalReplayMismatch, match=r"pddl/problem\.pddl"):
        verify_canonical_replay(expected, replayed)


@pytest.mark.parametrize("relative_path", ["/absolute/domain.pddl", "../outside.pddl", "pddl/../domain.pddl"])
def test_canonical_bundle_rejects_noncanonical_relative_paths(relative_path: str) -> None:
    with pytest.raises(ValueError, match="relative"):
        build_canonical_bundle({relative_path: b"pddl"})
