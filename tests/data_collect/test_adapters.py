from __future__ import annotations

import sys
import textwrap
from pathlib import Path

from src.data_collect.adapters.base import (
    GENERATOR_DUPLICATE_OUTPUT_REASON,
    GENERATOR_TIMEOUT_REASON,
    INVALID_PDDL_REASON,
    GenerationSpec,
    GeneratorAdapter,
    GeneratorRejection,
    GeneratorRunResult,
    NormalizedCandidate,
)


VALID_DOMAIN_PDDL = """
(define (domain fake-grid)
  (:requirements :strips)
  (:predicates (connected))
)
"""

VALID_PROBLEM_PDDL = """
(define (problem fake-grid-problem)
  (:domain fake-grid)
  (:init (connected))
  (:goal (and (connected)))
)
"""


class FakeAdapter(GeneratorAdapter):
    def __init__(self, *, generator_dir: Path, mode: str, seed_supported: bool = True) -> None:
        super().__init__(adapter_id=f"fake-{mode}", generator_dir=generator_dir)
        self.mode = mode
        self.seed_supported = seed_supported
        self.domain_source_path = self.generator_dir / "source-domain.pddl"
        self.script_path = self.generator_dir / "fake_generator.py"

    def prepare(self) -> None:
        self.generator_dir.mkdir(parents=True, exist_ok=True)
        self.domain_source_path.write_text(textwrap.dedent(VALID_DOMAIN_PDDL).strip() + "\n", encoding="utf-8")
        self.script_path.write_text(self._script_for_mode(), encoding="utf-8")

    def generate_candidate(self, spec: GenerationSpec) -> GeneratorRunResult:
        self.prepare()
        return self.execute_command(
            spec=spec,
            command=(sys.executable, str(self.script_path), self.mode),
            cwd=self.generator_dir,
            domain_path=self.domain_source_path,
            problem_paths=self._problem_paths_for_mode(),
        )

    def normalize_outputs(self, raw_result: GeneratorRunResult) -> NormalizedCandidate | GeneratorRejection:
        return self.normalize_candidate_output(raw_result)

    def supports_seed(self) -> bool:
        return self.seed_supported

    def _problem_paths_for_mode(self) -> tuple[Path, ...]:
        if self.mode == "success":
            return (self.generator_dir / "generated-problem.pddl",)
        if self.mode == "duplicate":
            return (
                self.generator_dir / "generated-problem-a.pddl",
                self.generator_dir / "generated-problem-b.pddl",
            )
        return ()

    def _script_for_mode(self) -> str:
        return textwrap.dedent(
            f"""
            from __future__ import annotations

            import os
            import pathlib
            import sys
            import time


            VALID_PROBLEM_PDDL = {VALID_PROBLEM_PDDL!r}


            mode = sys.argv[1]
            root = pathlib.Path.cwd()
            (root / "observed-cwd.txt").write_text(str(root), encoding="utf-8")

            if mode == "success":
                (root / "generated-problem.pddl").write_text(VALID_PROBLEM_PDDL.strip() + "\\n", encoding="utf-8")
            elif mode == "stdout_only":
                sys.stdout.write(VALID_PROBLEM_PDDL.strip() + "\\n")
            elif mode == "invalid":
                sys.stdout.write("this is not valid pddl\\n")
            elif mode == "duplicate":
                (root / "generated-problem-a.pddl").write_text(VALID_PROBLEM_PDDL.strip() + "\\n", encoding="utf-8")
                (root / "generated-problem-b.pddl").write_text(VALID_PROBLEM_PDDL.strip() + "\\n", encoding="utf-8")
            elif mode == "timeout":
                sys.stderr.write("about to sleep\\n")
                sys.stderr.flush()
                time.sleep(1.5)
            else:
                raise RuntimeError(f"unsupported fake adapter mode: {{mode}}")

            sys.stderr.write(f"seed-aware={{mode != 'stdout_only'}}\\n")
            """
        ).strip() + "\n"


def build_spec(tmp_path: Path, *, candidate_id: str = "grid-train-easy-attempt-000000", timeout_seconds: int = 1, seed: int = 123) -> GenerationSpec:
    return GenerationSpec(
        candidate_id=candidate_id,
        output_dir=tmp_path / candidate_id,
        timeout_seconds=timeout_seconds,
        seed=seed,
    )


