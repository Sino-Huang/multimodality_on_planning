from __future__ import annotations

import sys
import re
from math import gcd
from itertools import permutations
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from ..config import CurriculumConfig, DomainConfig, EXPECTED_DOMAIN_TO_GENERATOR
from .base import GenerationSpec, GeneratorAdapter, GeneratorRejection, GeneratorRunResult, NormalizedCandidate


@dataclass(frozen=True)
class SeedPolicy:
    supported: bool
    mode: str
    option: str | None
    required: bool
    notes: str


@dataclass(frozen=True)
class ProblemOutputPolicy:
    mode: str
    filename_template: str | None
    notes: str


@dataclass(frozen=True)
class TargetParameterPreset:
    preset_id: str
    command_arguments: tuple[str, ...]
    parameters: dict[str, Any]
    notes: str


@dataclass(frozen=True)
class AdapterMetadata:
    generator_path: str
    prep_command: tuple[str, ...]
    build_commands: tuple[str, ...]
    build_artifact_paths: tuple[str, ...]
    domain_file_source: str
    seed_policy: SeedPolicy
    output_policy: ProblemOutputPolicy
    problem_output_discovery: str
    target_parameter_presets: tuple[TargetParameterPreset, ...]
    build_required: bool
    smoke_supported: bool


@dataclass(frozen=True)
class AdapterReadinessFailure:
    code: str
    message: str
    path: str | None = None


@dataclass(frozen=True)
class AdapterCapability:
    domain_id: str
    generator_domain_id: str
    adapter_id: str | None
    adapter_configured: bool
    ready: bool
    generator_path: str | None
    prep_command: tuple[str, ...]
    build_commands: tuple[str, ...]
    build_artifact_paths: tuple[str, ...]
    domain_file_source: str | None
    seed_policy: SeedPolicy | None
    output_policy: ProblemOutputPolicy | None
    problem_output_discovery: str | None
    target_parameter_presets: tuple[TargetParameterPreset, ...]
    build_required: bool | None
    smoke_supported: bool | None
    readiness_failures: tuple[AdapterReadinessFailure, ...]


@dataclass(frozen=True)
class DomainSelection:
    domain_id: str
    generator_domain_id: str
    generator_dir: Path


@dataclass(frozen=True)
class PreparedCommand:
    command: tuple[str, ...] = ()
    expected_problem_paths: tuple[Path, ...] = ()
    stdout_transform: Callable[[str], str] | None = None
    rejection: GeneratorRejection | None = None


CommandBuilder = Callable[[GenerationSpec], PreparedCommand]


class CurriculumCommandAdapter(GeneratorAdapter):
    def __init__(
        self,
        *,
        adapter_id: str,
        generator_domain_id: str,
        generator_dir: Path,
        metadata: AdapterMetadata,
        command_builder: CommandBuilder,
    ) -> None:
        super().__init__(adapter_id=adapter_id, generator_dir=generator_dir)
        self.generator_domain_id = generator_domain_id
        self.metadata = metadata
        self._command_builder = command_builder

    def prepare(self) -> None:
        return None

    def generate_candidate(self, spec: GenerationSpec) -> GeneratorRunResult:
        prepared = self._command_builder(spec)
        if prepared.rejection is not None:
            return prepared.rejection

        raw_result = self.execute_command(
            spec=spec,
            command=prepared.command,
            cwd=self.generator_dir,
            domain_path=Path(self.metadata.domain_file_source),
            problem_paths=prepared.expected_problem_paths,
        )
        if prepared.stdout_transform is None:
            return raw_result

        transformed_stdout = prepared.stdout_transform(raw_result.stdout)
        raw_result.stdout_path.write_text(transformed_stdout, encoding="utf-8")
        return replace(raw_result, stdout=transformed_stdout)

    def normalize_outputs(self, raw_result: GeneratorRunResult | GeneratorRejection) -> NormalizedCandidate | GeneratorRejection:
        if isinstance(raw_result, GeneratorRejection):
            return raw_result
        return self.normalize_candidate_output(raw_result, domain_source=Path(self.metadata.domain_file_source))

    def supports_seed(self) -> bool:
        return self.metadata.seed_policy.supported

    def inspect_readiness(self) -> AdapterCapability:
        failures: list[AdapterReadinessFailure] = []

        generator_dir = self.generator_dir
        generator_path = Path(self.metadata.generator_path)
        domain_file_source = Path(self.metadata.domain_file_source)
        build_artifact_paths = tuple(Path(path) for path in self.metadata.build_artifact_paths)

        if not generator_dir.exists():
            failures.append(
                AdapterReadinessFailure(
                    code="generator_dir_missing",
                    message=f"Generator directory does not exist for adapter '{self.adapter_id}'",
                    path=str(generator_dir),
                )
            )

        if not generator_path.exists():
            missing_code = "generator_artifact_missing" if self.metadata.build_required else "generator_path_missing"
            message = (
                f"Generator entrypoint is missing for adapter '{self.adapter_id}'; run {list(self.metadata.build_commands)}"
                if self.metadata.build_required and self.metadata.build_commands
                else f"Generator entrypoint is missing for adapter '{self.adapter_id}'"
            )
            failures.append(
                AdapterReadinessFailure(
                    code=missing_code,
                    message=message,
                    path=str(generator_path),
                )
            )

        if not domain_file_source.exists():
            failures.append(
                AdapterReadinessFailure(
                    code="domain_file_missing",
                    message=f"Domain file source is missing for adapter '{self.adapter_id}'",
                    path=str(domain_file_source),
                )
            )

        if self.metadata.build_required:
            for build_artifact in build_artifact_paths:
                if build_artifact == generator_path:
                    continue
                if not build_artifact.exists():
                    failures.append(
                        AdapterReadinessFailure(
                            code="build_artifact_missing",
                            message=f"Required build artifact is missing for adapter '{self.adapter_id}'",
                            path=str(build_artifact),
                        )
                    )

        if self.metadata.smoke_supported and not self.metadata.target_parameter_presets:
            failures.append(
                AdapterReadinessFailure(
                    code="missing_smoke_presets",
                    message=f"Smoke testing is enabled but no parameter presets were defined for adapter '{self.adapter_id}'",
                )
            )

        return AdapterCapability(
            domain_id=self.adapter_id,
            generator_domain_id=self.generator_domain_id,
            adapter_id=self.adapter_id,
            adapter_configured=True,
            ready=not failures,
            generator_path=self.metadata.generator_path,
            prep_command=self.metadata.prep_command,
            build_commands=self.metadata.build_commands,
            build_artifact_paths=self.metadata.build_artifact_paths,
            domain_file_source=self.metadata.domain_file_source,
            seed_policy=self.metadata.seed_policy,
            output_policy=self.metadata.output_policy,
            problem_output_discovery=self.metadata.problem_output_discovery,
            target_parameter_presets=self.metadata.target_parameter_presets,
            build_required=self.metadata.build_required,
            smoke_supported=self.metadata.smoke_supported,
            readiness_failures=tuple(failures),
        )


