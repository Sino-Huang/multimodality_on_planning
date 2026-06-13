from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any

from .adapters import AdapterCapability, DomainSelection, build_adapter_capability_matrix
from .config import DEFAULT_CURRICULUM_CONFIG_PATH

try:
    import yaml
except ImportError:  # pragma: no cover - depends on runtime environment
    yaml = None


@dataclass(frozen=True)
class CommandCapability:
    name: str
    available: bool
    path: str | None
    version: str | None


@dataclass(frozen=True)
class PythonPackageCapability:
    name: str
    installed: bool
    version: str | None


@dataclass(frozen=True)
class DependencyGroupCapability:
    group_id: str
    generator_domain_id: str
    python_runtime: str
    python_packages: tuple[PythonPackageCapability, ...]
    missing_python_packages: tuple[str, ...]
    uv_install_command: str | None
    system_tools: tuple[str, ...]
    build_required: bool
    build_commands: tuple[str, ...]
    notes: str


@dataclass(frozen=True)
class RenderProfileCapability:
    domain_id: str
    path: str
    exists: bool


@dataclass(frozen=True)
class ToolInspectionReport:
    config_path: str
    workspace_root: str
    generator_root: str
    generator_root_exists: bool
    python: CommandCapability
    commands: dict[str, CommandCapability]
    downward_root: str
    planner_command: CommandCapability
    validator_command: CommandCapability
    dependency_groups: tuple[DependencyGroupCapability, ...]
    render_profiles: tuple[RenderProfileCapability, ...]
    adapter_matrix: tuple[AdapterCapability, ...]
    require_rendering: bool
    rendering_ready: bool
    ready: bool
    issues: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def inspect_tools(config_path: Path | str = DEFAULT_CURRICULUM_CONFIG_PATH) -> ToolInspectionReport:
    resolved_config_path = Path(config_path).resolve()
    curriculum_payload = _load_mapping_file(resolved_config_path, context="curriculum config")

    workspace_root = _resolve_path(
        resolved_config_path.parent,
        _require_non_empty_string(curriculum_payload, "workspace_root", context="curriculum config"),
    )
    generator_root = _resolve_path(
        workspace_root,
        _require_non_empty_string(curriculum_payload, "generator_root", context="curriculum config"),
    )
    dependency_config_path = _resolve_path(
        workspace_root,
        _require_non_empty_string(curriculum_payload, "dependency_config", context="curriculum config"),
    )

    require_rendering = _require_bool(curriculum_payload, "require_rendering", context="curriculum config")

    python_capability = _capture_command(sys.executable, sys.executable)
    command_capabilities = {
        "uv": _capture_command("uv", "uv"),
        "make": _capture_command("make", "make"),
        "g++": _capture_command("g++", "g++"),
        "cmake": _capture_command("cmake", "cmake"),
    }

    downward_root = (workspace_root / "modules" / "downward").resolve()
    planner_command = _capture_command(str(downward_root / "fast-downward.py"), str(downward_root / "fast-downward.py"))
    validator_command = _capture_command("validate", "validate")

    dependency_groups_payload = _load_dependency_groups(dependency_config_path)
    dependency_groups = tuple(
        _build_dependency_group_capability(group_id, group_payload)
        for group_id, group_payload in dependency_groups_payload.items()
    )

    domain_payloads = _read_domain_payloads(curriculum_payload)
    render_profiles = tuple(_build_render_profile_capability(domain_payload, workspace_root) for domain_payload in domain_payloads)
    adapter_matrix = build_adapter_capability_matrix(
        tuple(_build_domain_selection(domain_payload, generator_root) for domain_payload in domain_payloads)
    )

    generator_root_exists = generator_root.exists()
    render_profile_missing_domains = [profile.domain_id for profile in render_profiles if not profile.exists]
    missing_dependency_groups = [group.group_id for group in dependency_groups if group.missing_python_packages]
    adapter_failures = [
        (capability.domain_id, failure)
        for capability in adapter_matrix
        for failure in capability.readiness_failures
    ]

    issues: list[str] = []
    if not generator_root_exists:
        issues.append(f"generator_root missing: {generator_root}")
    if not planner_command.available:
        issues.append(f"planner command missing: {planner_command.path}")
    if not validator_command.available:
        issues.append("validator command missing: validate")
    for domain_id in render_profile_missing_domains:
        issues.append(f"render profile missing for domain: {domain_id}")
    for group_id in missing_dependency_groups:
        issues.append(f"missing python packages in dependency group: {group_id}")
    for domain_id, failure in adapter_failures:
        issues.append(f"adapter readiness failure for domain {domain_id}: {failure.code}: {failure.message}")

    rendering_ready = (not require_rendering) or not render_profile_missing_domains
    adapters_ready = all(capability.ready for capability in adapter_matrix)
    ready = generator_root_exists and rendering_ready and adapters_ready

    return ToolInspectionReport(
        config_path=str(resolved_config_path),
        workspace_root=str(workspace_root),
        generator_root=str(generator_root),
        generator_root_exists=generator_root_exists,
        python=python_capability,
        commands=command_capabilities,
        downward_root=str(downward_root),
        planner_command=planner_command,
        validator_command=validator_command,
        dependency_groups=dependency_groups,
        render_profiles=render_profiles,
        adapter_matrix=adapter_matrix,
        require_rendering=require_rendering,
        rendering_ready=rendering_ready,
        ready=ready,
        issues=tuple(issues),
    )


