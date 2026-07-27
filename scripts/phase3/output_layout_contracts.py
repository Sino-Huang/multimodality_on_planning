from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Final, Literal


SCHEMA_VERSION: Final = "phase3_output_layout_catalog_v2"
OUTPUTS_DIRECTORY: Final = "outputs"
REASONING_ROOT: Final = "outputs/reasoning_traces"
IMAGE_ROOT: Final = "outputs/image_frames"
DEPRECATED_ROOT: Final = "outputs/deprecated"
TRACE_SOURCE_ROOT: Final = "outputs/phase3_curriculum_traces_safe_no_visitall_strict_v1_1st_round"
PILOT_SOURCE_ROOT: Final = "outputs/phase3_planimation_frames_stratified_pilot_20260725"
SELECTION_SOURCE_ROOT: Final = "outputs/phase3_planimation_frames_safe_no_visitall_strict_v1_20260722_005800"
TRACE_ROOT: Final = f"{REASONING_ROOT}/curriculum/phase3_curriculum_traces_safe_no_visitall_strict_v1_1st_round"
PILOT_ROOT: Final = f"{IMAGE_ROOT}/phase3_planimation_frames_stratified_pilot_20260725"
SELECTION_ROOT: Final = f"{IMAGE_ROOT}/phase3_planimation_frames_safe_no_visitall_strict_v1_20260722_005800"
RECORD_ROOT: Final = f"{REASONING_ROOT}/vlm_records/stratified_pilot_20260725"

OutputCategory = Literal["reasoning_traces", "image_frames", "deprecated"]
RecordFamily = Literal["full_reasoning", "step_vlm", "search_traversal"]
RecordSplit = Literal["train", "dev", "test"]
CopyPolicy = Literal["physical_immutable_copy"]


class OutputLayoutContractError(ValueError):
    def __init__(self, *, rule: str, path: str) -> None:
        self.rule: str = rule
        self.path: str = path
        super().__init__(f"{rule}: {path}")


@dataclass(frozen=True, slots=True, order=True)
class RepositoryRelativePath:
    value: str

    @classmethod
    def parse(cls, value: str) -> RepositoryRelativePath:
        path = PurePosixPath(value)
        if path.is_absolute():
            raise OutputLayoutContractError(rule="path must be repository-relative", path=value)
        if value != path.as_posix() or ".." in path.parts:
            raise OutputLayoutContractError(rule="path must not contain '..' or normalization", path=value)
        if len(path.parts) < 2 or path.parts[0] != OUTPUTS_DIRECTORY:
            raise OutputLayoutContractError(rule="path must be confined to outputs/", path=value)
        if path.parts[1] == "datasets":
            raise OutputLayoutContractError(rule="outputs/datasets is prohibited", path=value)
        return cls(value)


@dataclass(frozen=True, slots=True)
class CategoryRoot:
    category: OutputCategory
    path: RepositoryRelativePath


@dataclass(frozen=True, slots=True)
class ProtectedRoot:
    path: RepositoryRelativePath
    rationale: str


@dataclass(frozen=True, slots=True)
class Relocation:
    source: RepositoryRelativePath
    classification: str
    category: OutputCategory
    destination: RepositoryRelativePath


@dataclass(frozen=True, slots=True)
class PhysicalRecordCopy:
    source: RepositoryRelativePath
    destination: RepositoryRelativePath
    family: RecordFamily
    split: RecordSplit
    policy: CopyPolicy


@dataclass(frozen=True, slots=True)
class OutputLayout:
    schema_version: str
    rationale: str
    category_roots: tuple[CategoryRoot, ...]
    protected_roots: tuple[ProtectedRoot, ...]
    relocations: tuple[Relocation, ...]
    physical_record_copies: tuple[PhysicalRecordCopy, ...]


def _path(value: str) -> RepositoryRelativePath:
    return RepositoryRelativePath.parse(value)


def _move(source: str, classification: str, category: OutputCategory, destination: str) -> Relocation:
    return Relocation(_path(source), classification, category, _path(destination))


