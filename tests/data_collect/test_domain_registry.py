from __future__ import annotations

from pathlib import Path

from src.data_collect.adapters import build_domain_adapter, build_domain_registry, registry_domain_ids
from src.data_collect.adapters.base import GenerationSpec
from src.data_collect.config import EXPECTED_DOMAIN_TO_GENERATOR, load_curriculum_config
from src.data_collect.hashing import build_pddl_hash_info


def _typed_sokoban_problem() -> str:
    return """
    ; generator diagnostics
    (define (problem typed-sokoban-grid5-boxes1-walls0)
    (:domain typed-sokoban)
    (:objects
        up down left right - DIR
        box0 - BOX
        f0-0f f0-1f f1-0f - LOC
    )
    (:init
        (adjacent f0-0f f0-1f right)
        (adjacent f0-1f f0-0f left)
        (adjacent f0-0f f1-0f down)
        (at box0 f0-1f)
        (at-robot f0-0f)
        (clear f1-0f)
    )
    (:goal
        (and
            (at box0 f1-0f)
        )
    )
    )
    """


def test_registry_domain_ids_exactly_match_curriculum_config_domain_ids() -> None:
    curriculum_config = load_curriculum_config()

    assert curriculum_config.selected_domain_ids == registry_domain_ids()
    assert curriculum_config.domain_to_generator_id == EXPECTED_DOMAIN_TO_GENERATOR


def test_registry_builds_adapter_for_every_configured_domain_with_metadata() -> None:
    curriculum_config = load_curriculum_config()
    registry = build_domain_registry(curriculum_config)

    assert tuple(registry) == curriculum_config.selected_domain_ids

    for domain_id, adapter in registry.items():
        metadata = adapter.metadata
        assert domain_id == adapter.adapter_id
        assert metadata.generator_path
        assert metadata.domain_file_source
        assert metadata.problem_output_discovery
        assert metadata.output_policy is not None
        assert metadata.seed_policy is not None
        assert metadata.smoke_supported is True
        assert len(metadata.target_parameter_presets) == 3
        assert {preset.preset_id for preset in metadata.target_parameter_presets} == {"easy", "medium", "hard"}


def test_driverlog_command_places_seed_before_preset_arguments(tmp_path: Path) -> None:
    curriculum_config = load_curriculum_config()
    driverlog = next(domain for domain in curriculum_config.domains if domain.domain_id == "driverlog")
    adapter = build_domain_adapter(driverlog)

    prepared = adapter._command_builder(
        GenerationSpec(
            candidate_id="driverlog-train-medium-attempt-000001",
            output_dir=tmp_path / "driverlog-medium",
            timeout_seconds=30,
            seed=12345,
            extra={"preset_id": "medium"},
        )
    )

    assert prepared.command[:6] == (
        str(Path(adapter.metadata.generator_path)),
        "12345",
        "8",
        "3",
        "4",
        "3",
    )


def test_elevators_domain_uses_miconic_generator_family() -> None:
    curriculum_config = load_curriculum_config()
    elevators = next(domain for domain in curriculum_config.domains if domain.domain_id == "elevators")
    adapter = build_domain_adapter(elevators)

    assert elevators.generator_domain_id == "miconic"
    assert adapter.generator_domain_id == "miconic"
    assert adapter.metadata.generator_path.endswith("/modules/pddl-generators/miconic/miconic")


def test_15puzzle_hard_preset_uses_stable_4x4_board() -> None:
    curriculum_config = load_curriculum_config()
    puzzle = next(domain for domain in curriculum_config.domains if domain.domain_id == "15puzzle")
    adapter = build_domain_adapter(puzzle)

    hard_preset = next(preset for preset in adapter.metadata.target_parameter_presets if preset.preset_id == "hard")
    assert hard_preset.command_arguments == ("-n", "4")
    assert hard_preset.parameters == {"board_size": 4}