@dataclass(frozen=True)
class AdapterTemplate:
    generator_relative_path: str
    domain_relative_path: str
    prep_command: tuple[str, ...]
    build_commands: tuple[str, ...]
    build_artifact_relpaths: tuple[str, ...]
    seed_policy: SeedPolicy
    output_policy: ProblemOutputPolicy
    problem_output_discovery: str
    target_parameter_presets: tuple[TargetParameterPreset, ...]
    build_required: bool
    smoke_supported: bool
    command_builder_factory: Callable[[DomainSelection, AdapterMetadata], CommandBuilder]


def build_domain_registry(curriculum_config: CurriculumConfig) -> dict[str, CurriculumCommandAdapter]:
    registry: dict[str, CurriculumCommandAdapter] = {}
    for domain in curriculum_config.domains:
        registry[domain.domain_id] = build_domain_adapter(
            DomainSelection(
                domain_id=domain.domain_id,
                generator_domain_id=domain.generator_domain_id,
                generator_dir=domain.generator_dir,
            )
        )
    return registry


def build_domain_adapter(selection: DomainSelection | DomainConfig) -> CurriculumCommandAdapter:
    resolved_selection = DomainSelection(
        domain_id=selection.domain_id,
        generator_domain_id=selection.generator_domain_id,
        generator_dir=Path(selection.generator_dir).resolve(),
    )

    template = ADAPTER_TEMPLATES.get(resolved_selection.domain_id)
    if template is None:
        raise KeyError(f"No adapter template registered for domain '{resolved_selection.domain_id}'")

    metadata = AdapterMetadata(
        generator_path=str((resolved_selection.generator_dir / template.generator_relative_path).resolve()),
        prep_command=template.prep_command,
        build_commands=template.build_commands,
        build_artifact_paths=tuple(
            str((resolved_selection.generator_dir / relative_path).resolve())
            for relative_path in template.build_artifact_relpaths
        ),
        domain_file_source=str((resolved_selection.generator_dir / template.domain_relative_path).resolve()),
        seed_policy=template.seed_policy,
        output_policy=template.output_policy,
        problem_output_discovery=template.problem_output_discovery,
        target_parameter_presets=template.target_parameter_presets,
        build_required=template.build_required,
        smoke_supported=template.smoke_supported,
    )

    return CurriculumCommandAdapter(
        adapter_id=resolved_selection.domain_id,
        generator_domain_id=resolved_selection.generator_domain_id,
        generator_dir=resolved_selection.generator_dir,
        metadata=metadata,
        command_builder=template.command_builder_factory(resolved_selection, metadata),
    )


def build_adapter_capability_matrix(domains: tuple[DomainSelection, ...]) -> tuple[AdapterCapability, ...]:
    capabilities: list[AdapterCapability] = []
    for domain in domains:
        template = ADAPTER_TEMPLATES.get(domain.domain_id)
        if template is None:
            capabilities.append(
                AdapterCapability(
                    domain_id=domain.domain_id,
                    generator_domain_id=domain.generator_domain_id,
                    adapter_id=None,
                    adapter_configured=False,
                    ready=False,
                    generator_path=None,
                    prep_command=(),
                    build_commands=(),
                    build_artifact_paths=(),
                    domain_file_source=None,
                    seed_policy=None,
                    output_policy=None,
                    problem_output_discovery=None,
                    target_parameter_presets=(),
                    build_required=None,
                    smoke_supported=None,
                    readiness_failures=(
                        AdapterReadinessFailure(
                            code="adapter_missing",
                            message=f"No adapter is registered for configured domain '{domain.domain_id}'",
                        ),
                    ),
                )
            )
            continue

        capabilities.append(build_domain_adapter(domain).inspect_readiness())
    return tuple(capabilities)


def registry_domain_ids() -> tuple[str, ...]:
    return tuple(ADAPTER_TEMPLATES)


def _preset(
    preset_id: str,
    *,
    command_arguments: tuple[str, ...],
    parameters: Mapping[str, Any],
    notes: str,
) -> TargetParameterPreset:
    return TargetParameterPreset(
        preset_id=preset_id,
        command_arguments=command_arguments,
        parameters=dict(parameters),
        notes=notes,
    )


def _make_stdout_builder(
    _selection: DomainSelection,
    metadata: AdapterMetadata,
    *,
    executable_parts: tuple[str, ...],
    seed_prefix: tuple[str, ...] = (),
    seed_suffix: tuple[str, ...] = (),
    seed_transform: Callable[[int], tuple[str, ...]] | None = None,
    stdout_transform: Callable[[str], str] | None = None,
) -> CommandBuilder:
    preset_lookup = {preset.preset_id: preset for preset in metadata.target_parameter_presets}

    def build(spec: GenerationSpec) -> PreparedCommand:
        preset_id = str(spec.extra.get("preset_id", metadata.target_parameter_presets[0].preset_id))
        preset = preset_lookup[preset_id]
        command_parts = [*executable_parts, *preset.command_arguments]

        if spec.seed is not None and metadata.seed_policy.supported:
            if seed_transform is not None:
                command_parts.extend(seed_transform(spec.seed))
            else:
                command_parts.extend(seed_prefix)
                command_parts.append(str(spec.seed))
                command_parts.extend(seed_suffix)

        return PreparedCommand(command=tuple(command_parts), stdout_transform=stdout_transform)

    return build


def _make_seed_first_stdout_builder(
    _selection: DomainSelection,
    metadata: AdapterMetadata,
    *,
    executable_parts: tuple[str, ...],
) -> CommandBuilder:
    preset_lookup = {preset.preset_id: preset for preset in metadata.target_parameter_presets}

    def build(spec: GenerationSpec) -> PreparedCommand:
        preset_id = str(spec.extra.get("preset_id", metadata.target_parameter_presets[0].preset_id))
        preset = preset_lookup[preset_id]
        command_parts = [*executable_parts]
        if spec.seed is not None and metadata.seed_policy.supported:
            command_parts.append(str(spec.seed))
        command_parts.extend(preset.command_arguments)
        return PreparedCommand(command=tuple(command_parts))

    return build


