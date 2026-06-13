from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from src.data_collect.adapters.base import GenerationSpec, GeneratorAdapter, GeneratorRejection, GeneratorRunResult, NormalizedCandidate
from src.data_collect.config import CurriculumConfig, DomainConfig, OutputPolicy, SeedRange, SplitConfig, TimeoutConfig
from src.data_collect.generate import REJECTIONS_FILENAME, SUMMARY_FILENAME, orchestrate_generation
from src.data_collect.rendering import FakeRenderer

VALID_DOMAIN_TEMPLATE = """
(define (domain {domain_name})
  (:requirements :strips)
  (:predicates (ok))
)
"""

VALID_PROBLEM_TEMPLATE = """
(define (problem {problem_name})
  (:domain {domain_name})
  (:objects {objects})
  (:init (ok))
  (:goal (and (ok)))
)
"""


@dataclass(frozen=True)
class AttemptPlan:
    mode: str
    object_count: int = 1
    variant: str = "v1"


class ScriptedAdapter(GeneratorAdapter):
    def __init__(
        self,
        *,
        adapter_id: str,
        generator_dir: Path,
        plans_by_bucket: dict[tuple[str, str], list[AttemptPlan]],
    ) -> None:
        super().__init__(adapter_id=adapter_id, generator_dir=generator_dir)
        self.plans_by_bucket = plans_by_bucket
        self.plan_cursor: dict[tuple[str, str], int] = {}
        self.call_count = 0
        self.seen_preset_ids: list[str] = []
        self.domain_source_path = generator_dir / "source-domain.pddl"

    def prepare(self) -> None:
        self.generator_dir.mkdir(parents=True, exist_ok=True)
        self.domain_source_path.write_text(
            textwrap.dedent(VALID_DOMAIN_TEMPLATE.format(domain_name=self.adapter_id)).strip() + "\n",
            encoding="utf-8",
        )

    def generate_candidate(self, spec: GenerationSpec) -> GeneratorRunResult:
        self.prepare()
        split = str(spec.extra["split"])
        target_bucket = str(spec.extra["target_bucket"])
        self.seen_preset_ids.append(str(spec.extra.get("preset_id", "")))
        plan_key = (split, target_bucket)
        plan_index = self.plan_cursor.get(plan_key, 0)
        plan = self.plans_by_bucket[plan_key][plan_index]
        self.plan_cursor[plan_key] = plan_index + 1
        self.call_count += 1

        spec.output_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = spec.output_dir / "generator.stdout"
        stderr_path = spec.output_dir / "generator.stderr"
        stdout_text = ""
        stderr_text = f"plan={plan.mode}\n"
        problem_paths: tuple[Path, ...] = ()

        if plan.mode == "success":
            problem_path = spec.output_dir / "raw-problem.pddl"
            problem_path.write_text(
                _problem_text(
                    domain_name=self.adapter_id,
                    problem_name=f"{self.adapter_id}-{target_bucket}-{plan.variant}-{plan_index}",
                    object_count=plan.object_count,
                ),
                encoding="utf-8",
            )
            problem_paths = (problem_path,)
        elif plan.mode == "invalid":
            stdout_text = "this is not valid pddl\n"
        else:  # pragma: no cover - defensive
            raise ValueError(f"Unsupported scripted mode: {plan.mode}")

        stdout_path.write_text(stdout_text, encoding="utf-8")
        stderr_path.write_text(stderr_text, encoding="utf-8")
        return GeneratorRunResult(
            candidate_id=spec.candidate_id,
            adapter_id=self.adapter_id,
            output_dir=spec.output_dir,
            command=("scripted", self.adapter_id, split, target_bucket),
            generator_cwd=self.generator_dir,
            stdout=stdout_text,
            stderr=stderr_text,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            exit_code=0,
            timed_out=False,
            duration_seconds=0.01,
            seed=spec.seed,
            domain_path=self.domain_source_path,
            problem_paths=problem_paths,
        )

    def normalize_outputs(self, raw_result: GeneratorRunResult) -> NormalizedCandidate | GeneratorRejection:
        return self.normalize_candidate_output(raw_result)

    def supports_seed(self) -> bool:
        return True


