from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

try:
    import yaml
except ImportError:  # pragma: no cover - depends on runtime environment
    yaml = None


EXPECTED_DOMAIN_TO_GENERATOR: dict[str, str] = {
    "15puzzle": "npuzzle",
    "blocksworld": "blocksworld",
    "depot": "depots",
    "driverlog": "driverlog",
    "elevators": "miconic",
    "ferry": "ferry",
    "freecell": "freecell",
    "grid": "grid",
    "gripper": "gripper",
    "logistics": "logistics",
    "snake": "snake",
    "sokoban": "sokoban",
    "storage": "storage",
    "towers_of_hanoi": "hanoi",
    "visitall": "visitall",
}

EXPECTED_SPLIT_BUCKETS: dict[str, dict[str, int]] = {
    "train": {"easy": 70, "medium": 80, "hard": 50},
    "dev": {"easy": 7, "medium": 8, "hard": 5},
    "test": {"easy": 5, "medium": 7, "hard": 8},
}

EXPECTED_SPLIT_TOTALS: dict[str, int] = {
    split_name: sum(buckets.values())
    for split_name, buckets in EXPECTED_SPLIT_BUCKETS.items()
}

DEFAULT_CONFIG_DIR = Path(__file__).resolve().parent / "configs"
DEFAULT_CURRICULUM_CONFIG_PATH = DEFAULT_CONFIG_DIR / "curriculum_15_domains.yaml"
DEFAULT_GENERATOR_DEPENDENCIES_PATH = DEFAULT_CONFIG_DIR / "generator_dependencies.yaml"


@dataclass(frozen=True)
class SeedRange:
    start: int
    stop: int


@dataclass(frozen=True)
class TimeoutConfig:
    generator_seconds: int
    render_seconds: int


@dataclass(frozen=True)
class OutputPolicy:
    accepted_dir: str
    rejected_dir: str
    summaries_dir: str


@dataclass(frozen=True)
class SplitConfig:
    total: int
    buckets: dict[str, int]


@dataclass(frozen=True)
class DependencyGroup:
    group_id: str
    generator_domain_id: str
    python_runtime: str
    python_packages: tuple[str, ...]
    system_tools: tuple[str, ...]
    build_required: bool
    build_commands: tuple[str, ...]
    notes: str


@dataclass(frozen=True)
class DomainConfig:
    domain_id: str
    generator_domain_id: str
    generator_dir: Path
    render_profile_path: Path
    dependency_group: str


@dataclass(frozen=True)
class CurriculumConfig:
    config_path: Path
    workspace_root: Path
    generator_root: Path
    manifest_path: Path
    dependency_config_path: Path
    require_rendering: bool
    candidate_multiplier: int
    seed_range: SeedRange
    timeouts: TimeoutConfig
    output_policy: OutputPolicy
    splits: dict[str, SplitConfig]
    domains: tuple[DomainConfig, ...]
    dependencies: dict[str, DependencyGroup]

    @property
    def domain_count(self) -> int:
        return len(self.domains)

    @property
    def selected_domain_ids(self) -> tuple[str, ...]:
        return tuple(domain.domain_id for domain in self.domains)

    @property
    def target_accepted_total(self) -> int:
        per_domain_total = sum(split.total for split in self.splits.values())
        return self.domain_count * per_domain_total

    @property
    def domain_to_generator_id(self) -> dict[str, str]:
        return {domain.domain_id: domain.generator_domain_id for domain in self.domains}


