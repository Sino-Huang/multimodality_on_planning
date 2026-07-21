# Phase 3 F2 Exception Boundaries

Planimation production paths must distinguish expected operational failures from adapter and programming defects. Retry or persisted-failure boundaries should catch only the specific filesystem, runtime, parsing, archive, image, decoding, and validation errors that their contracts model. Do not use `except Exception` or `# noqa: BLE001` in these paths.

The regression in `tests/data_collect/test_rendering.py` verifies that an injected adapter `AttributeError` propagates through `render_candidate()`. Preserve this behavior when changing `PlanimationRenderer`.

Use the `PddlPoster`, `VfgPoster`, `LocalFrameRenderer`, `ArchiveExtractor`, and `HostPreflight` protocols for injected adapters instead of callable `Any` annotations.
