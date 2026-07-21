"""Compatibility aggregator for modular Phase 3 pairing workflows."""

from __future__ import annotations

from .planimation_pairing_contracts import (
    ACTIVE_PLANNERS,
    CORE_BUCKETS,
    CORE_DOMAINS,
    CURRENT_TRACE_ROOTS,
    PNG_SIGNATURE,
    PairingConfig,
    RenderConfig,
    SourceSnapshotMismatch,
    StateRenderer,
    UnsupportedActivePlanner,
)
from .planimation_persisted_contracts import validate_pair_record, validate_state_render_record

SCHEMA_VERSION = "phase3_planimation_vlm_v1"

from .planimation_pairing_source import _load_source_example, _provenance_text, _provenance_line_index, _source_text, _assert_source_identity, _source_root_snapshot, _source_jsonl_rows, _assert_active_planner, _trace_identity, _repo_path
from .planimation_pairing_reasoning import compact_reasoning, _language_context, _find_action, _trim_payload, _planner_approximation, _state_summary
from .planimation_pairing_schema import _full_record, _step_record, _search_traversal_record, _hybrid_record, _write_pairing_schema, _write_vlm_schema, _hybrid_vlm_schema, _strict_object_schema, validate_vlm_record, validate_vlm_schema_instance, _schema_instance_errors, _matches_schema_type, _write_schema
from .planimation_pairing_rendering import render_state_with_planimation, _render_one_state, _write_problem_state, _balanced_end, _profile_path, _valid_png, _png_metadata, _cache_identity, _valid_vfg, _validated_cache, _assert_repo_output_root, _assert_source_output_disjoint
from .planimation_pairing_manifest import build_pairing_manifest, _pair_record, _exclusion_reasons, _has_recovery, _vfg_actions, _alignment_status, _pairing_summary
from .planimation_pairing_replay import render_replay_states, _render_transitions, _search_traversal_transitions
from .planimation_pairing_records import build_vlm_records, _recordable_render_rows, _write_hybrid_output_manifest, _reconcile_hybrid_output_manifest
from .planimation_pairing_validation import _render_receipt_is_valid, validate_pairing_output, validate_vlm_output

__all__ = (
    "ACTIVE_PLANNERS",
    "CORE_BUCKETS",
    "CORE_DOMAINS",
    "CURRENT_TRACE_ROOTS",
    "PNG_SIGNATURE",
    "PairingConfig",
    "RenderConfig",
    "SourceSnapshotMismatch",
    "StateRenderer",
    "UnsupportedActivePlanner",
    "validate_pair_record",
    "validate_state_render_record",
    "SCHEMA_VERSION",
    "_load_source_example",
    "_provenance_text",
    "_provenance_line_index",
    "_source_text",
    "_assert_source_identity",
    "_source_root_snapshot",
    "_source_jsonl_rows",
    "_assert_active_planner",
    "_trace_identity",
    "_repo_path",
    "compact_reasoning",
    "_language_context",
    "_find_action",
    "_trim_payload",
    "_planner_approximation",
    "_state_summary",
    "_full_record",
    "_step_record",
    "_search_traversal_record",
    "_hybrid_record",
    "_write_pairing_schema",
    "_write_vlm_schema",
    "_hybrid_vlm_schema",
    "_strict_object_schema",
    "validate_vlm_record",
    "validate_vlm_schema_instance",
    "_schema_instance_errors",
    "_matches_schema_type",
    "_write_schema",
    "render_state_with_planimation",
    "_render_one_state",
    "_write_problem_state",
    "_balanced_end",
    "_profile_path",
    "_valid_png",
    "_png_metadata",
    "_cache_identity",
    "_valid_vfg",
    "_validated_cache",
    "_assert_repo_output_root",
    "_assert_source_output_disjoint",
    "build_pairing_manifest",
    "_pair_record",
    "_exclusion_reasons",
    "_has_recovery",
    "_vfg_actions",
    "_alignment_status",
    "_pairing_summary",
    "render_replay_states",
    "_render_transitions",
    "_search_traversal_transitions",
    "build_vlm_records",
    "_recordable_render_rows",
    "_write_hybrid_output_manifest",
    "_reconcile_hybrid_output_manifest",
    "_render_receipt_is_valid",
    "validate_pairing_output",
    "validate_vlm_output",
)

_LEGACY_EXPORTS = (
    ACTIVE_PLANNERS,
    CORE_BUCKETS,
    CORE_DOMAINS,
    CURRENT_TRACE_ROOTS,
    PNG_SIGNATURE,
    PairingConfig,
    RenderConfig,
    SourceSnapshotMismatch,
    StateRenderer,
    UnsupportedActivePlanner,
    validate_pair_record,
    validate_state_render_record,
    _load_source_example,
    _provenance_text,
    _provenance_line_index,
    _source_text,
    _assert_source_identity,
    _assert_active_planner,
    _trace_identity,
    _repo_path,
    compact_reasoning,
    _language_context,
    _find_action,
    _trim_payload,
    _planner_approximation,
    _state_summary,
    _full_record,
    _step_record,
    _search_traversal_record,
    _hybrid_record,
    _write_pairing_schema,
    _write_vlm_schema,
    _hybrid_vlm_schema,
    _strict_object_schema,
    validate_vlm_record,
    validate_vlm_schema_instance,
    _schema_instance_errors,
    _matches_schema_type,
    _write_schema,
    render_state_with_planimation,
    _render_one_state,
    _write_problem_state,
    _balanced_end,
    _profile_path,
    _valid_png,
    _png_metadata,
    _cache_identity,
    _valid_vfg,
    _validated_cache,
    _assert_repo_output_root,
    _assert_source_output_disjoint,
    build_pairing_manifest,
    _pair_record,
    _exclusion_reasons,
    _has_recovery,
    _vfg_actions,
    _alignment_status,
    _pairing_summary,
    render_replay_states,
    _render_transitions,
    _search_traversal_transitions,
    build_vlm_records,
    _recordable_render_rows,
    _write_hybrid_output_manifest,
    _reconcile_hybrid_output_manifest,
    _render_receipt_is_valid,
    validate_pairing_output,
    validate_vlm_output,
)


def _synchronize_source_hooks() -> None:
    from . import planimation_pairing_manifest as manifest
    from . import planimation_pairing_source as source
    source._source_jsonl_rows = _source_jsonl_rows
    source._source_root_snapshot = _source_root_snapshot
    manifest._source_jsonl_rows = _source_jsonl_rows
    manifest._source_root_snapshot = _source_root_snapshot


def build_pairing_manifest(*args, **kwargs):
    _synchronize_source_hooks()
    from .planimation_pairing_manifest import build_pairing_manifest as implementation
    return implementation(*args, **kwargs)


def render_replay_states(*args, **kwargs):
    _synchronize_source_hooks()
    from .planimation_pairing_replay import render_replay_states as implementation
    return implementation(*args, **kwargs)


def build_vlm_records(*args, **kwargs):
    _synchronize_source_hooks()
    from .planimation_pairing_records import build_vlm_records as implementation
    return implementation(*args, **kwargs)


def validate_pairing_output(*args, **kwargs):
    _synchronize_source_hooks()
    from .planimation_pairing_validation import validate_pairing_output as implementation
    return implementation(*args, **kwargs)