def load_curriculum_config(config_path: Path | str = DEFAULT_CURRICULUM_CONFIG_PATH) -> CurriculumConfig:
    resolved_config_path = Path(config_path).resolve()
    payload = _load_yaml_mapping(resolved_config_path, "curriculum config")

    workspace_root = _resolve_path(
        resolved_config_path.parent,
        _require_non_empty_string(payload, "workspace_root", context="curriculum config"),
    )
    generator_root = _resolve_path(
        workspace_root,
        _require_non_empty_string(payload, "generator_root", context="curriculum config"),
    )
    manifest_path = _resolve_path(
        workspace_root,
        _require_non_empty_string(payload, "manifest_path", context="curriculum config"),
    )
    dependency_config_path = _resolve_path(
        workspace_root,
        _require_non_empty_string(payload, "dependency_config", context="curriculum config"),
    )

    if not workspace_root.exists():
        raise FileNotFoundError(f"Configured workspace_root does not exist: {workspace_root}")
    if not generator_root.exists():
        raise FileNotFoundError(f"Configured generator_root does not exist: {generator_root}")
    if not manifest_path.exists():
        raise FileNotFoundError(f"Configured manifest_path does not exist: {manifest_path}")

    dependencies = load_generator_dependencies(dependency_config_path)

    require_rendering = _require_bool(payload, "require_rendering", context="curriculum config")
    candidate_multiplier = _require_positive_int(payload, "candidate_multiplier", context="curriculum config")

    seed_range_payload = _require_mapping(payload, "seed_range", context="curriculum config")
    seed_range = SeedRange(
        start=_require_int(seed_range_payload, "start", context="seed_range"),
        stop=_require_int(seed_range_payload, "stop", context="seed_range"),
    )
    if seed_range.start > seed_range.stop:
        raise ValueError(
            f"seed_range.start must be <= seed_range.stop, got {seed_range.start} > {seed_range.stop}"
        )

    timeouts_payload = _require_mapping(payload, "timeouts", context="curriculum config")
    timeouts = TimeoutConfig(
        generator_seconds=_require_positive_int(timeouts_payload, "generator_seconds", context="timeouts"),
        render_seconds=_require_positive_int(timeouts_payload, "render_seconds", context="timeouts"),
    )

    output_policy_payload = _require_mapping(payload, "output_policy", context="curriculum config")
    output_policy = OutputPolicy(
        accepted_dir=_require_non_empty_string(output_policy_payload, "accepted_dir", context="output_policy"),
        rejected_dir=_require_non_empty_string(output_policy_payload, "rejected_dir", context="output_policy"),
        summaries_dir=_require_non_empty_string(output_policy_payload, "summaries_dir", context="output_policy"),
    )

    splits = _load_split_configs(payload)
    domains = _load_domain_configs(payload, workspace_root=workspace_root, generator_root=generator_root)

    configured_domain_to_generator = {domain.domain_id: domain.generator_domain_id for domain in domains}
    if configured_domain_to_generator != EXPECTED_DOMAIN_TO_GENERATOR:
        raise ValueError(
            "Configured domain mappings do not match the 15-domain curriculum contract: "
            f"expected {EXPECTED_DOMAIN_TO_GENERATOR}, got {configured_domain_to_generator}"
        )

    if len(domains) != len(EXPECTED_DOMAIN_TO_GENERATOR):
        raise ValueError(
            f"Curriculum must declare exactly {len(EXPECTED_DOMAIN_TO_GENERATOR)} domains, got {len(domains)}"
        )

    for domain in domains:
        dependency_group = dependencies.get(domain.dependency_group)
        if dependency_group is None:
            raise ValueError(
                f"Domain '{domain.domain_id}' references unknown dependency group '{domain.dependency_group}'"
            )
        if dependency_group.generator_domain_id != domain.generator_domain_id:
            raise ValueError(
                "Dependency group generator mismatch for domain "
                f"'{domain.domain_id}': expected '{domain.generator_domain_id}', "
                f"got '{dependency_group.generator_domain_id}'"
            )
        if not domain.generator_dir.exists():
            raise FileNotFoundError(
                f"Configured generator directory does not exist for domain '{domain.domain_id}': {domain.generator_dir}"
            )
        if require_rendering and not domain.render_profile_path.exists():
            raise FileNotFoundError(
                f"Configured render_profile_path does not exist for domain '{domain.domain_id}': "
                f"{domain.render_profile_path}"
            )

    return CurriculumConfig(
        config_path=resolved_config_path,
        workspace_root=workspace_root,
        generator_root=generator_root,
        manifest_path=manifest_path,
        dependency_config_path=dependency_config_path,
        require_rendering=require_rendering,
        candidate_multiplier=candidate_multiplier,
        seed_range=seed_range,
        timeouts=timeouts,
        output_policy=output_policy,
        splits=splits,
        domains=tuple(domains),
        dependencies=dependencies,
    )