CATEGORY_ROOTS: Final = (
    CategoryRoot("reasoning_traces", _path(REASONING_ROOT)),
    CategoryRoot("image_frames", _path(IMAGE_ROOT)),
    CategoryRoot("deprecated", _path(DEPRECATED_ROOT)),
)
PROTECTED_ROOTS: Final = (
    ProtectedRoot(_path(TRACE_ROOT), "approved strict source traces for the pilot"),
    ProtectedRoot(_path(PILOT_ROOT), "approved 52-pair stratified pilot records and assets"),
    ProtectedRoot(_path(SELECTION_ROOT), "frozen selection provenance for the approved pilot"),
)
RELOCATIONS: Final = (
    _move(TRACE_SOURCE_ROOT, "approved strict source traces for the pilot", "reasoning_traces", TRACE_ROOT),
    _move(PILOT_SOURCE_ROOT, "approved 52-pair stratified pilot records and assets", "image_frames", PILOT_ROOT),
    _move(SELECTION_SOURCE_ROOT, "frozen selection provenance for the approved pilot", "image_frames", SELECTION_ROOT),
    _move("outputs/phase3_curriculum_traces_15puzzle_easy_20260709_002417", "superseded legacy trace source", "deprecated", "outputs/deprecated/phase3/curriculum_traces/phase3_curriculum_traces_15puzzle_easy_20260709_002417"),
    _move("outputs/phase3_curriculum_traces_15puzzle_easy_strict_v1_1st_round", "superseded strict 15-puzzle candidate", "deprecated", "outputs/deprecated/phase3/curriculum_traces/phase3_curriculum_traces_15puzzle_easy_strict_v1_1st_round"),
    _move("outputs/phase3_curriculum_traces_safe_no_visitall_20260708_122431", "superseded predecessor", "deprecated", "outputs/deprecated/phase3/curriculum_traces/phase3_curriculum_traces_safe_no_visitall_20260708_122431"),
    _move("outputs/phase3_curriculum_traces_visitall_20260708_191916", "failed/incomplete Visitall attempt", "deprecated", "outputs/deprecated/phase3/curriculum_traces/phase3_curriculum_traces_visitall_20260708_191916"),
    _move("outputs/phase3_curriculum_traces_visitall_strict_v1_1st_round", "failed/incomplete strict Visitall attempt", "deprecated", "outputs/deprecated/phase3/curriculum_traces/phase3_curriculum_traces_visitall_strict_v1_1st_round"),
    _move("outputs/phase3_curriculum_traces_visitall_train_test_long_timeout_20260710_000503", "incomplete/superseded recovery attempt", "deprecated", "outputs/deprecated/phase3/curriculum_traces/phase3_curriculum_traces_visitall_train_test_long_timeout_20260710_000503"),
    _move("outputs/phase3_planimation_bounded_repro_20260721_2130", "temporary failed bounded reproduction", "deprecated", "outputs/deprecated/phase3/planimation_runs/phase3_planimation_bounded_repro_20260721_2130"),
    _move("outputs/phase3_planimation_elevators_profile_probe_20260722_100300", "temporary profile probe", "deprecated", "outputs/deprecated/phase3/planimation_runs/phase3_planimation_elevators_profile_probe_20260722_100300"),
    _move("outputs/phase3_planimation_frames_15puzzle_easy_20260721_214258", "superseded/incomplete manifest run", "deprecated", "outputs/deprecated/phase3/planimation_runs/phase3_planimation_frames_15puzzle_easy_20260721_214258"),
    _move("outputs/phase3_planimation_frames_safe_no_visitall_20260721_044105", "superseded pre-strict manifest run", "deprecated", "outputs/deprecated/phase3/planimation_runs/phase3_planimation_frames_safe_no_visitall_20260721_044105"),
    _move("outputs/phase3_planimation_frames_visitall_20260721_213129", "failed Visitall render run", "deprecated", "outputs/deprecated/phase3/planimation_runs/phase3_planimation_frames_visitall_20260721_213129"),
    _move("outputs/phase3_planimation_smoke_blocksworld_20260722_001817", "temporary bounded smoke run", "deprecated", "outputs/deprecated/phase3/planimation_runs/phase3_planimation_smoke_blocksworld_20260722_001817"),
)
PHYSICAL_RECORD_COPIES: Final = tuple(
    PhysicalRecordCopy(_path(f"{PILOT_ROOT}/{family}_{split}.jsonl"), _path(f"{RECORD_ROOT}/{family}/{split}.jsonl"), family, split, "physical_immutable_copy")
    for family in ("full_reasoning", "step_vlm", "search_traversal")
    for split in ("train", "dev", "test")
)
DEFAULT_OUTPUT_LAYOUT: Final = OutputLayout(
    schema_version=SCHEMA_VERSION,
    rationale="Three-category migration contract; canonical pilot JSONLs are copied as immutable physical records.",
    category_roots=CATEGORY_ROOTS,
    protected_roots=PROTECTED_ROOTS,
    relocations=RELOCATIONS,
    physical_record_copies=PHYSICAL_RECORD_COPIES,
)
OUTPUT_LAYOUT: Final = DEFAULT_OUTPUT_LAYOUT


