from __future__ import annotations

import importlib


MODULES = [
    "src.data_collect",
    "src.data_collect.cli",
    "src.data_collect.config",
    "src.data_collect.tools",
    "src.data_collect.metadata",
    "src.data_collect.hashing",
    "src.data_collect.rendering",
    "src.data_collect.difficulty",
    "src.data_collect.selection",
    "src.data_collect.generate",
    "src.data_collect.adapters",
]


def test_placeholder_modules_import_cleanly() -> None:
    for module_name in MODULES:
        importlib.import_module(module_name)