def _make_storage_builder(_selection: DomainSelection, metadata: AdapterMetadata) -> CommandBuilder:
    executable = str(Path(metadata.generator_path))

    def build(spec: GenerationSpec) -> PreparedCommand:
        preset_id = str(spec.extra.get("preset_id", metadata.target_parameter_presets[0].preset_id))
        bucket_attempt_index = int(spec.extra.get("bucket_attempt_index", 0))
        attempt_index = int(spec.extra.get("attempt_index", bucket_attempt_index))
        split = str(spec.extra.get("split", "train"))
        variant = _storage_variant_for_attempt(preset_id, bucket_attempt_index)
        problem_number = _storage_problem_number(split=split, attempt_index=attempt_index, bucket_attempt_index=bucket_attempt_index)
        raw_problem_path = (spec.output_dir / "raw-problem.pddl").resolve()
        command_parts = [
            executable,
            "-p",
            str(problem_number),
            "-o",
            str(variant["containers"]),
            "-c",
            str(variant["crates"]),
            "-n",
            str(variant["hoists"]),
            "-s",
            str(variant["store_areas"]),
            "-d",
            str(variant["depots"]),
        ]
        if spec.seed is not None and metadata.seed_policy.supported:
            command_parts.extend(["-e", str(spec.seed)])
        command_parts.append(str(raw_problem_path))
        return PreparedCommand(command=tuple(command_parts), expected_problem_paths=(raw_problem_path,))

    return build


def _make_sokoban_builder(
    _selection: DomainSelection,
    metadata: AdapterMetadata,
    *,
    executable_parts: tuple[str, ...],
    seed_prefix: tuple[str, ...],
) -> CommandBuilder:
    preset_lookup = {preset.preset_id: preset for preset in metadata.target_parameter_presets}

    def build(spec: GenerationSpec) -> PreparedCommand:
        preset_id = str(spec.extra.get("preset_id", metadata.target_parameter_presets[0].preset_id))
        preset = preset_lookup[preset_id]
        split = str(spec.extra.get("split", "train"))
        bucket_attempt_index = int(spec.extra.get("bucket_attempt_index", 0))
        variant_index = _sokoban_variant_index(split=split, preset_id=preset_id, bucket_attempt_index=bucket_attempt_index)
        command_parts = [*executable_parts, *preset.command_arguments]
        if spec.seed is not None and metadata.seed_policy.supported:
            command_parts.extend(seed_prefix)
            command_parts.append(str(spec.seed))
        return PreparedCommand(
            command=tuple(command_parts),
            stdout_transform=lambda text: _sokoban_template_problem(text, variant_index=variant_index),
        )

    return build


_STORAGE_README_VARIANTS: tuple[dict[str, int], ...] = (
    {"containers": 1, "crates": 1, "hoists": 1, "store_areas": 1, "depots": 1},
    {"containers": 1, "crates": 1, "hoists": 2, "store_areas": 2, "depots": 1},
    {"containers": 1, "crates": 1, "hoists": 3, "store_areas": 3, "depots": 1},
    {"containers": 1, "crates": 2, "hoists": 1, "store_areas": 4, "depots": 1},
    {"containers": 1, "crates": 2, "hoists": 2, "store_areas": 4, "depots": 1},
    {"containers": 1, "crates": 2, "hoists": 3, "store_areas": 4, "depots": 1},
    {"containers": 1, "crates": 3, "hoists": 1, "store_areas": 6, "depots": 1},
    {"containers": 1, "crates": 3, "hoists": 2, "store_areas": 6, "depots": 1},
    {"containers": 1, "crates": 3, "hoists": 3, "store_areas": 6, "depots": 1},
    {"containers": 1, "crates": 4, "hoists": 1, "store_areas": 8, "depots": 1},
    {"containers": 1, "crates": 4, "hoists": 2, "store_areas": 8, "depots": 1},
    {"containers": 1, "crates": 4, "hoists": 3, "store_areas": 8, "depots": 1},
    {"containers": 2, "crates": 5, "hoists": 1, "store_areas": 10, "depots": 2},
    {"containers": 2, "crates": 5, "hoists": 2, "store_areas": 10, "depots": 2},
    {"containers": 2, "crates": 5, "hoists": 3, "store_areas": 10, "depots": 2},
    {"containers": 2, "crates": 6, "hoists": 3, "store_areas": 12, "depots": 2},
    {"containers": 2, "crates": 7, "hoists": 3, "store_areas": 14, "depots": 2},
    {"containers": 2, "crates": 8, "hoists": 3, "store_areas": 16, "depots": 2},
    {"containers": 3, "crates": 9, "hoists": 3, "store_areas": 18, "depots": 3},
)


_STORAGE_BUCKET_VARIANT_START = {"easy": 0, "medium": 6, "hard": 12}
_STORAGE_SPLIT_PROBLEM_NUMBER_OFFSET = {"train": 0, "dev": 10000, "test": 20000}


def _storage_variant_for_attempt(preset_id: str, bucket_attempt_index: int) -> dict[str, int]:
    start = _STORAGE_BUCKET_VARIANT_START.get(preset_id, 0)
    variant = _STORAGE_README_VARIANTS[(start + bucket_attempt_index) % len(_STORAGE_README_VARIANTS)]
    _validate_storage_variant(variant)
    return variant


def _validate_storage_variant(variant: Mapping[str, int]) -> None:
    crates = int(variant["crates"])
    store_areas = int(variant["store_areas"])
    depots = int(variant["depots"])
    hoists = int(variant["hoists"])
    if crates > store_areas or depots > store_areas or hoists > store_areas:
        raise ValueError(f"Invalid storage generator variant violates README constraints: {dict(variant)}")


def _storage_problem_number(*, split: str, attempt_index: int, bucket_attempt_index: int) -> int:
    return _STORAGE_SPLIT_PROBLEM_NUMBER_OFFSET.get(split, 30000) + attempt_index + bucket_attempt_index + 1


def _make_named_object_variant_sweep_builder(
    _selection: DomainSelection,
    metadata: AdapterMetadata,
    *,
    executable_parts: tuple[str, ...],
    bucket_ranges: Mapping[str, tuple[int, int, int]],
    variant_transform: Callable[[str, int, int], str],
) -> CommandBuilder:
    preset_lookup = {preset.preset_id: preset for preset in metadata.target_parameter_presets}

    def build(spec: GenerationSpec) -> PreparedCommand:
        preset_id = str(spec.extra.get("preset_id", metadata.target_parameter_presets[0].preset_id))
        _ = preset_lookup[preset_id]
        start_n, stop_n, variants_per_n = bucket_ranges[preset_id]
        bucket_attempt_index = int(spec.extra.get("bucket_attempt_index", 0))
        n_count = stop_n - start_n + 1
        capacity = n_count * variants_per_n
        if bucket_attempt_index >= capacity:
            stdout_path = spec.output_dir / "generator.stdout"
            stderr_path = spec.output_dir / "generator.stderr"
            spec.output_dir.mkdir(parents=True, exist_ok=True)
            stdout_path.write_text("", encoding="utf-8")
            stderr_path.write_text("", encoding="utf-8")
            return PreparedCommand(
                rejection=GeneratorRejection(
                    candidate_id=spec.candidate_id,
                    adapter_id=metadata.generator_path,
                    rejection_reason="deterministic_variants_exhausted",
                    message=(
                        f"Deterministic variant capacity exhausted for preset {preset_id}: "
                        f"capacity={capacity}, attempt={bucket_attempt_index}"
                    ),
                    generator_command=tuple(str(part) for part in executable_parts),
                    generator_cwd=Path(metadata.generator_path).resolve().parent,
                    stdout_path=stdout_path,
                    stderr_path=stderr_path,
                    seed=spec.seed,
                    details={
                        "preset_id": preset_id,
                        "capacity": capacity,
                        "start_n": start_n,
                        "stop_n": stop_n,
                        "variants_per_n": variants_per_n,
                        "bucket_attempt_index": bucket_attempt_index,
                    },
                )
            )

        n_offset = bucket_attempt_index // variants_per_n
        variant_index = bucket_attempt_index % variants_per_n
        n_value = start_n + n_offset
        command_parts = [*executable_parts, "-n", str(n_value)]

        return PreparedCommand(
            command=tuple(command_parts),
            stdout_transform=(None if variant_index == 0 else lambda text: variant_transform(text, n_value, variant_index)),
        )

    return build


