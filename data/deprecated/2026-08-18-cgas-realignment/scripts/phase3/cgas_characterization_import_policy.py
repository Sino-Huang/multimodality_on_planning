from __future__ import annotations

import ast


_DYNAMIC_IMPORTS = frozenset(
    {
        "__import__",
        "builtins.__import__",
        "importlib.import_module",
        "importlib.reload",
        "importlib.util.spec_from_file_location",
        "runpy.run_module",
        "runpy.run_path",
    }
)
_DYNAMIC_CODE = frozenset(
    {"compile", "eval", "exec", "builtins.compile", "builtins.eval", "builtins.exec"}
)
_REFLECTION_BUILTINS = frozenset(
    {"getattr", "vars", "globals", "locals", "builtins.getattr", "builtins.vars", "builtins.globals", "builtins.locals"}
)
_SITE_PATH_CALLS = frozenset(
    {
        "site.addpackage",
        "site.addsitedir",
        "site.execsitecustomize",
        "site.execusercustomize",
        "site.main",
    }
)
_ENVIRONMENT_MUTATORS = frozenset(
    {"os.environ.clear", "os.environ.pop", "os.environ.setdefault", "os.environ.update", "os.putenv"}
)


def import_resolution_violation(tree: ast.Module) -> str | None:
    aliases = _aliases(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            reason = _call_violation(node, aliases)
            if reason is not None:
                return reason
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            reason = _assignment_violation(node, aliases)
            if reason is not None:
                return reason
    return None


def _aliases(tree: ast.Module) -> dict[str, str]:
    bindings: dict[str, str] = {}
    for node in ast.walk(tree):
        match node:
            case ast.Import(names=names):
                for alias in names:
                    bindings[alias.asname or alias.name.split(".")[0]] = alias.name
            case ast.ImportFrom(module=module, names=names) if module is not None:
                for alias in names:
                    if alias.name != "*":
                        bindings[alias.asname or alias.name] = f"{module}.{alias.name}"
    while _propagate_assignment_aliases(tree, bindings):
        pass
    return bindings


def _propagate_assignment_aliases(tree: ast.Module, bindings: dict[str, str]) -> bool:
    changed = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        source = _name(node.value, bindings)
        if not _sensitive_import_name(source):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and bindings.get(target.id) != source:
                bindings[target.id] = source
                changed = True
    return changed


def _sensitive_import_name(name: str) -> bool:
    return name == "builtins" or name in _DYNAMIC_CODE | _DYNAMIC_IMPORTS | _REFLECTION_BUILTINS or name.startswith(("importlib.", "os.", "site.", "sys.", "runpy."))


def _call_violation(node: ast.Call, aliases: dict[str, str]) -> str | None:
    reflection = _reflection_violation(node, aliases)
    if reflection is not None:
        return reflection
    name = _name(node.func, aliases)
    if name in _DYNAMIC_IMPORTS:
        return "dynamic_import"
    if name in _DYNAMIC_CODE:
        return "dynamic_code_execution"
    if name.startswith("sys.path."):
        return "sys_path_mutation"
    if name in _SITE_PATH_CALLS:
        return "site_path_mutation"
    if name in _ENVIRONMENT_MUTATORS:
        return "pythonpath_mutation"
    return None


def _reflection_violation(node: ast.Call, aliases: dict[str, str]) -> str | None:
    name = _name(node.func, aliases)
    if name in {"getattr", "builtins.getattr"}:
        return _reflection_target_violation(_getattr_target(node, aliases))
    if name in {"globals", "builtins.globals", "locals", "builtins.locals"}:
        return "reflection_namespace_access"
    match node.func:
        case ast.Subscript(value=value, slice=ast.Constant(value=str() as attribute)):
            return _subscript_reflection_violation(value, attribute, aliases)
        case _:
            return None


def _getattr_target(node: ast.Call, aliases: dict[str, str]) -> str:
    if len(node.args) < 2 or not isinstance(node.args[1], ast.Constant) or not isinstance(node.args[1].value, str):
        return ""
    base = _name(node.args[0], aliases)
    return f"{base}.{node.args[1].value}" if base else ""


def _subscript_reflection_violation(value: ast.expr, attribute: str, aliases: dict[str, str]) -> str | None:
    match value:
        case ast.Call(func=func, args=(target,)) if _name(func, aliases) in {"vars", "builtins.vars"}:
            base = _name(target, aliases)
            return _reflection_target_violation(f"{base}.{attribute}" if base else "")
        case ast.Call(func=func) if _name(func, aliases) in {"globals", "builtins.globals", "locals", "builtins.locals"}:
            return "reflection_namespace_access"
        case _:
            return None


def _reflection_target_violation(target: str) -> str | None:
    if target in _DYNAMIC_IMPORTS:
        return "dynamic_import_reflection"
    if target in _DYNAMIC_CODE:
        return "dynamic_code_execution"
    if target == "sys.path":
        return "sys_path_reflection"
    if target == "os.environ":
        return "pythonpath_reflection"
    if target in _SITE_PATH_CALLS:
        return "site_path_mutation"
    return None


def _assignment_violation(node: ast.Assign | ast.AnnAssign | ast.AugAssign, aliases: dict[str, str]) -> str | None:
    targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
    for target in targets:
        name = _target_name(target, aliases)
        if name == "sys.path":
            return "sys_path_mutation"
        if name == "os.environ":
            return "pythonpath_mutation"
    return None


def _target_name(node: ast.expr, aliases: dict[str, str]) -> str:
    match node:
        case ast.Subscript(value=value):
            return _name(value, aliases)
        case _:
            return _name(node, aliases)


def _name(node: ast.expr, aliases: dict[str, str]) -> str:
    match node:
        case ast.Name(id="__builtins__"):
            return "builtins"
        case ast.Name(id=name):
            return aliases.get(name, name)
        case ast.Attribute(value=value, attr=attribute):
            prefix = _name(value, aliases)
            return f"{prefix}.{attribute}" if prefix else attribute
        case _:
            return ""
