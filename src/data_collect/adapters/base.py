from __future__ import annotations

import subprocess
import time
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..hashing import normalize_pddl


GENERATOR_TIMEOUT_REASON = "generator_timeout"
GENERATOR_FAILED_REASON = "generator_failed"
GENERATOR_MISSING_OUTPUT_REASON = "generator_missing_output"
GENERATOR_MISSING_DOMAIN_REASON = "generator_missing_domain"
GENERATOR_DUPLICATE_OUTPUT_REASON = "generator_duplicate_output"
INVALID_PDDL_REASON = "invalid_pddl"


@dataclass(frozen=True)
class GenerationSpec:
    candidate_id: str
    output_dir: Path
    timeout_seconds: int
    seed: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GeneratorRunResult:
    candidate_id: str
    adapter_id: str
    output_dir: Path
    command: tuple[str, ...]
    generator_cwd: Path
    stdout: str
    stderr: str
    stdout_path: Path
    stderr_path: Path
    exit_code: int | None
    timed_out: bool
    duration_seconds: float
    seed: int | None = None
    domain_path: Path | None = None
    problem_paths: tuple[Path, ...] = ()


@dataclass(frozen=True)
class NormalizedCandidate:
    candidate_id: str
    adapter_id: str
    output_dir: Path
    domain_path: Path
    problem_path: Path
    generator_command: tuple[str, ...]
    generator_cwd: Path
    stdout_path: Path
    stderr_path: Path
    seed: int | None = None


@dataclass(frozen=True)
class GeneratorRejection:
    candidate_id: str
    adapter_id: str
    rejection_reason: str
    message: str
    generator_command: tuple[str, ...]
    generator_cwd: Path
    stdout_path: Path
    stderr_path: Path
    seed: int | None = None
    details: dict[str, Any] = field(default_factory=dict)