def load_generator_dependencies(dependency_config_path: Path | str) -> dict[str, DependencyGroup]:
    resolved_dependency_path = Path(dependency_config_path).resolve()
    payload = _load_yaml_mapping(resolved_dependency_path, "generator dependency config")
    groups_payload = _require_mapping(payload, "dependency_groups", context="generator dependency config")

    dependencies: dict[str, DependencyGroup] = {}
    for group_id, group_payload in groups_payload.items():
        if not isinstance(group_id, str) or not group_id.strip():
            raise ValueError("Dependency group ids must be non-empty strings")
        group_mapping = _ensure_mapping(group_payload, context=f"dependency_groups.{group_id}")
        build_payload = _require_mapping(group_mapping, "build", context=f"dependency_groups.{group_id}")
        build_required = _require_bool(build_payload, "required", context=f"dependency_groups.{group_id}.build")
        build_commands = tuple(
            _read_string_list(build_payload, "commands", context=f"dependency_groups.{group_id}.build")
        )
        if build_required and not build_commands:
            raise ValueError(f"dependency_groups.{group_id}.build.commands must not be empty when build is required")

        dependencies[group_id] = DependencyGroup(
            group_id=group_id,
            generator_domain_id=_require_non_empty_string(
                group_mapping,
                "generator_domain_id",
                context=f"dependency_groups.{group_id}",
            ),
            python_runtime=_require_non_empty_string(
                group_mapping,
                "python_runtime",
                context=f"dependency_groups.{group_id}",
            ),
            python_packages=tuple(
                _read_string_list(group_mapping, "python_packages", context=f"dependency_groups.{group_id}")
            ),
            system_tools=tuple(
                _read_string_list(group_mapping, "system_tools", context=f"dependency_groups.{group_id}")
            ),
            build_required=build_required,
            build_commands=build_commands,
            notes=_require_string(group_mapping, "notes", context=f"dependency_groups.{group_id}"),
        )

    return dependencies


def _load_split_configs(payload: Mapping[str, Any]) -> dict[str, SplitConfig]:
    splits_payload = _require_mapping(payload, "splits", context="curriculum config")

    if set(splits_payload) != set(EXPECTED_SPLIT_BUCKETS):
        raise ValueError(
            f"Curriculum splits must be exactly {sorted(EXPECTED_SPLIT_BUCKETS)}, got {sorted(splits_payload)}"
        )

    splits: dict[str, SplitConfig] = {}
    for split_name, expected_buckets in EXPECTED_SPLIT_BUCKETS.items():
        split_payload = _require_mapping(splits_payload, split_name, context="splits")
        total = _require_positive_int(split_payload, "total", context=f"splits.{split_name}")
        expected_total = EXPECTED_SPLIT_TOTALS[split_name]
        if total != expected_total:
            raise ValueError(
                f"splits.{split_name}.total must equal {expected_total}, got {total}"
            )

        buckets_payload = _require_mapping(split_payload, "buckets", context=f"splits.{split_name}")
        if set(buckets_payload) != set(expected_buckets):
            raise ValueError(
                f"splits.{split_name}.buckets must be exactly {sorted(expected_buckets)}, got {sorted(buckets_payload)}"
            )

        buckets = {
            bucket_name: _require_positive_int(
                buckets_payload,
                bucket_name,
                context=f"splits.{split_name}.buckets",
            )
            for bucket_name in ("easy", "medium", "hard")
        }
        if buckets != expected_buckets:
            raise ValueError(
                f"splits.{split_name}.buckets must equal {expected_buckets}, got {buckets}"
            )
        if sum(buckets.values()) != total:
            raise ValueError(
                f"splits.{split_name}.buckets sum to {sum(buckets.values())}, but total is {total}"
            )

        splits[split_name] = SplitConfig(total=total, buckets=buckets)

    return splits