def test_fake_adapter_success(tmp_path: Path) -> None:
    adapter = FakeAdapter(generator_dir=tmp_path / "generator-success", mode="success")
    spec = build_spec(tmp_path, timeout_seconds=2)

    raw_result = adapter.generate_candidate(spec)
    normalized = adapter.normalize_outputs(raw_result)

    assert adapter.supports_seed() is True
    assert isinstance(normalized, NormalizedCandidate)
    assert raw_result.generator_cwd == (tmp_path / "generator-success").resolve()
    assert (adapter.generator_dir / "observed-cwd.txt").read_text(encoding="utf-8") == str(adapter.generator_dir)
    assert normalized.domain_path.name == "domain.pddl"
    assert normalized.problem_path.name == "problem.pddl"
    assert normalized.domain_path.read_text(encoding="utf-8") == textwrap.dedent(VALID_DOMAIN_PDDL).strip() + "\n"
    assert normalized.problem_path.read_text(encoding="utf-8") == textwrap.dedent(VALID_PROBLEM_PDDL).strip() + "\n"
    assert normalized.seed == 123
    assert raw_result.stdout_path.read_text(encoding="utf-8") == ""
    assert "seed-aware=True" in raw_result.stderr_path.read_text(encoding="utf-8")


def test_fake_adapter_stdout_only_output_normalizes_to_problem_file(tmp_path: Path) -> None:
    adapter = FakeAdapter(generator_dir=tmp_path / "generator-stdout", mode="stdout_only", seed_supported=False)
    spec = build_spec(tmp_path, candidate_id="grid-train-medium-attempt-000001", timeout_seconds=2)

    raw_result = adapter.generate_candidate(spec)
    normalized = adapter.normalize_outputs(raw_result)

    assert adapter.supports_seed() is False
    assert isinstance(normalized, NormalizedCandidate)
    assert normalized.problem_path.read_text(encoding="utf-8") == textwrap.dedent(VALID_PROBLEM_PDDL).strip() + "\n"
    assert raw_result.stdout.strip().startswith("(define (problem fake-grid-problem)")


def test_fake_adapter_invalid_pddl_rejected(tmp_path: Path) -> None:
    adapter = FakeAdapter(generator_dir=tmp_path / "generator-invalid", mode="invalid")
    spec = build_spec(tmp_path, candidate_id="grid-dev-easy-attempt-000002", timeout_seconds=2)

    rejection = adapter.normalize_outputs(adapter.generate_candidate(spec))

    assert isinstance(rejection, GeneratorRejection)
    assert rejection.rejection_reason == INVALID_PDDL_REASON
    assert "problem PDDL" in rejection.message


def test_fake_adapter_duplicate_output_rejected(tmp_path: Path) -> None:
    adapter = FakeAdapter(generator_dir=tmp_path / "generator-duplicate", mode="duplicate")
    spec = build_spec(tmp_path, candidate_id="grid-test-hard-attempt-000003", timeout_seconds=2)

    rejection = adapter.normalize_outputs(adapter.generate_candidate(spec))

    assert isinstance(rejection, GeneratorRejection)
    assert rejection.rejection_reason == GENERATOR_DUPLICATE_OUTPUT_REASON
    assert rejection.details["problem_source_count"] == 2


def test_fake_adapter_timeout_rejection(tmp_path: Path) -> None:
    adapter = FakeAdapter(generator_dir=tmp_path / "generator-timeout", mode="timeout")
    spec = build_spec(tmp_path, candidate_id="grid-test-medium-attempt-000004", timeout_seconds=1)

    raw_result = adapter.generate_candidate(spec)
    rejection = adapter.normalize_outputs(raw_result)

    assert raw_result.timed_out is True
    assert raw_result.exit_code is None
    assert isinstance(rejection, GeneratorRejection)
    assert rejection.rejection_reason == GENERATOR_TIMEOUT_REASON
    assert "Generator exceeded timeout" in rejection.message
    assert "about to sleep" in raw_result.stderr_path.read_text(encoding="utf-8")