class GeneratorAdapter(ABC):
    def __init__(self, *, adapter_id: str, generator_dir: Path | str) -> None:
        self.adapter_id = adapter_id
        self.generator_dir = Path(generator_dir).resolve()

    @abstractmethod
    def prepare(self) -> None:
        """Prepare the generator workspace before candidate execution."""

    @abstractmethod
    def generate_candidate(self, spec: GenerationSpec) -> GeneratorRunResult:
        """Generate one raw candidate result."""

    @abstractmethod
    def normalize_outputs(self, raw_result: GeneratorRunResult) -> NormalizedCandidate | GeneratorRejection:
        """Normalize raw generator outputs into canonical adapter assets."""

    @abstractmethod
    def supports_seed(self) -> bool:
        """Report whether this adapter can honor deterministic seeds."""

    def execute_command(
        self,
        *,
        spec: GenerationSpec,
        command: Sequence[str],
        cwd: Path | str | None = None,
        domain_path: Path | str | None = None,
        problem_paths: Sequence[Path | str] = (),
    ) -> GeneratorRunResult:
        working_dir = Path(cwd or self.generator_dir).resolve()
        spec.output_dir.mkdir(parents=True, exist_ok=True)

        stdout_path = spec.output_dir / "generator.stdout"
        stderr_path = spec.output_dir / "generator.stderr"

        started_at = time.monotonic()
        try:
            completed = subprocess.run(
                list(command),
                cwd=working_dir,
                check=False,
                text=True,
                capture_output=True,
                timeout=spec.timeout_seconds,
            )
            stdout = self._coerce_text(completed.stdout)
            stderr = self._coerce_text(completed.stderr)
            exit_code = completed.returncode
            timed_out = False
        except subprocess.TimeoutExpired as error:
            stdout = self._coerce_text(error.stdout)
            stderr = self._coerce_text(error.stderr)
            exit_code = None
            timed_out = True

        duration_seconds = time.monotonic() - started_at
        stdout_path.write_text(stdout, encoding="utf-8")
        stderr_path.write_text(stderr, encoding="utf-8")

        resolved_domain_path = Path(domain_path).resolve() if domain_path is not None else None
        resolved_problem_paths = tuple(Path(path).resolve() for path in problem_paths)

        return GeneratorRunResult(
            candidate_id=spec.candidate_id,
            adapter_id=self.adapter_id,
            output_dir=spec.output_dir,
            command=tuple(str(part) for part in command),
            generator_cwd=working_dir,
            stdout=stdout,
            stderr=stderr,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            exit_code=exit_code,
            timed_out=timed_out,
            duration_seconds=duration_seconds,
            seed=spec.seed,
            domain_path=resolved_domain_path,
            problem_paths=resolved_problem_paths,
        )

    def normalize_candidate_output(
        self,
        raw_result: GeneratorRunResult,
        *,
        domain_source: Path | str | None = None,
        problem_source: Path | str | None = None,
        problem_sources: Sequence[Path | str] = (),
    ) -> NormalizedCandidate | GeneratorRejection:
        if raw_result.timed_out:
            return self._build_rejection(
                raw_result,
                rejection_reason=GENERATOR_TIMEOUT_REASON,
                message=(
                    f"Generator exceeded timeout of {raw_result.duration_seconds:.2f} seconds "
                    f"for candidate {raw_result.candidate_id}"
                ),
                details={"duration_seconds": raw_result.duration_seconds},
            )

        if raw_result.exit_code not in (None, 0):
            return self._build_rejection(
                raw_result,
                rejection_reason=GENERATOR_FAILED_REASON,
                message=f"Generator exited with status {raw_result.exit_code}",
                details={"exit_code": raw_result.exit_code},
            )

        selected_domain_source = domain_source or raw_result.domain_path
        if selected_domain_source is None:
            return self._build_rejection(
                raw_result,
                rejection_reason=GENERATOR_MISSING_DOMAIN_REASON,
                message="Generator did not expose a domain source for normalization",
            )

        selected_problem_sources = list(problem_sources)
        if problem_source is not None:
            selected_problem_sources.append(problem_source)
        elif not selected_problem_sources:
            selected_problem_sources.extend(raw_result.problem_paths)
            if raw_result.stdout.strip():
                selected_problem_sources.append(raw_result.stdout)

        if not selected_problem_sources:
            return self._build_rejection(
                raw_result,
                rejection_reason=GENERATOR_MISSING_OUTPUT_REASON,
                message="Generator did not expose a problem source for normalization",
            )

        if len(selected_problem_sources) != 1:
            return self._build_rejection(
                raw_result,
                rejection_reason=GENERATOR_DUPLICATE_OUTPUT_REASON,
                message=f"Generator exposed {len(selected_problem_sources)} problem outputs; expected exactly one",
                details={"problem_source_count": len(selected_problem_sources)},
            )

        try:
            domain_text = self._read_output_source(selected_domain_source)
            problem_text = self._read_output_source(selected_problem_sources[0])
            self._validate_pddl_text(domain_text, kind="domain")
            self._validate_pddl_text(problem_text, kind="problem")
        except (FileNotFoundError, ValueError) as error:
            return self._build_rejection(
                raw_result,
                rejection_reason=INVALID_PDDL_REASON,
                message=str(error),
            )

        normalized_domain_path = raw_result.output_dir / "domain.pddl"
        normalized_problem_path = raw_result.output_dir / "problem.pddl"
        normalized_domain_path.write_text(domain_text, encoding="utf-8")
        normalized_problem_path.write_text(problem_text, encoding="utf-8")

        return NormalizedCandidate(
            candidate_id=raw_result.candidate_id,
            adapter_id=raw_result.adapter_id,
            output_dir=raw_result.output_dir,
            domain_path=normalized_domain_path,
            problem_path=normalized_problem_path,
            generator_command=raw_result.command,
            generator_cwd=raw_result.generator_cwd,
            stdout_path=raw_result.stdout_path,
            stderr_path=raw_result.stderr_path,
            seed=raw_result.seed,
        )

    def _build_rejection(
        self,
        raw_result: GeneratorRunResult,
        *,
        rejection_reason: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> GeneratorRejection:
        return GeneratorRejection(
            candidate_id=raw_result.candidate_id,
            adapter_id=raw_result.adapter_id,
            rejection_reason=rejection_reason,
            message=message,
            generator_command=raw_result.command,
            generator_cwd=raw_result.generator_cwd,
            stdout_path=raw_result.stdout_path,
            stderr_path=raw_result.stderr_path,
            seed=raw_result.seed,
            details=details or {},
        )

    def _read_output_source(self, source: Path | str) -> str:
        if isinstance(source, Path):
            return source.read_text(encoding="utf-8")

        return str(source)

    def _coerce_text(self, value: str | bytes | None) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value

    def _validate_pddl_text(self, text: str, *, kind: str) -> None:
        normalized = normalize_pddl(text)
        if not normalized.startswith("( define"):
            raise ValueError(f"{kind} PDDL must start with (define ...)")

        if kind == "domain":
            if "( domain" not in normalized:
                raise ValueError("domain PDDL must declare (domain ...)")
            return

        if "( problem" not in normalized:
            raise ValueError("problem PDDL must declare (problem ...)")
        if " :domain " not in normalized:
            raise ValueError("problem PDDL must declare (:domain ...)")


__all__ = [
    "GENERATOR_DUPLICATE_OUTPUT_REASON",
    "GENERATOR_FAILED_REASON",
    "GENERATOR_MISSING_DOMAIN_REASON",
    "GENERATOR_MISSING_OUTPUT_REASON",
    "GENERATOR_TIMEOUT_REASON",
    "GenerationSpec",
    "GeneratorAdapter",
    "GeneratorRejection",
    "GeneratorRunResult",
    "INVALID_PDDL_REASON",
    "NormalizedCandidate",
]