def _load_domain_configs(
    payload: Mapping[str, Any],
    *,
    workspace_root: Path,
    generator_root: Path,
) -> list[DomainConfig]:
    domains_payload = payload.get("domains")
    if not isinstance(domains_payload, list):
        raise ValueError("curriculum config field 'domains' must be a list")

    domains: list[DomainConfig] = []
    seen_domain_ids: set[str] = set()
    for index, domain_payload in enumerate(domains_payload):
        domain_mapping = _ensure_mapping(domain_payload, context=f"domains[{index}]")
        domain_id = _require_non_empty_string(domain_mapping, "domain_id", context=f"domains[{index}]")
        if domain_id in seen_domain_ids:
            raise ValueError(f"Duplicate domain_id in curriculum config: {domain_id}")
        seen_domain_ids.add(domain_id)

        render_profile = _require_non_empty_string(
            domain_mapping,
            "render_profile_path",
            context=f"domains[{index}]",
        )
        generator_domain_id = _require_non_empty_string(
            domain_mapping,
            "generator_domain_id",
            context=f"domains[{index}]",
        )
        dependency_group = _require_non_empty_string(
            domain_mapping,
            "dependency_group",
            context=f"domains[{index}]",
        )

        domains.append(
            DomainConfig(
                domain_id=domain_id,
                generator_domain_id=generator_domain_id,
                generator_dir=(generator_root / generator_domain_id).resolve(),
                render_profile_path=_resolve_path(workspace_root, render_profile),
                dependency_group=dependency_group,
            )
        )

    return domains


def _load_yaml_mapping(path: Path, context: str) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"{context.capitalize()} file does not exist: {path}")

    text = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        if yaml is None:
            raise RuntimeError(
                f"{context.capitalize()} must be JSON-formatted YAML in environments without PyYAML: {path}"
            )
        payload = yaml.safe_load(text)
    return _ensure_mapping(payload, context=context)


def _resolve_path(base_dir: Path, value: str) -> Path:
    raw_path = Path(value)
    if raw_path.is_absolute():
        return raw_path.resolve()
    return (base_dir / raw_path).resolve()


def _ensure_mapping(value: Any, *, context: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{context} must be a mapping")
    return dict(value)


def _require_mapping(payload: Mapping[str, Any], key: str, *, context: str) -> dict[str, Any]:
    return _ensure_mapping(payload.get(key), context=f"{context}.{key}")


def _require_non_empty_string(payload: Mapping[str, Any], key: str, *, context: str) -> str:
    value = _require_string(payload, key, context=context)
    if not value.strip():
        raise ValueError(f"{context}.{key} must not be empty")
    return value.strip()


def _require_string(payload: Mapping[str, Any], key: str, *, context: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{context}.{key} must be a string")
    return value


def _require_bool(payload: Mapping[str, Any], key: str, *, context: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{context}.{key} must be a boolean")
    return value


def _require_int(payload: Mapping[str, Any], key: str, *, context: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{context}.{key} must be an integer")
    return value


def _require_positive_int(payload: Mapping[str, Any], key: str, *, context: str) -> int:
    value = _require_int(payload, key, context=context)
    if value <= 0:
        raise ValueError(f"{context}.{key} must be > 0")
    return value


def _read_string_list(payload: Mapping[str, Any], key: str, *, context: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{context}.{key} must be a list")
    items: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{context}.{key}[{index}] must be a non-empty string")
        items.append(item.strip())
    return items