def _problem_text(*, domain_name: str, problem_name: str, object_count: int) -> str:
    objects = " ".join(f"o{index}" for index in range(object_count))
    return textwrap.dedent(
        VALID_PROBLEM_TEMPLATE.format(
            domain_name=domain_name,
            problem_name=problem_name,
            objects=objects,
        )
    ).strip() + "\n"


def _build_curriculum_config(
    tmp_path: Path,
    domain_ids: list[str],
    *,
    split_buckets: dict[str, dict[str, int]] | None = None,
) -> CurriculumConfig:
    render_root = tmp_path / "render_profiles"
    domains = []
    for domain_id in domain_ids:
        generator_dir = tmp_path / "generators" / domain_id
        render_profile_path = render_root / f"{domain_id}.pddl"
        render_profile_path.parent.mkdir(parents=True, exist_ok=True)
        render_profile_path.write_text("(define (animation-profile fake))\n", encoding="utf-8")
        domains.append(
            DomainConfig(
                domain_id=domain_id,
                generator_domain_id=domain_id,
                generator_dir=generator_dir,
                render_profile_path=render_profile_path,
                dependency_group=domain_id,
            )
        )

    resolved_split_buckets = split_buckets or {"train": {"easy": 1, "medium": 1, "hard": 1}}
    return CurriculumConfig(
        config_path=tmp_path / "config.json",
        workspace_root=tmp_path,
        generator_root=tmp_path / "generators",
        manifest_path=tmp_path / "manifest.json",
        dependency_config_path=tmp_path / "dependencies.json",
        require_rendering=True,
        candidate_multiplier=1,
        seed_range=SeedRange(start=0, stop=1000),
        timeouts=TimeoutConfig(generator_seconds=5, render_seconds=5),
        output_policy=OutputPolicy(accepted_dir="accepted", rejected_dir="rejected", summaries_dir="summaries"),
        splits={
            split: SplitConfig(total=sum(buckets.values()), buckets=dict(buckets))
            for split, buckets in resolved_split_buckets.items()
        },
        domains=tuple(domains),
        dependencies={},
    )


def _build_registry(tmp_path: Path, domain_ids: list[str], *, variant: str = "v1") -> dict[str, ScriptedAdapter]:
    registry: dict[str, ScriptedAdapter] = {}
    for domain_id in domain_ids:
        registry[domain_id] = ScriptedAdapter(
            adapter_id=domain_id,
            generator_dir=tmp_path / "generators" / domain_id,
            plans_by_bucket={
                ("train", "easy"): [AttemptPlan(mode="invalid"), AttemptPlan(mode="success", object_count=1, variant=variant)],
                ("train", "medium"): [AttemptPlan(mode="success", object_count=2, variant=variant)],
                ("train", "hard"): [AttemptPlan(mode="success", object_count=3, variant=variant)],
            },
        )
    return registry


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_fake_generation_exact_quotas(tmp_path: Path) -> None:
    domain_ids = ["grid", "snake"]
    curriculum_config = _build_curriculum_config(tmp_path, domain_ids)
    registry = _build_registry(tmp_path, domain_ids)

    result = orchestrate_generation(
        curriculum_config,
        output_root=tmp_path / "dataset",
        renderer=FakeRenderer(frame_count=1),
        max_attempts_per_bucket=2,
        seed=123,
        registry=registry,
    )

    assert result.summary.accepted_total == 6
    assert result.summary.accepted_by_bucket == {"easy": 2, "medium": 2, "hard": 2}
    assert result.summary.accepted_by_split == {"train": 6}
    assert result.summary.domains_completed == 2
    assert result.summary.render_failed_accepted == 0
    assert result.summary.extra["selection"]["grid"]["train"]["selected_counts"] == {"easy": 1, "medium": 1, "hard": 1}
    assert result.summary.extra["selection"]["snake"]["train"]["selected_counts"] == {"easy": 1, "medium": 1, "hard": 1}
    for domain_id in domain_ids:
        for bucket in ("easy", "medium", "hard"):
            instance_dir = tmp_path / "dataset" / domain_id / "train" / bucket / f"{domain_id}-train-{bucket}-0000"
            assert instance_dir.exists()
            payload = _load_json(instance_dir / "result.json")
            assert payload["bucket"] == bucket
            assert payload["difficulty_measured"] == bucket
    rejection_lines = (tmp_path / "dataset" / REJECTIONS_FILENAME).read_text(encoding="utf-8").splitlines()
    assert len(rejection_lines) == 2
    rejection_payload = json.loads(rejection_lines[0])
    assert rejection_payload["rejection_stage"] == "generation"
    assert rejection_payload["rejection_reason"] == "invalid_pddl"