def validate_output_layout(layout: OutputLayout) -> None:
    if layout.schema_version != SCHEMA_VERSION:
        raise OutputLayoutContractError(rule="unsupported schema version", path=layout.schema_version)
    if len(layout.category_roots) != 3 or len(layout.protected_roots) != 3 or len(layout.relocations) != 15 or len(layout.physical_record_copies) != 9:
        raise OutputLayoutContractError(rule="catalog has unexpected category, protected, relocation, or copy count", path=layout.schema_version)
    category_paths = tuple(root.path for root in layout.category_roots)
    protected_paths = tuple(root.path for root in layout.protected_roots)
    source_paths = tuple(move.source for move in layout.relocations)
    destination_paths = tuple(move.destination for move in layout.relocations)
    copy_sources = tuple(copy.source for copy in layout.physical_record_copies)
    copy_destinations = tuple(copy.destination for copy in layout.physical_record_copies)
    _validate_unique("category root", category_paths)
    _validate_unique("protected root", protected_paths)
    _validate_unique("relocation source", source_paths)
    _validate_unique("relocation destination", destination_paths)
    _validate_unique("physical record source", copy_sources)
    _validate_unique("physical record destination", copy_destinations)
    if tuple((root.category, root.path.value) for root in layout.category_roots) != (("reasoning_traces", REASONING_ROOT), ("image_frames", IMAGE_ROOT), ("deprecated", DEPRECATED_ROOT)):
        raise OutputLayoutContractError(rule="unexpected category roots", path=layout.schema_version)
    for path in (*category_paths, *protected_paths, *source_paths, *destination_paths, *copy_sources, *copy_destinations):
        _ = RepositoryRelativePath.parse(path.value)
    for protected_path in protected_paths:
        if any(_paths_overlap(protected_path, source_path) for source_path in source_paths):
            raise OutputLayoutContractError(rule="relocation overlaps protected root", path=protected_path.value)
    for move in layout.relocations:
        if not _is_below(move.destination, _category_path(move.category, layout.category_roots)):
            raise OutputLayoutContractError(rule="relocation destination must be below its category root", path=move.destination.value)
    if any(len(PurePosixPath(path.value).parts) != 2 for path in source_paths):
        raise OutputLayoutContractError(rule="relocation source must be a flat outputs root", path=layout.schema_version)
    for protected_path in protected_paths:
        if protected_path not in destination_paths:
            raise OutputLayoutContractError(rule="protected root must be a live relocation destination", path=protected_path.value)
    for source_path in source_paths:
        if any(_paths_overlap(source_path, destination_path) for destination_path in destination_paths):
            raise OutputLayoutContractError(rule="source and destination overlap", path=source_path.value)
    for copy in layout.physical_record_copies:
        if copy.policy != "physical_immutable_copy":
            raise OutputLayoutContractError(rule="record copy must be physical and immutable", path=copy.destination.value)
        if copy.source.value != f"{PILOT_ROOT}/{copy.family}_{copy.split}.jsonl":
            raise OutputLayoutContractError(rule="physical record source must be below the moved pilot root", path=copy.source.value)
        if copy.destination.value != f"{RECORD_ROOT}/{copy.family}/{copy.split}.jsonl":
            raise OutputLayoutContractError(rule="physical record destination must use the family and split tree", path=copy.destination.value)
    if layout != DEFAULT_OUTPUT_LAYOUT:
        raise OutputLayoutContractError(rule="catalog differs from approved immutable default", path=layout.schema_version)


def validate_inventory_roots(layout: OutputLayout, inventory_roots: tuple[RepositoryRelativePath, ...]) -> None:
    validate_output_layout(layout)
    _validate_unique("inventory root", inventory_roots)
    approved_roots = frozenset(move.source for move in layout.relocations)
    for root in inventory_roots:
        parsed_root = RepositoryRelativePath.parse(root.value)
        if len(PurePosixPath(parsed_root.value).parts) != 2:
            raise OutputLayoutContractError(rule="inventory root must be top-level under outputs/", path=parsed_root.value)
        if parsed_root not in approved_roots:
            raise OutputLayoutContractError(rule="unknown inventory root", path=parsed_root.value)


def serialize_catalog(layout: OutputLayout = DEFAULT_OUTPUT_LAYOUT) -> str:
    validate_output_layout(layout)
    catalog = {
        "authoritativeness": "migration_contract",
        "categories": [{"category": root.category, "path": root.path.value} for root in layout.category_roots],
        "physical_record_copies": [{"destination": copy.destination.value, "family": copy.family, "policy": copy.policy, "source": copy.source.value, "split": copy.split} for copy in layout.physical_record_copies],
        "protected_roots": [{"path": root.path.value, "rationale": root.rationale} for root in layout.protected_roots],
        "rationale": layout.rationale,
        "relocations": [{"category": move.category, "classification": move.classification, "destination": move.destination.value, "source": move.source.value} for move in layout.relocations],
        "schema_version": layout.schema_version,
    }
    return json.dumps(catalog, indent=2, sort_keys=True) + "\n"


def _validate_unique(label: str, paths: tuple[RepositoryRelativePath, ...]) -> None:
    if len(paths) != len(frozenset(paths)):
        raise OutputLayoutContractError(rule=f"duplicate {label}", path=label)


def _paths_overlap(left: RepositoryRelativePath, right: RepositoryRelativePath) -> bool:
    return left == right or left.value.startswith(f"{right.value}/") or right.value.startswith(f"{left.value}/")


def _is_below(path: RepositoryRelativePath, root: RepositoryRelativePath) -> bool:
    return path.value.startswith(f"{root.value}/")


def _category_path(category: OutputCategory, roots: tuple[CategoryRoot, ...]) -> RepositoryRelativePath:
    for root in roots:
        if root.category == category:
            return root.path
    raise OutputLayoutContractError(rule="unknown output category", path=category)


validate_output_layout(DEFAULT_OUTPUT_LAYOUT)
