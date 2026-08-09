from __future__ import annotations

import hashlib
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from .cgas_candidate_characterization_contracts import canonical_bytes
from .cgas_candidate_characterization_models import JsonObject
from .cgas_pilot_manifest_selection import PilotManifestError


def validate_pilot_approval(scope_report_path: Path, approval_path: Path) -> str:
    scope, scope_contents = read_json(scope_report_path, "pilot_scope_report_invalid")
    approval, approval_contents = read_json(approval_path, "pilot_owner_approval_invalid")
    if approval_contents != canonical_bytes(approval) + b"\n":
        raise PilotManifestError("pilot_owner_approval_noncanonical", approval_path)
    required: JsonObject = {
        "approval_scope": "cgas_phase3_pilot_manifest_and_row_budget",
        "decisions": _approved_decisions(),
        "owner_approved": True,
        "schema_version": "cgas_phase3_pilot_owner_approval_v1",
        "scope_report_sha256": sha256(scope_contents),
        "status": "approved_pilot_scope",
    }
    if any(approval.get(key) != value for key, value in required.items()):
        raise PilotManifestError("pilot_scope_report_mismatch", approval_path)
    if scope.get("schema_version") != "cgas_phase3_pilot_scope_v1" or scope.get("read_only") is not True:
        raise PilotManifestError("pilot_scope_report_invalid", scope_report_path)
    if approval.get("scope_report_bindings") != scope.get("bindings"):
        raise PilotManifestError("pilot_scope_binding_mismatch", approval_path)
    owner_id = approval.get("owner_id")
    approved_at = approval.get("approved_at")
    if not isinstance(owner_id, str) or not owner_id or not isinstance(approved_at, str) or not approved_at:
        raise PilotManifestError("pilot_owner_identity_missing", approval_path)
    decision_path = approval.get("provenance_decision_path")
    decision_digest = approval.get("provenance_decision_sha256")
    if not isinstance(decision_path, str) or not isinstance(decision_digest, str):
        raise PilotManifestError("pilot_provenance_binding_invalid", approval_path)
    repository_root = scope_report_path.resolve().parents[3]
    if sha256(read_bytes(repository_root / decision_path, "pilot_provenance_decision_unreadable")) != decision_digest:
        raise PilotManifestError("pilot_provenance_binding_invalid", approval_path)
    return sha256(approval_contents)


def read_json(path: Path, code: str) -> tuple[JsonObject, bytes]:
    contents = read_bytes(path, code)
    try:
        return TypeAdapter(JsonObject).validate_json(contents), contents
    except ValidationError as error:
        raise PilotManifestError(code, path) from error


def read_bytes(path: Path, code: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise PilotManifestError(code, path) from error


def sha256(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


def _approved_decisions() -> JsonObject:
    return {
        "diversity_floor": {
            "instances_per_object_count": 30,
            "minimum_goal_edge_levels_per_object_count": 3,
            "minimum_instances_per_repeated_signature": 2,
            "minimum_repeated_composition_signatures_per_object_count": 5,
            "minimum_stack_profiles_per_object_count": 3,
            "object_counts": [4, 8, 12],
        },
        "harvest": "off_plan",
        "pilot_provenance": "reproducibility_only",
        "provenance_conditions": {
            "never_release": True,
            "phase0c_production_precedence": True,
            "pin_inputs": True,
            "verify_steps_required": True,
        },
        "stability_bar": 10,
    }