def test_gripper_deterministic_sweep_builder_changes_n_and_variant(tmp_path: Path) -> None:
    curriculum_config = load_curriculum_config()
    domain = next(item for item in curriculum_config.domains if item.domain_id == "gripper")
    adapter = build_domain_adapter(domain)

    first = adapter._command_builder(
        GenerationSpec(
            candidate_id="gripper-train-easy-attempt-000000",
            output_dir=tmp_path / "g0",
            timeout_seconds=30,
            extra={"preset_id": "easy", "bucket_attempt_index": 1},
        )
    )
    thirteenth = adapter._command_builder(
        GenerationSpec(
            candidate_id="gripper-train-easy-attempt-000012",
            output_dir=tmp_path / "g12",
            timeout_seconds=30,
            extra={"preset_id": "easy", "bucket_attempt_index": 12},
        )
    )

    assert first.command[-2:] == ("-n", "3")
    assert thirteenth.command[-2:] == ("-n", "4")
    assert first.stdout_transform is not None
    transformed = first.stdout_transform(
        "(define (problem p) (:domain gripper-strips) (:objects rooma roomb left right ball1 ball2 ball3) (:init (at ball1 rooma) (free left)) (:goal (and (at ball1 roomb))))"
    )
    assert transformed != "(define (problem p) (:domain gripper-strips) (:objects rooma roomb left right ball1 ball2 ball3) (:init (at ball1 rooma) (free left)) (:goal (and (at ball1 roomb))))"
    assert "ball2" in transformed


def test_hanoi_hard_preset_uses_render_safe_disc_range() -> None:
    curriculum_config = load_curriculum_config()
    domain = next(item for item in curriculum_config.domains if item.domain_id == "towers_of_hanoi")
    adapter = build_domain_adapter(domain)

    hard_preset = next(preset for preset in adapter.metadata.target_parameter_presets if preset.preset_id == "hard")
    assert hard_preset.command_arguments == ("-n", "8")
    assert hard_preset.parameters == {"discs_start": 8, "discs_stop": 9, "variants_per_n": 48}


def test_visitall_stdout_transform_strips_numeric_prefix_before_define(tmp_path: Path) -> None:
    curriculum_config = load_curriculum_config()
    domain = next(item for item in curriculum_config.domains if item.domain_id == "visitall")
    adapter = build_domain_adapter(domain)

    prepared = adapter._command_builder(
        GenerationSpec(
            candidate_id="visitall-train-hard-attempt-000001",
            output_dir=tmp_path / "visitall-hard",
            timeout_seconds=30,
            seed=12345,
            extra={"preset_id": "hard"},
        )
    )

    assert prepared.stdout_transform is not None
    assert prepared.stdout_transform("122\n139\n(define (problem p) (:domain d))") == "(define (problem p) (:domain d))"


def test_hanoi_deterministic_sweep_exhaustion_returns_rejection(tmp_path: Path) -> None:
    curriculum_config = load_curriculum_config()
    domain = next(item for item in curriculum_config.domains if item.domain_id == "towers_of_hanoi")
    adapter = build_domain_adapter(domain)

    exhausted = adapter._command_builder(
        GenerationSpec(
            candidate_id="towers_of_hanoi-train-hard-attempt-999999",
            output_dir=tmp_path / "h-exhausted",
            timeout_seconds=30,
            extra={"preset_id": "hard", "bucket_attempt_index": 96},
        )
    )

    assert exhausted.rejection is not None
    assert exhausted.rejection.rejection_reason == "deterministic_variants_exhausted"


def test_storage_builder_varies_structural_arguments_by_bucket_attempt(tmp_path: Path) -> None:
    curriculum_config = load_curriculum_config()
    domain = next(item for item in curriculum_config.domains if item.domain_id == "storage")
    adapter = build_domain_adapter(domain)

    commands = []
    for bucket_attempt_index in (0, 1, 2, 12, 13, 14, 18):
        prepared = adapter._command_builder(
            GenerationSpec(
                candidate_id=f"storage-train-easy-attempt-{bucket_attempt_index:06d}",
                output_dir=tmp_path / f"storage-{bucket_attempt_index}",
                timeout_seconds=30,
                seed=12345,
                extra={"preset_id": "easy", "split": "train", "attempt_index": bucket_attempt_index, "bucket_attempt_index": bucket_attempt_index},
            )
        )
        commands.append(prepared.command)

    def value(command: tuple[str, ...], flag: str) -> str:
        return command[command.index(flag) + 1]

    for flag in ("-o", "-c", "-n", "-s", "-d"):
        assert len({value(command, flag) for command in commands}) > 1
    assert len({value(command, "-p") for command in commands}) == len(commands)
    assert len({command[-1] for command in commands}) == len(commands)


