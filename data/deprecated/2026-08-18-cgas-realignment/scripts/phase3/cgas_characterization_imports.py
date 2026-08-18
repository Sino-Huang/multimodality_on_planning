from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass
from pathlib import Path

from .cgas_characterization_import_policy import import_resolution_violation


@dataclass(frozen=True, slots=True)
class ImportClosureError(ValueError):
    reason: str
    module: str

    def __str__(self) -> str:
        return f"{self.reason}:{self.module}"


@dataclass(frozen=True, slots=True)
class ImplementationFile:
    path: str
    sha256: str


def implementation_closure(repository_root: Path, module_roots: tuple[str, ...]) -> tuple[ImplementationFile, ...]:
    pending = list(sorted(module_roots))
    seen: set[str] = set()
    files: dict[str, ImplementationFile] = {}
    while pending:
        module = pending.pop(0)
        if module in seen:
            continue
        seen.add(module)
        path = _resolve_module(repository_root, module)
        if path is None:
            raise ImportClosureError("unresolved_local_import", module)
        relative = path.relative_to(repository_root).as_posix()
        contents = path.read_bytes()
        files[relative] = ImplementationFile(relative, hashlib.sha256(contents).hexdigest())
        tree = ast.parse(contents, filename=relative)
        violation = import_resolution_violation(tree)
        if violation is not None:
            raise ImportClosureError(violation, module)
        dependencies = _dependencies(tree, module, repository_root)
        dependencies.update(_package_modules(module, repository_root))
        pending.extend(name for name in dependencies if name not in seen)
    return tuple(files[path] for path in sorted(files))


def _dependencies(tree: ast.Module, module: str, root: Path) -> set[str]:
    dependencies: set[str] = set()
    module_path = _resolve_module(root, module)
    if module_path is None:
        raise ImportClosureError("unresolved_local_import", module)
    is_package = module_path.name == "__init__.py"
    for node in ast.walk(tree):
        match node:
            case ast.Import(names=names):
                for alias in names:
                    _add_if_local(dependencies, alias.name, root)
            case ast.ImportFrom(module=base, level=level, names=names):
                resolved = _relative_module(module, base, level, is_package)
                _add_import_from_base(dependencies, resolved, level, root)
                for alias in names:
                    if alias.name != "*":
                        _add_if_local(dependencies, f"{resolved}.{alias.name}", root)
    return dependencies


def _add_import_from_base(dependencies: set[str], module: str, level: int, root: Path) -> None:
    if level and _resolve_module(root, module) is None:
        raise ImportClosureError("unresolved_local_import", module)
    _add_if_local(dependencies, module, root)


def _package_modules(module: str, root: Path) -> set[str]:
    parts = module.split(".")
    modules = {".".join(parts[:index]) for index in range(1, len(parts))}
    return {name for name in modules if (root.joinpath(*name.split(".")) / "__init__.py").is_file()}


def _relative_module(current: str, imported: str | None, level: int, is_package: bool) -> str:
    if level == 0:
        return imported or ""
    package = current if is_package else current.rsplit(".", 1)[0] if "." in current else ""
    parents = package.split(".") if package else []
    if level > len(parents) + 1:
        raise ImportClosureError("unresolved_local_import", current)
    prefix = ".".join(parents[: len(parents) - level + 1])
    return ".".join(part for part in (prefix, imported or "") if part)


def _add_if_local(dependencies: set[str], module: str, root: Path) -> None:
    if module and _resolve_module(root, module) is not None:
        dependencies.add(module)


def _resolve_module(root: Path, module: str) -> Path | None:
    parts = module.split(".")
    file_path = root.joinpath(*parts).with_suffix(".py")
    package_path = root.joinpath(*parts) / "__init__.py"
    if file_path.is_file() and package_path.is_file():
        raise ImportClosureError("ambiguous_local_import", module)
    candidate = file_path if file_path.is_file() else package_path if package_path.is_file() else None
    if candidate is None:
        return None
    _reject_symlink_path(root, candidate, module)
    _package_initializers(root, candidate)
    return candidate


def _package_initializers(root: Path, path: Path) -> None:
    current = path.parent
    while current != root:
        initializer = current / "__init__.py"
        if current.is_symlink() or initializer.is_symlink():
            raise ImportClosureError("symlink_local_import", current.relative_to(root).as_posix())
        if initializer.exists() and not initializer.is_file():
            raise ImportClosureError("ambiguous_local_import", current.relative_to(root).as_posix())
        current = current.parent

def _reject_symlink_path(root: Path, candidate: Path, module: str) -> None:
    current = root
    for part in candidate.relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            raise ImportClosureError("symlink_local_import", module)