def test_rejections_written_to_jsonl_with_structured_reasons(tmp_path: Path) -> None:
    curriculum_config = _build_curriculum_config(tmp_path, ["grid"])
    registry = _build_registry(tmp_path, ["grid"])

    orchestrate_generation(
        curriculum_config,
        output_root=tmp_path / "dataset",
        renderer=FakeRenderer(frame_count=1),
        max_attempts_per_bucket=2,
        seed=123,
        registry=registry,
    )

    rejections_path = tmp_path / "dataset" / REJECTIONS_FILENAME
    payloads = [json.loads(line) for line in rejections_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert payloads
    first = payloads[0]
    assert first["candidate_id"].startswith("grid-train-easy-attempt-")
    assert first["domain_id"] == "grid"
    assert first["split"] == "train"
    assert first["bucket"] == "easy"
    assert first["rejection_stage"] == "generation"
    assert first["rejection_reason"] == "invalid_pddl"
    assert isinstance(first["details"], dict)


def test_resume_no_duplicates(tmp_path: Path) -> None:
    curriculum_config = _build_curriculum_config(tmp_path, ["grid"])
    registry = _build_registry(tmp_path, ["grid"])

    first = orchestrate_generation(
        curriculum_config,
        output_root=tmp_path / "dataset",
        renderer=FakeRenderer(frame_count=1),
        max_attempts_per_bucket=2,
        seed=123,
        registry=registry,
    )
    first_call_count = registry["grid"].call_count
    second = orchestrate_generation(
        curriculum_config,
        output_root=tmp_path / "dataset",
        renderer=FakeRenderer(frame_count=1),
        max_attempts_per_bucket=2,
        seed=123,
        registry=registry,
    )

    assert first.summary.accepted_total == 3
    assert second.summary.accepted_total == 3
    assert second.summary.resumed_accepted_total == 3
    assert second.summary.duplicate_accepted_problem_hashes == 0
    assert registry["grid"].call_count == first_call_count
    manifest_lines = (tmp_path / "dataset" / "accepted_manifest.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(manifest_lines) == 3


def test_force_overwrites_existing_outputs(tmp_path: Path) -> None:
    curriculum_config = _build_curriculum_config(tmp_path, ["grid"])
    first_registry = _build_registry(tmp_path, ["grid"], variant="v1")
    second_registry = _build_registry(tmp_path, ["grid"], variant="v2")
    output_root = tmp_path / "dataset"

    orchestrate_generation(
        curriculum_config,
        output_root=output_root,
        renderer=FakeRenderer(frame_count=1),
        max_attempts_per_bucket=2,
        seed=123,
        registry=first_registry,
    )
    before_payload = _load_json(output_root / "grid" / "train" / "easy" / "grid-train-easy-0000" / "result.json")

    orchestrate_generation(
        curriculum_config,
        output_root=output_root,
        renderer=FakeRenderer(frame_count=1),
        max_attempts_per_bucket=2,
        seed=123,
        force=True,
        registry=second_registry,
    )
    after_payload = _load_json(output_root / "grid" / "train" / "easy" / "grid-train-easy-0000" / "result.json")

    assert before_payload["normalized_problem_hash"] != after_payload["normalized_problem_hash"]
    assert second_registry["grid"].call_count > 0
    summary_payload = _load_json(output_root / SUMMARY_FILENAME)
    assert summary_payload["resumed_accepted_total"] == 0


def test_orchestrator_passes_target_bucket_as_preset_id(tmp_path: Path) -> None:
    curriculum_config = _build_curriculum_config(tmp_path, ["grid"])
    registry = _build_registry(tmp_path, ["grid"])

    orchestrate_generation(
        curriculum_config,
        output_root=tmp_path / "dataset",
        renderer=FakeRenderer(frame_count=1),
        max_attempts_per_bucket=2,
        seed=123,
        registry=registry,
    )

    assert registry["grid"].seen_preset_ids == ["easy", "easy", "medium", "hard"]


def test_generation_fails_early_when_selected_adapter_is_not_ready(tmp_path: Path) -> None:
    curriculum_config = _build_curriculum_config(tmp_path, ["grid"])
    registry = _build_registry(tmp_path, ["grid"])

    def failing_readiness() -> SimpleNamespace:
        return SimpleNamespace(
            ready=False,
            readiness_failures=(
                SimpleNamespace(
                    code="generator_artifact_missing",
                    message="Generator entrypoint is missing for adapter 'grid'",
                    path=str(tmp_path / "generators" / "grid" / "generate.py"),
                ),
            ),
        )

    registry["grid"].inspect_readiness = failing_readiness  # type: ignore[attr-defined]

    try:
        orchestrate_generation(
            curriculum_config,
            output_root=tmp_path / "dataset",
            renderer=FakeRenderer(frame_count=1),
            max_attempts_per_bucket=2,
            seed=123,
            registry=registry,
        )
    except RuntimeError as error:
        message = str(error)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected generator readiness preflight to fail")

    assert message.startswith("Generator readiness preflight failed:")
    assert "grid: generator_artifact_missing" in message
    assert registry["grid"].call_count == 0
    assert not (tmp_path / "dataset" / "accepted_manifest.jsonl").exists()


def test_split_specific_resume_rejects_hashes_accepted_in_other_splits(tmp_path: Path) -> None:
    curriculum_config = _build_curriculum_config(
        tmp_path,
        ["grid"],
        split_buckets={
            "train": {"easy": 1, "medium": 0, "hard": 0},
            "dev": {"easy": 1, "medium": 0, "hard": 0},
        },
    )
    output_root = tmp_path / "dataset"
    train_registry = {
        "grid": ScriptedAdapter(
            adapter_id="grid",
            generator_dir=tmp_path / "generators" / "grid",
            plans_by_bucket={
                ("train", "easy"): [AttemptPlan(mode="success", object_count=1, variant="shared")],
                ("dev", "easy"): [AttemptPlan(mode="success", object_count=1, variant="shared")],
            },
        )
    }

    train_result = orchestrate_generation(
        curriculum_config,
        output_root=output_root,
        splits=["train"],
        renderer=FakeRenderer(frame_count=1),
        max_attempts_per_bucket=2,
        seed=123,
        registry=train_registry,
    )

    dev_registry = {
        "grid": ScriptedAdapter(
            adapter_id="grid",
            generator_dir=tmp_path / "generators" / "grid",
            plans_by_bucket={
                ("train", "easy"): [AttemptPlan(mode="success", object_count=1, variant="shared")],
                ("dev", "easy"): [
                    AttemptPlan(mode="success", object_count=1, variant="shared"),
                    AttemptPlan(mode="success", object_count=2, variant="dev-unique"),
                ],
            },
        )
    }
    dev_result = orchestrate_generation(
        curriculum_config,
        output_root=output_root,
        splits=["dev"],
        renderer=FakeRenderer(frame_count=1),
        max_attempts_per_bucket=2,
        seed=123,
        registry=dev_registry,
    )

    dedupe_rejections = [
        rejection
        for rejection in dev_result.rejected_candidates
        if rejection.rejection_stage == "dedupe" and rejection.split == "dev"
    ]
    assert train_result.summary.accepted_total == 1
    assert dev_result.summary.accepted_total == 2
    assert dev_result.summary.resumed_accepted_total == 1
    assert dev_result.summary.duplicate_accepted_problem_hashes == 0
    assert dev_result.summary.accepted_by_split == {"dev": 1, "train": 1}
    selection_report = dev_result.summary.extra["selection"]
    assert set(selection_report["grid"]) == {"dev"}
    assert selection_report["grid"]["dev"]["attempt_counts"] == {"easy": 2, "medium": 0, "hard": 0}
    assert selection_report["grid"]["dev"]["pool_size"] == 1
    assert selection_report["grid"]["dev"]["selected_pool_size"] == 1
    assert selection_report["grid"]["dev"]["resumed_only"] is False
    assert len(dedupe_rejections) == 1
    assert dedupe_rejections[0].details["source"] == "accepted_outputs"
    assert dedupe_rejections[0].details["existing_split"] == "train"
    assert dedupe_rejections[0].duplicate_of_instance_id == "grid-train-easy-0000"
    assert len((output_root / "accepted_manifest.jsonl").read_text(encoding="utf-8").splitlines()) == 2