def test_sokoban_adapter_uses_planimation_template_schema(tmp_path: Path) -> None:
    curriculum_config = load_curriculum_config()
    domain = next(item for item in curriculum_config.domains if item.domain_id == "sokoban")
    adapter = build_domain_adapter(domain)

    prepared = adapter._command_builder(
        GenerationSpec(
            candidate_id="sokoban-train-easy-attempt-000000",
            output_dir=tmp_path / "sokoban",
            timeout_seconds=30,
            seed=12345,
            extra={"preset_id": "easy"},
        )
    )

    assert adapter.metadata.domain_file_source.endswith("/data/pddl_instances/sokoban/domain.pddl")
    assert prepared.stdout_transform is not None

    transformed = prepared.stdout_transform(_typed_sokoban_problem())

    assert "(:domain template)" in transformed
    assert "pos1_1 pos1_2 pos2_1 - pos" in transformed
    assert "ply1 - player" in transformed
    assert "blk1 - block" in transformed
    assert "but1 - button" in transformed
    assert "(position pos1_1)" in transformed
    assert "(right pos1_1 pos1_2)" in transformed
    assert "(at ply1 pos1_1)" in transformed
    assert "(at blk1 pos1_2)" in transformed
    assert "(at but1 pos2_1)" in transformed
    assert "(forall (?but - button)" in transformed
    assert "(exists (?blk - block)" in transformed


def test_sokoban_presets_use_render_compatible_generator_shape() -> None:
    curriculum_config = load_curriculum_config()
    domain = next(item for item in curriculum_config.domains if item.domain_id == "sokoban")
    adapter = build_domain_adapter(domain)

    for preset in adapter.metadata.target_parameter_presets:
        assert preset.command_arguments == ("-n", "5", "-b", "1", "-w", "0")
        assert preset.parameters == {"grid_size": 5, "boxes": 1, "walls": 0}


def test_sokoban_builder_varies_normalized_template_problem_hashes(tmp_path: Path) -> None:
    curriculum_config = load_curriculum_config()
    domain = next(item for item in curriculum_config.domains if item.domain_id == "sokoban")
    adapter = build_domain_adapter(domain)
    raw_problem = _typed_sokoban_problem()

    hashes: set[str] = set()
    normalized_texts: set[str] = set()
    for index in range(270):
        split = ("train", "dev", "test")[index % 3]
        preset_id = ("easy", "medium", "hard")[(index // 3) % 3]
        bucket_attempt_index = index // 9
        prepared = adapter._command_builder(
            GenerationSpec(
                candidate_id=f"sokoban-{split}-{preset_id}-attempt-{index:06d}",
                output_dir=tmp_path / f"sokoban-{index}",
                timeout_seconds=30,
                seed=12345,
                extra={
                    "preset_id": preset_id,
                    "split": split,
                    "attempt_index": index,
                    "bucket_attempt_index": bucket_attempt_index,
                },
            )
        )

        assert prepared.stdout_transform is not None
        transformed = prepared.stdout_transform(raw_problem)
        hash_info = build_pddl_hash_info(transformed)
        hashes.add(hash_info.normalized_sha256)
        normalized_texts.add(hash_info.normalized_text)

        assert "(:domain template)" in transformed
        assert "ply1 - player" in transformed
        assert "blk1 - block" in transformed
        assert "but1 - button" in transformed
        assert "(forall (?but - button)" in transformed

    assert len(hashes) == 270
    assert len(normalized_texts) == 270


def test_sokoban_variant_changes_positive_position_symbols_not_comments(tmp_path: Path) -> None:
    curriculum_config = load_curriculum_config()
    domain = next(item for item in curriculum_config.domains if item.domain_id == "sokoban")
    adapter = build_domain_adapter(domain)

    first = adapter._command_builder(
        GenerationSpec(
            candidate_id="sokoban-train-easy-attempt-000000",
            output_dir=tmp_path / "sokoban-0",
            timeout_seconds=30,
            seed=12345,
            extra={"preset_id": "easy", "split": "train", "bucket_attempt_index": 0},
        )
    )
    second = adapter._command_builder(
        GenerationSpec(
            candidate_id="sokoban-train-easy-attempt-000001",
            output_dir=tmp_path / "sokoban-1",
            timeout_seconds=30,
            seed=12345,
            extra={"preset_id": "easy", "split": "train", "bucket_attempt_index": 1},
        )
    )

    assert first.stdout_transform is not None
    assert second.stdout_transform is not None
    first_problem = first.stdout_transform(_typed_sokoban_problem())
    second_problem = second.stdout_transform(_typed_sokoban_problem())

    assert "pos1_1 pos1_2 pos2_1 - pos" in first_problem
    assert "pos11_1 pos11_2 pos12_1 - pos" in second_problem
    assert "(right pos11_1 pos11_2)" in second_problem
    assert build_pddl_hash_info(first_problem).normalized_sha256 != build_pddl_hash_info(second_problem).normalized_sha256