def report_tools_json(config_path: Path | str = DEFAULT_CURRICULUM_CONFIG_PATH) -> str:
    return json.dumps(inspect_tools(config_path).to_dict(), indent=2, sort_keys=True)


def _build_dependency_group_capability(group_id: str, group_payload: Mapping[str, Any]) -> DependencyGroupCapability:
    python_packages = tuple(
        _build_python_package_capability(package_name)
        for package_name in _read_string_list(group_payload, "python_packages", context=f"dependency_groups.{group_id}")
    )
    missing_python_packages = tuple(package.name for package in python_packages if not package.installed)
    uv_install_command = f"uv pip install {' '.join(missing_python_packages)}" if missing_python_packages else None

    build_payload = _require_mapping(group_payload, "build", context=f"dependency_groups.{group_id}")
    return DependencyGroupCapability(
        group_id=group_id,
        generator_domain_id=_require_non_empty_string(
            group_payload,
            "generator_domain_id",
            context=f"dependency_groups.{group_id}",
        ),
        python_runtime=_require_non_empty_string(group_payload, "python_runtime", context=f"dependency_groups.{group_id}"),
        python_packages=python_packages,
        missing_python_packages=missing_python_packages,
        uv_install_command=uv_install_command,
        system_tools=tuple(_read_string_list(group_payload, "system_tools", context=f"dependency_groups.{group_id}")),
        build_required=_require_bool(build_payload, "required", context=f"dependency_groups.{group_id}.build"),
        build_commands=tuple(_read_string_list(build_payload, "commands", context=f"dependency_groups.{group_id}.build")),
        notes=_require_string(group_payload, "notes", context=f"dependency_groups.{group_id}"),
    )


def _build_render_profile_capability(domain_payload: Mapping[str, Any], workspace_root: Path) -> RenderProfileCapability:
    domain_id = _require_non_empty_string(domain_payload, "domain_id", context="domains")
    render_profile_path = _resolve_path(
        workspace_root,
        _require_non_empty_string(domain_payload, "render_profile_path", context=f"domains.{domain_id}"),
    )
    return RenderProfileCapability(domain_id=domain_id, path=str(render_profile_path), exists=render_profile_path.exists())


def _build_python_package_capability(package_name: str) -> PythonPackageCapability:
    try:
        version = importlib_metadata.version(package_name)
    except importlib_metadata.PackageNotFoundError:
        return PythonPackageCapability(name=package_name, installed=False, version=None)
    return PythonPackageCapability(name=package_name, installed=True, version=version)


def _capture_command(name: str, command: str) -> CommandCapability:
    command_path = shutil.which(command) if command != sys.executable else sys.executable
    if command_path is None:
        return CommandCapability(name=name, available=False, path=None, version=None)

    version = _read_command_version(command_path, command)
    return CommandCapability(name=name, available=True, path=command_path, version=version)


def _read_command_version(command_path: str, command: str) -> str | None:
    if command == sys.executable:
        return sys.version.split()[0]

    version_args = {
        "uv": ("--version",),
        "make": ("--version",),
        "g++": ("--version",),
        "cmake": ("--version",),
    }.get(command, ("--version",))

    completed = subprocess.run(
        [command_path, *version_args],
        check=False,
        text=True,
        capture_output=True,
    )
    output = (completed.stdout or completed.stderr).strip()
    if not output:
        return None
    return output.splitlines()[0].strip()


def _load_dependency_groups(path: Path) -> dict[str, dict[str, Any]]:
    payload = _load_mapping_file(path, context="generator dependency config")
    groups_payload = _require_mapping(payload, "dependency_groups", context="generator dependency config")
    return groups_payload


def _read_domain_payloads(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    domains_payload = payload.get("domains")
    if not isinstance(domains_payload, list):
        raise ValueError("curriculum config field 'domains' must be a list")
    return [domain_payload for domain_payload in domains_payload if isinstance(domain_payload, Mapping)]


def _build_domain_selection(domain_payload: Mapping[str, Any], generator_root: Path) -> DomainSelection:
    domain_id = _require_non_empty_string(domain_payload, "domain_id", context="domains")
    generator_domain_id = _require_non_empty_string(domain_payload, "generator_domain_id", context=f"domains.{domain_id}")
    return DomainSelection(
        domain_id=domain_id,
        generator_domain_id=generator_domain_id,
        generator_dir=(generator_root / generator_domain_id).resolve(),
    )


def _load_mapping_file(path: Path, *, context: str) -> dict[str, Any]:
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