def _rename_problem_tokens(problem_text: str, replacements: Mapping[str, str]) -> str:
    if not replacements:
        return problem_text
    pattern = re.compile(r"\b(" + "|".join(re.escape(token) for token in sorted(replacements, key=len, reverse=True)) + r")\b")
    return pattern.sub(lambda match: replacements[match.group(0)], problem_text)


def _strip_before_define(problem_text: str) -> str:
    define_index = problem_text.find("(define")
    return problem_text[define_index:] if define_index >= 0 else problem_text


def _cyclic_permutation(tokens: list[str], shift: int) -> dict[str, str]:
    if not tokens:
        return {}
    rotation = shift % len(tokens)
    rotated = tokens[rotation:] + tokens[:rotation]
    return dict(zip(tokens, rotated, strict=True))


def _gripper_named_variant(problem_text: str, n_value: int, variant_index: int) -> str:
    balls = [f"ball{i}" for i in range(1, n_value + 1)]
    ball_shift = variant_index % n_value
    remainder = variant_index // n_value
    room_shift = remainder % 2
    remainder //= 2
    gripper_shift = remainder % 2

    replacements: dict[str, str] = {}
    replacements.update(_cyclic_permutation(balls, ball_shift))
    if room_shift:
        replacements.update({"rooma": "roomb", "roomb": "rooma"})
    if gripper_shift:
        replacements.update({"left": "right", "right": "left"})
    return _rename_problem_tokens(problem_text, replacements)


_PEG_PERMUTATIONS = tuple(permutations(("peg1", "peg2", "peg3")))


