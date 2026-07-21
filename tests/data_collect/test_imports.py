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


def test_planimation_legacy_facades_export_required_symbols() -> None:
    rendering = importlib.import_module("src.data_collect.rendering")
    phase1 = importlib.import_module("scripts.planimation_phase1")
    pairing = importlib.import_module("scripts.phase3.planimation_pairing")

    assert all(
        hasattr(rendering, symbol)
        for symbol in ("_extract_png_archive", "FakeRenderer", "PlanimationRenderer", "render_candidate")
    )
    assert all(
        hasattr(phase1, symbol)
        for symbol in ("post_pddl_for_vfg", "render_vfg_to_local_png_frames", "extract_png_archive")
    )
    assert all(
        hasattr(pairing, symbol)
        for symbol in (
            "SCHEMA_VERSION",
            "PairingConfig",
            "RenderConfig",
            "build_pairing_manifest",
            "render_replay_states",
            "build_vlm_records",
            "validate_pairing_output",
            "_load_source_example",
            "_render_receipt_is_valid",
            "_trace_identity",
        )
    )


def test_rendering_facade_reexports_extracted_objects_by_identity() -> None:
    rendering = importlib.import_module("src.data_collect.rendering")
    render_archive = importlib.import_module("src.data_collect.render_archive")
    render_backends = importlib.import_module("src.data_collect.render_backends")
    render_fake = importlib.import_module("src.data_collect.render_fake")
    render_gates = importlib.import_module("src.data_collect.render_gates")
    render_preflight = importlib.import_module("src.data_collect.render_preflight")
    render_types = importlib.import_module("src.data_collect.render_types")

    assert rendering._extract_png_archive is render_archive._extract_png_archive
    assert rendering.FakeRenderer is render_fake.FakeRenderer
    assert rendering.PlanimationRenderer is render_backends.PlanimationRenderer
    assert rendering.RenderOutcome is render_types.RenderOutcome
    assert rendering.gate_rendered_candidate is render_gates.gate_rendered_candidate
    assert rendering.inspect_rendering_preflight is render_preflight.inspect_rendering_preflight
