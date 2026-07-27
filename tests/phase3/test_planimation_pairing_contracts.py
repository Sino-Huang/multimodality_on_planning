from __future__ import annotations

from pathlib import Path

from scripts.phase3.planimation_pairing_contracts import (
    CURRENT_IMAGE_FRAME_ROOT,
    CURRENT_SELECTION_CACHE_ROOT,
    CURRENT_TEXT_RECORD_ROOT,
    CURRENT_TRACE_ROOTS,
)


def test_current_trace_roots_resolve_to_canonical_reasoning_location() -> None:
    assert CURRENT_TRACE_ROOTS == (
        Path("outputs/reasoning_traces/curriculum/phase3_curriculum_traces_safe_no_visitall_strict_v1_1st_round"),
    )


def test_current_pairing_artifacts_resolve_to_three_category_layout() -> None:
    # Given: the canonical locations for frames, selection, and text-only records.
    # When: the pairing contract exposes its active artifact roots.
    # Then: each root resolves within its approved output category.
    assert CURRENT_IMAGE_FRAME_ROOT == Path(
        "outputs/image_frames/phase3_planimation_frames_stratified_pilot_20260725"
    )
    assert CURRENT_SELECTION_CACHE_ROOT == Path(
        "outputs/image_frames/phase3_planimation_frames_safe_no_visitall_strict_v1_20260722_005800"
    )
    assert CURRENT_TEXT_RECORD_ROOT == Path(
        "outputs/reasoning_traces/vlm_records/stratified_pilot_20260725"
    )