def _hanoi_named_variant(problem_text: str, n_value: int, variant_index: int) -> str:
    discs = [f"d{i}" for i in range(1, n_value + 1)]
    disc_steps = [step for step in range(1, n_value + 1) if gcd(step, n_value) == 1]
    disc_variant_space = n_value * len(disc_steps)
    disc_variant_index = variant_index % disc_variant_space
    disc_shift = disc_variant_index % n_value
    disc_step = disc_steps[disc_variant_index // n_value]
    remainder = variant_index // disc_variant_space
    peg_permutation = _PEG_PERMUTATIONS[remainder % len(_PEG_PERMUTATIONS)]

    replacements: dict[str, str] = {}
    target_discs = [discs[(disc_shift + (index * disc_step)) % n_value] for index in range(n_value)]
    replacements.update(dict(zip(discs, target_discs, strict=True)))
    replacements.update(dict(zip(("peg1", "peg2", "peg3"), peg_permutation, strict=True)))
    return _rename_problem_tokens(problem_text, replacements)


def _sokoban_template_problem(problem_text: str, variant_index: int = 0) -> str:
    source = _strip_before_define(problem_text)
    raw_problem_name = _first_match(r"\(define\s+\(problem\s+([^\s\)]+)", source, "sokoban-generated")
    problem_name = _sokoban_safe_symbol(f"{raw_problem_name}-v{variant_index}")
    object_section = _section_between(source, "(:objects", "(:init")
    init_section = _section_between(source, "(:init", "(:goal")
    goal_section = _section_between(source, "(:goal", None)

    typed_objects = _parse_typed_object_section(object_section)
    positions = typed_objects.get("LOC", ())
    boxes = typed_objects.get("BOX", ())
    if not positions or not boxes:
        return source.replace("(:domain typed-sokoban)", "(:domain template)").replace("(:domain sokoban-typed)", "(:domain template)")

    row_offset, column_offset = _sokoban_position_offsets(variant_index)
    position_map = {
        position: _sokoban_position_symbol(position, row_offset=row_offset, column_offset=column_offset)
        for position in positions
    }
    box_map = {box: f"blk{index}" for index, box in enumerate(boxes, start=1)}

    directions = [
        (src, dst, direction)
        for src, dst, direction in re.findall(r"\(adjacent\s+([^\s\)]+)\s+([^\s\)]+)\s+(up|down|left|right)\)", init_section)
    ]
    robot_locations = re.findall(r"\(at-robot\s+([^\s\)]+)\)", init_section)
    box_locations = re.findall(r"\(at\s+([^\s\)]+)\s+([^\s\)]+)\)", init_section)
    goal_locations = re.findall(r"\(at\s+([^\s\)]+)\s+([^\s\)]+)\)", goal_section)

    button_names = [f"but{index}" for index, _goal in enumerate(goal_locations or box_locations, start=1)]
    init_facts: list[str] = []
    init_facts.extend(f"        (position {position_map[position]})" for position in positions)
    init_facts.extend(f"        ({direction} {position_map[src]} {position_map[dst]})" for src, dst, direction in directions)
    if robot_locations:
        init_facts.append(f"        (at ply1 {position_map[robot_locations[0]]})")
    init_facts.extend(f"        (at {box_map[box]} {position_map[location]})" for box, location in box_locations)
    init_facts.extend(
        f"        (at {button} {position_map[location]})"
        for button, (_box, location) in zip(button_names, goal_locations or box_locations, strict=False)
    )

    button_object_line = f"        {' '.join(button_names)} - button\n" if button_names else ""
    return (
        f"(define (problem {problem_name})\n"
        "    (:domain template)\n"
        "    (:objects\n"
        f"        {' '.join(position_map[position] for position in positions)} - pos\n"
        "        ply1 - player\n"
        f"        {' '.join(box_map[box] for box in boxes)} - block\n"
        f"{button_object_line}"
        "    )\n"
        "    (:init\n"
        + "\n".join(init_facts)
        + "\n    )\n"
        "    (:goal\n"
        "        (forall (?but - button)\n"
        "            (exists (?blk - block)\n"
        "                (exists (?pos - pos)\n"
        "                    (and\n"
        "                        (at ?but ?pos)\n"
        "                        (at ?blk ?pos)\n"
        "                    )\n"
        "                )\n"
        "            )\n"
        "        )\n"
        "    )\n"
        ")\n"
    )


def _first_match(pattern: str, text: str, default: str) -> str:
    match = re.search(pattern, text)
    return match.group(1) if match else default


_SOKOBAN_SPLIT_VARIANT_OFFSETS = {"train": 0, "dev": 10_000, "test": 20_000}
_SOKOBAN_PRESET_VARIANT_OFFSETS = {"easy": 0, "medium": 3_000, "hard": 6_000}


def _sokoban_variant_index(*, split: str, preset_id: str, bucket_attempt_index: int) -> int:
    return (
        _SOKOBAN_SPLIT_VARIANT_OFFSETS.get(split, 30_000)
        + _SOKOBAN_PRESET_VARIANT_OFFSETS.get(preset_id, 9_000)
        + bucket_attempt_index
    )


def _sokoban_position_offsets(variant_index: int) -> tuple[int, int]:
    row_offset = (variant_index % 1_000) * 10
    column_offset = (variant_index // 1_000) * 10
    return row_offset, column_offset


def _sokoban_position_symbol(raw_symbol: str, *, row_offset: int = 0, column_offset: int = 0) -> str:
    match = re.fullmatch(r"f(\d+)-(\d+)f", raw_symbol)
    if match:
        return f"pos{int(match.group(1)) + 1 + row_offset}_{int(match.group(2)) + 1 + column_offset}"
    return _sokoban_safe_symbol(raw_symbol)


def _sokoban_safe_symbol(raw_symbol: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_]", "_", raw_symbol)
    if not safe or safe[0].isdigit():
        safe = f"s_{safe}"
    return safe


def _section_between(text: str, start_marker: str, end_marker: str | None) -> str:
    start = text.find(start_marker)
    if start < 0:
        return ""
    start += len(start_marker)
    end = text.find(end_marker, start) if end_marker is not None else len(text)
    if end < 0:
        end = len(text)
    return text[start:end]


def _parse_typed_object_section(object_section: str) -> dict[str, tuple[str, ...]]:
    parsed: dict[str, list[str]] = {}
    pending: list[str] = []
    tokens = object_section.replace("(", " ").replace(")", " ").split()
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "-" and index + 1 < len(tokens):
            type_name = tokens[index + 1]
            parsed.setdefault(type_name, []).extend(pending)
            pending = []
            index += 2
            continue
        pending.append(token)
        index += 1
    if pending:
        parsed.setdefault("object", []).extend(pending)
    return {type_name: tuple(values) for type_name, values in parsed.items()}


ADAPTER_TEMPLATES: dict[str, AdapterTemplate] = {
    "15puzzle": AdapterTemplate(
        generator_relative_path="n-puzzle-generator",
        domain_relative_path="domain.pddl",
        prep_command=(),
        build_commands=("make",),
        build_artifact_relpaths=("n-puzzle-generator",),
        seed_policy=SeedPolicy(supported=True, mode="flag", option="-s", required=True, notes="Seed is required via -s."),
        output_policy=ProblemOutputPolicy(mode="stdout", filename_template=None, notes="Generator prints exactly one problem to stdout."),
        problem_output_discovery="Normalize the single stdout payload as the problem PDDL.",
        target_parameter_presets=(
            _preset("easy", command_arguments=("-n", "3"), parameters={"board_size": 3}, notes="3x3 sliding puzzle."),
            _preset("medium", command_arguments=("-n", "4"), parameters={"board_size": 4}, notes="4x4 sliding puzzle."),
            _preset("hard", command_arguments=("-n", "4"), parameters={"board_size": 4}, notes="4x4 sliding puzzle reserved for the measured-hard tail because 5x5 uploads are too unstable for rendered curriculum generation."),
        ),
        build_required=True,
        smoke_supported=True,
        command_builder_factory=lambda selection, metadata: _make_stdout_builder(
            selection,
            metadata,
            executable_parts=(str(Path(metadata.generator_path)),),
            seed_prefix=("-s",),
        ),
    ),
    "blocksworld": AdapterTemplate(
        generator_relative_path="blocksworld",
        domain_relative_path="4ops/domain.pddl",
        prep_command=("make", "4ops"),
        build_commands=("make", "4ops"),
        build_artifact_relpaths=("bwstates.1/bwstates", "4ops/2pddl/2pddl"),
        seed_policy=SeedPolicy(supported=True, mode="positional", option=None, required=True, notes="Seed is the third positional argument after operator count and block count."),
        output_policy=ProblemOutputPolicy(mode="stdout", filename_template=None, notes="The shell wrapper emits one problem to stdout."),
        problem_output_discovery="Normalize the stdout payload produced by the shell wrapper.",
        target_parameter_presets=(
            _preset("easy", command_arguments=("4", "4"), parameters={"operators": 4, "blocks": 4}, notes="4-operator encoding with 4 blocks."),
            _preset("medium", command_arguments=("4", "8"), parameters={"operators": 4, "blocks": 8}, notes="4-operator encoding with 8 blocks."),
            _preset("hard", command_arguments=("4", "12"), parameters={"operators": 4, "blocks": 12}, notes="4-operator encoding with 12 blocks."),
        ),
        build_required=True,
        smoke_supported=True,
        command_builder_factory=lambda selection, metadata: _make_stdout_builder(
            selection,
            metadata,
            executable_parts=(str(Path(metadata.generator_path)),),
            seed_transform=lambda seed: (str(seed),),
        ),
    ),
    "depot": AdapterTemplate(
        generator_relative_path="depots",
        domain_relative_path="domain.pddl",
        prep_command=(),
        build_commands=("make",),
        build_artifact_relpaths=("depots",),
        seed_policy=SeedPolicy(supported=True, mode="flag", option="-s", required=False, notes="Optional random seed via -s."),
        output_policy=ProblemOutputPolicy(mode="stdout", filename_template=None, notes="Generator prints one problem to stdout."),
        problem_output_discovery="Normalize the single stdout payload as the problem PDDL.",
        target_parameter_presets=(
            _preset("easy", command_arguments=("-e", "1", "-i", "2", "-t", "2", "-p", "3", "-h", "3", "-c", "3"), parameters={"depots": 1, "distributors": 2, "trucks": 2, "pallets": 3, "hoists": 3, "crates": 3}, notes="Small depots instance."),
            _preset("medium", command_arguments=("-e", "2", "-i", "3", "-t", "3", "-p", "5", "-h", "4", "-c", "5"), parameters={"depots": 2, "distributors": 3, "trucks": 3, "pallets": 5, "hoists": 4, "crates": 5}, notes="Mid-sized depots instance."),
            _preset("hard", command_arguments=("-e", "3", "-i", "4", "-t", "4", "-p", "8", "-h", "6", "-c", "8"), parameters={"depots": 3, "distributors": 4, "trucks": 4, "pallets": 8, "hoists": 6, "crates": 8}, notes="Larger depots instance."),
        ),
        build_required=True,
        smoke_supported=True,
        command_builder_factory=lambda selection, metadata: _make_stdout_builder(
            selection,
            metadata,
            executable_parts=(str(Path(metadata.generator_path)),),
            seed_prefix=("-s",),
        ),
    ),
    "driverlog": AdapterTemplate(
        generator_relative_path="dlgen",
        domain_relative_path="domain.pddl",
        prep_command=(),
        build_commands=("make",),
        build_artifact_relpaths=("dlgen",),
        seed_policy=SeedPolicy(supported=True, mode="positional", option=None, required=True, notes="Seed is the first positional argument after any mode flags."),
        output_policy=ProblemOutputPolicy(mode="stdout", filename_template=None, notes="Generator prints one problem to stdout."),
        problem_output_discovery="Normalize the single stdout payload as the problem PDDL.",
        target_parameter_presets=(
            _preset("easy", command_arguments=("5", "2", "2", "2"), parameters={"junctions": 5, "drivers": 2, "packages": 2, "trucks": 2}, notes="Matches the Makefile smoke scale."),
            _preset("medium", command_arguments=("8", "3", "4", "3"), parameters={"junctions": 8, "drivers": 3, "packages": 4, "trucks": 3}, notes="Moderate driverlog instance."),
            _preset("hard", command_arguments=("12", "4", "6", "4", "8"), parameters={"junctions": 12, "drivers": 4, "packages": 6, "trucks": 4, "distance": 8}, notes="Larger instance with randomized edge distances."),
        ),
        build_required=True,
        smoke_supported=True,
        command_builder_factory=lambda selection, metadata: _make_seed_first_stdout_builder(
            selection,
            metadata,
            executable_parts=(str(Path(metadata.generator_path)),),
        ),
    ),
    "elevators": AdapterTemplate(
        generator_relative_path="miconic",
        domain_relative_path="domain.pddl",
        prep_command=(),
        build_commands=("make",),
        build_artifact_relpaths=("miconic",),
        seed_policy=SeedPolicy(supported=True, mode="flag", option="-r", required=False, notes="Optional random seed via -r."),
        output_policy=ProblemOutputPolicy(mode="stdout", filename_template=None, notes="Miconic generator prints one problem to stdout."),
        problem_output_discovery="Normalize the single stdout payload from the Miconic generator as the problem PDDL.",
        target_parameter_presets=(
            _preset("easy", command_arguments=("-f", "4", "-p", "2"), parameters={"floors": 4, "passengers": 2}, notes="Small Miconic instance matching the Planimation elevators sample shape."),
            _preset("medium", command_arguments=("-f", "8", "-p", "4"), parameters={"floors": 8, "passengers": 4}, notes="Moderate Miconic instance."),
            _preset("hard", command_arguments=("-f", "12", "-p", "6"), parameters={"floors": 12, "passengers": 6}, notes="Larger Miconic instance."),
        ),
        build_required=True,
        smoke_supported=True,
        command_builder_factory=lambda selection, metadata: _make_stdout_builder(
            selection,
            metadata,
            executable_parts=(str(Path(metadata.generator_path)),),
            seed_prefix=("-r",),
        ),
    ),
    "ferry": AdapterTemplate(
        generator_relative_path="ferry",
        domain_relative_path="domain.pddl",
        prep_command=(),
        build_commands=("make",),
        build_artifact_relpaths=("ferry",),
        seed_policy=SeedPolicy(supported=True, mode="flag", option="-s", required=False, notes="Optional random seed via -s."),
        output_policy=ProblemOutputPolicy(mode="stdout", filename_template=None, notes="Generator prints one problem to stdout."),
        problem_output_discovery="Normalize the single stdout payload as the problem PDDL.",
        target_parameter_presets=(
            _preset("easy", command_arguments=("-l", "3", "-c", "2"), parameters={"locations": 3, "cars": 2}, notes="Small ferry instance."),
            _preset("medium", command_arguments=("-l", "5", "-c", "4"), parameters={"locations": 5, "cars": 4}, notes="Moderate ferry instance."),
            _preset("hard", command_arguments=("-l", "7", "-c", "6"), parameters={"locations": 7, "cars": 6}, notes="Larger ferry instance."),
        ),
        build_required=True,
        smoke_supported=True,
        command_builder_factory=lambda selection, metadata: _make_stdout_builder(
            selection,
            metadata,
            executable_parts=(str(Path(metadata.generator_path)),),
            seed_prefix=("-s",),
        ),
    ),
    "freecell": AdapterTemplate(
        generator_relative_path="freecell",
        domain_relative_path="domain.pddl",
        prep_command=(),
        build_commands=("make",),
        build_artifact_relpaths=("freecell",),
        seed_policy=SeedPolicy(supported=True, mode="flag", option="-r", required=False, notes="Optional random seed via -r."),
        output_policy=ProblemOutputPolicy(mode="stdout", filename_template=None, notes="Generator prints one problem to stdout."),
        problem_output_discovery="Normalize the single stdout payload as the problem PDDL.",
        target_parameter_presets=(
            _preset("easy", command_arguments=("-f", "2", "-c", "2", "-s", "2", "-0", "2", "-1", "2", "-i", "1"), parameters={"freecells": 2, "columns": 2, "suits": 2, "cards_per_suit": [2, 2], "initial_stacks": 1}, notes="Small Freecell instance."),
            _preset("medium", command_arguments=("-f", "4", "-c", "4", "-s", "4", "-0", "3", "-1", "3", "-2", "3", "-3", "3", "-i", "2"), parameters={"freecells": 4, "columns": 4, "suits": 4, "cards_per_suit": [3, 3, 3, 3], "initial_stacks": 2}, notes="Balanced 4-suit Freecell instance."),
            _preset("hard", command_arguments=("-f", "4", "-c", "6", "-s", "4", "-0", "5", "-1", "5", "-2", "5", "-3", "5", "-i", "4"), parameters={"freecells": 4, "columns": 6, "suits": 4, "cards_per_suit": [5, 5, 5, 5], "initial_stacks": 4}, notes="Larger Freecell instance."),
        ),
        build_required=True,
        smoke_supported=True,
        command_builder_factory=lambda selection, metadata: _make_stdout_builder(
            selection,
            metadata,
            executable_parts=(str(Path(metadata.generator_path)),),
            seed_prefix=("-r",),
        ),
    ),
    "grid": AdapterTemplate(
        generator_relative_path="generate.py",
        domain_relative_path="domain.pddl",
        prep_command=(),
        build_commands=(),
        build_artifact_relpaths=(),
        seed_policy=SeedPolicy(supported=True, mode="flag", option="--seed", required=False, notes="Python generator accepts --seed."),
        output_policy=ProblemOutputPolicy(mode="stdout", filename_template=None, notes="Python generator prints one problem to stdout."),
        problem_output_discovery="Normalize the single stdout payload from generate.py as the problem PDDL.",
        target_parameter_presets=(
            _preset("easy", command_arguments=("4", "4", "--shapes", "2", "--keys", "2", "--locks", "2", "--prob-goal", "0.5"), parameters={"x": 4, "y": 4, "shapes": 2, "keys": 2, "locks": 2, "prob_goal": 0.5}, notes="Small grid instance."),
            _preset("medium", command_arguments=("5", "5", "--shapes", "3", "--keys", "4", "--locks", "4", "--prob-goal", "0.6"), parameters={"x": 5, "y": 5, "shapes": 3, "keys": 4, "locks": 4, "prob_goal": 0.6}, notes="Moderate grid instance."),
            _preset("hard", command_arguments=("6", "6", "--shapes", "4", "--keys", "6", "--locks", "6", "--prob-goal", "0.75"), parameters={"x": 6, "y": 6, "shapes": 4, "keys": 6, "locks": 6, "prob_goal": 0.75}, notes="Larger grid instance."),
        ),
        build_required=False,
        smoke_supported=True,
        command_builder_factory=lambda selection, metadata: _make_stdout_builder(
            selection,
            metadata,
            executable_parts=(sys.executable, str(Path(metadata.generator_path))),
            seed_prefix=("--seed",),
        ),
    ),
    "gripper": AdapterTemplate(
        generator_relative_path="gripper",
        domain_relative_path="domain.pddl",
        prep_command=(),
        build_commands=("make",),
        build_artifact_relpaths=("gripper",),
        seed_policy=SeedPolicy(supported=False, mode="unsupported", option=None, required=False, notes="Generator is deterministic and does not accept a seed."),
        output_policy=ProblemOutputPolicy(mode="stdout", filename_template=None, notes="Generator prints one problem to stdout."),
        problem_output_discovery="Normalize the single stdout payload as the problem PDDL.",
        target_parameter_presets=(
            _preset("easy", command_arguments=("-n", "3"), parameters={"balls_start": 3, "balls_stop": 13, "variants_per_n": 8}, notes="Deterministic sweep over 3-13 balls with init-order variants for easy gripper instances."),
            _preset("medium", command_arguments=("-n", "14"), parameters={"balls_start": 14, "balls_stop": 25, "variants_per_n": 8}, notes="Deterministic sweep over 14-25 balls with init-order variants for medium gripper instances."),
            _preset("hard", command_arguments=("-n", "26"), parameters={"balls_start": 26, "balls_stop": 33, "variants_per_n": 8}, notes="Deterministic sweep over 26-33 balls with init-order variants for hard gripper instances."),
        ),
        build_required=True,
        smoke_supported=True,
        command_builder_factory=lambda selection, metadata: _make_named_object_variant_sweep_builder(
            selection,
            metadata,
            executable_parts=(str(Path(metadata.generator_path)),),
            bucket_ranges={
                "easy": (3, 13, 12),
                "medium": (14, 25, 12),
                "hard": (26, 33, 12),
            },
            variant_transform=_gripper_named_variant,
        ),
    ),
    "logistics": AdapterTemplate(
        generator_relative_path="logistics",
        domain_relative_path="domain.pddl",
        prep_command=(),
        build_commands=("make",),
        build_artifact_relpaths=("logistics",),
        seed_policy=SeedPolicy(supported=True, mode="flag", option="-r", required=False, notes="Optional random seed via -r."),
        output_policy=ProblemOutputPolicy(mode="stdout", filename_template=None, notes="Generator prints one problem to stdout."),
        problem_output_discovery="Normalize the single stdout payload as the problem PDDL.",
        target_parameter_presets=(
            _preset("easy", command_arguments=("-a", "1", "-c", "2", "-s", "2", "-p", "2", "-t", "2"), parameters={"airplanes": 1, "cities": 2, "city_size": 2, "packages": 2, "trucks": 2}, notes="Matches the Makefile smoke scale with explicit trucks."),
            _preset("medium", command_arguments=("-a", "1", "-c", "3", "-s", "3", "-p", "4", "-t", "3"), parameters={"airplanes": 1, "cities": 3, "city_size": 3, "packages": 4, "trucks": 3}, notes="Moderate logistics instance."),
            _preset("hard", command_arguments=("-a", "2", "-c", "4", "-s", "4", "-p", "8", "-t", "4"), parameters={"airplanes": 2, "cities": 4, "city_size": 4, "packages": 8, "trucks": 4}, notes="Larger logistics instance."),
        ),
        build_required=True,
        smoke_supported=True,
        command_builder_factory=lambda selection, metadata: _make_stdout_builder(
            selection,
            metadata,
            executable_parts=(str(Path(metadata.generator_path)),),
            seed_prefix=("-r",),
        ),
    ),
    "snake": AdapterTemplate(
        generator_relative_path="generate.py",
        domain_relative_path="domain.pddl",
        prep_command=(),
        build_commands=(),
        build_artifact_relpaths=(),
        seed_policy=SeedPolicy(supported=True, mode="positional", option=None, required=True, notes="Seed is the fifth positional argument before the output-type selector."),
        output_policy=ProblemOutputPolicy(mode="stdout", filename_template=None, notes="Python generator prints one problem to stdout when output type is pddl."),
        problem_output_discovery="Normalize the single stdout payload from generate.py when invoked with output_type=pddl.",
        target_parameter_presets=(
            _preset("easy", command_arguments=("empty-6x6", "2", "1", "1"), parameters={"board": "empty-6x6", "snake_size": 2, "initial_apples": 1, "spawn_apples": 1}, notes="Empty 6x6 board with one spawn apple."),
            _preset("medium", command_arguments=("boards/obstacles-6x6.txt", "3", "1", "2"), parameters={"board": "boards/obstacles-6x6.txt", "snake_size": 3, "initial_apples": 1, "spawn_apples": 2}, notes="Obstacle board with a slightly longer snake."),
            _preset("hard", command_arguments=("boards/obstacles-8x8.txt", "4", "2", "20%"), parameters={"board": "boards/obstacles-8x8.txt", "snake_size": 4, "initial_apples": 2, "spawn_apples": "20%"}, notes="Larger obstacle board with percentage-based spawn apples."),
        ),
        build_required=False,
        smoke_supported=True,
        command_builder_factory=lambda selection, metadata: _make_stdout_builder(
            selection,
            metadata,
            executable_parts=(sys.executable, str(Path(metadata.generator_path))),
            seed_transform=lambda seed: (str(seed), "pddl"),
        ),
    ),
    "sokoban": AdapterTemplate(
        generator_relative_path="random/sokoban-generator-typed",
        domain_relative_path="../../../data/pddl_instances/sokoban/domain.pddl",
        prep_command=("make", "random"),
        build_commands=("make", "random"),
        build_artifact_relpaths=("random/sokoban-generator-typed",),
        seed_policy=SeedPolicy(supported=True, mode="flag", option="-s", required=False, notes="Optional random seed via -s."),
        output_policy=ProblemOutputPolicy(mode="stdout", filename_template=None, notes="Typed Sokoban generator prints one problem to stdout."),
        problem_output_discovery="Normalize the single stdout payload produced by the typed random generator.",
        target_parameter_presets=(
            _preset("easy", command_arguments=("-n", "5", "-b", "1", "-w", "0"), parameters={"grid_size": 5, "boxes": 1, "walls": 0}, notes="Render-compatible one-box Sokoban instance."),
            _preset("medium", command_arguments=("-n", "5", "-b", "1", "-w", "0"), parameters={"grid_size": 5, "boxes": 1, "walls": 0}, notes="Render-compatible one-box Sokoban instance; measured percentile selection assigns final bucket."),
            _preset("hard", command_arguments=("-n", "5", "-b", "1", "-w", "0"), parameters={"grid_size": 5, "boxes": 1, "walls": 0}, notes="Render-compatible one-box Sokoban instance; measured percentile selection assigns final bucket."),
        ),
        build_required=True,
        smoke_supported=True,
        command_builder_factory=lambda selection, metadata: _make_sokoban_builder(
            selection,
            metadata,
            executable_parts=(str(Path(metadata.generator_path)),),
            seed_prefix=("-s",),
        ),
    ),
    "storage": AdapterTemplate(
        generator_relative_path="storage",
        domain_relative_path="domain.pddl",
        prep_command=("make", "generator"),
        build_commands=("make", "generator"),
        build_artifact_relpaths=("storage",),
        seed_policy=SeedPolicy(supported=True, mode="flag", option="-e", required=False, notes="Optional random seed via -e; the binary falls back to time(0) otherwise."),
        output_policy=ProblemOutputPolicy(mode="named_file", filename_template="raw-problem.pddl", notes="Generator writes exactly one problem to the output filename argument."),
        problem_output_discovery="Normalize the named file passed as the final CLI argument.",
        target_parameter_presets=(
            _preset("easy", command_arguments=("-p", "01", "-o", "1", "-c", "1", "-n", "1", "-s", "1", "-d", "1"), parameters={"problem_number": 1, "containers": 1, "crates": 1, "hoists": 1, "store_areas": 1, "depots": 1}, notes="Matches the Makefile smoke scale."),
            _preset("medium", command_arguments=("-p", "02", "-o", "2", "-c", "4", "-n", "2", "-s", "8", "-d", "2"), parameters={"problem_number": 2, "containers": 2, "crates": 4, "hoists": 2, "store_areas": 8, "depots": 2}, notes="Moderate storage instance."),
            _preset("hard", command_arguments=("-p", "03", "-o", "3", "-c", "9", "-n", "3", "-s", "18", "-d", "3"), parameters={"problem_number": 3, "containers": 3, "crates": 9, "hoists": 3, "store_areas": 18, "depots": 3}, notes="Larger storage instance."),
        ),
        build_required=True,
        smoke_supported=True,
        command_builder_factory=_make_storage_builder,
    ),
    "towers_of_hanoi": AdapterTemplate(
        generator_relative_path="hanoi",
        domain_relative_path="domain.pddl",
        prep_command=(),
        build_commands=("make",),
        build_artifact_relpaths=("hanoi",),
        seed_policy=SeedPolicy(supported=False, mode="unsupported", option=None, required=False, notes="Generator is deterministic and does not accept a seed."),
        output_policy=ProblemOutputPolicy(mode="stdout", filename_template=None, notes="Generator prints one problem to stdout."),
        problem_output_discovery="Normalize the single stdout payload as the problem PDDL.",
        target_parameter_presets=(
            _preset("easy", command_arguments=("-n", "3"), parameters={"discs_start": 3, "discs_stop": 5, "variants_per_n": 36}, notes="Deterministic sweep over 3-5 discs with render-safe object-renaming variants for easy Hanoi instances."),
            _preset("medium", command_arguments=("-n", "6"), parameters={"discs_start": 6, "discs_stop": 7, "variants_per_n": 48}, notes="Deterministic sweep over 6-7 discs with render-safe object-renaming variants for medium Hanoi instances."),
            _preset("hard", command_arguments=("-n", "8"), parameters={"discs_start": 8, "discs_stop": 9, "variants_per_n": 48}, notes="Deterministic sweep over 8-9 discs with render-safe object-renaming variants for hard Hanoi instances."),
        ),
        build_required=True,
        smoke_supported=True,
        command_builder_factory=lambda selection, metadata: _make_named_object_variant_sweep_builder(
            selection,
            metadata,
            executable_parts=(str(Path(metadata.generator_path)),),
            bucket_ranges={
                "easy": (3, 5, 36),
                "medium": (6, 7, 48),
                "hard": (8, 9, 48),
            },
            variant_transform=_hanoi_named_variant,
        ),
    ),
    "visitall": AdapterTemplate(
        generator_relative_path="grid",
        domain_relative_path="domain.pddl",
        prep_command=(),
        build_commands=("make",),
        build_artifact_relpaths=("grid",),
        seed_policy=SeedPolicy(supported=True, mode="flag", option="-s", required=False, notes="Optional random seed via -s."),
        output_policy=ProblemOutputPolicy(mode="stdout", filename_template=None, notes="Generator prints one problem to stdout."),
        problem_output_discovery="Normalize the single stdout payload as the problem PDDL.",
        target_parameter_presets=(
            _preset("easy", command_arguments=("-n", "5", "-r", "0.5", "-u", "0"), parameters={"grid_size": 5, "goal_ratio": 0.5, "unavailable": 0}, notes="Half-goal 5x5 instance."),
            _preset("medium", command_arguments=("-n", "8", "-r", "1", "-u", "4"), parameters={"grid_size": 8, "goal_ratio": 1.0, "unavailable": 4}, notes="Full-goal 8x8 instance with holes."),
            _preset("hard", command_arguments=("-n", "12", "-r", "1", "-u", "12"), parameters={"grid_size": 12, "goal_ratio": 1.0, "unavailable": 12}, notes="Larger full-goal instance with more unavailable cells."),
        ),
        build_required=True,
        smoke_supported=True,
        command_builder_factory=lambda selection, metadata: _make_stdout_builder(
            selection,
            metadata,
            executable_parts=(str(Path(metadata.generator_path)),),
            seed_prefix=("-s",),
            stdout_transform=_strip_before_define,
        ),
    ),
}


if tuple(ADAPTER_TEMPLATES) != tuple(EXPECTED_DOMAIN_TO_GENERATOR):
    raise RuntimeError(
        "Adapter registry domains must exactly match the curriculum config domain order: "
        f"expected {tuple(EXPECTED_DOMAIN_TO_GENERATOR)}, got {tuple(ADAPTER_TEMPLATES)}"
    )


__all__ = [
    "AdapterCapability",
    "AdapterMetadata",
    "AdapterReadinessFailure",
    "CurriculumCommandAdapter",
    "DomainSelection",
    "PreparedCommand",
    "ProblemOutputPolicy",
    "SeedPolicy",
    "TargetParameterPreset",
    "build_adapter_capability_matrix",
    "build_domain_adapter",
    "build_domain_registry",
    "registry_domain_ids",
]
