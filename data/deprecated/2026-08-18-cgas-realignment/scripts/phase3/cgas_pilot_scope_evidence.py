from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from . import cgas_trace_contract_v3
from .cgas_candidate_characterization_contracts import (
    CandidateCharacterizationError,
    parse_canonical_model,
    validate_approval,
)
from .cgas_candidate_characterization_models import CheckpointModel, JsonObject
from .cgas_candidate_contracts import load_config
from .cgas_gate0b_verifier import verify_gate0b_round
from .cgas_pilot_scope import PilotScopeReport, analyze_rows


@dataclass(frozen=True, slots=True)
class AnalysisRequest:
    repository_root: Path
    characterization_root: Path
    approval_path: Path
    candidate_config_path: Path
    output_root: Path
    command: str


@dataclass(frozen=True, slots=True)
class EvidenceBindings:
    checkpoint_path: str
    checkpoint_sha256: str
    current_index_path: str
    current_index_sha256: str
    approved_trace_path: str
    approved_trace_sha256: str
    owner_approval_sha256: str
    contract_sha256: str
    policy_sha256: str
    candidate_config_path: str
    candidate_config_sha256: str
    selector_config_sha256: str
    selector_implementation_sha256: str
    analysis_implementation_sha256: str
    evidence_adapter_sha256: str
    release_sha256: str


@dataclass(frozen=True, slots=True)
class PilotScopeEvidence:
    schema_version: str
    read_only: bool
    command: str
    bindings: EvidenceBindings
    report: PilotScopeReport


def write_signed_evidence(request: AnalysisRequest) -> PilotScopeEvidence:
    approval, approval_digest = validate_approval(request.approval_path)
    config = load_config(request.candidate_config_path)
    gate = verify_gate0b_round(
        request.repository_root,
        request.characterization_root,
        request.approval_path,
        request.candidate_config_path,
    )
    checkpoint, checkpoint_contents = parse_canonical_model(
        gate.checkpoint_path,
        CheckpointModel,
        "pilot_scope_checkpoint_invalid",
    )
    rows = _rows(checkpoint, gate.checkpoint_path)
    current = request.characterization_root / "current.json"
    bindings = EvidenceBindings(
        checkpoint_path=_relative(gate.checkpoint_path, request.repository_root),
        checkpoint_sha256=_sha256(checkpoint_contents),
        current_index_path=_relative(current, request.repository_root),
        current_index_sha256=_sha256(current.read_bytes()),
        approved_trace_path=_relative(request.approval_path, request.repository_root),
        approved_trace_sha256=approval_digest,
        owner_approval_sha256=approval.owner_approval_sha256,
        contract_sha256=approval.contract_sha256,
        policy_sha256=approval.policy_sha256,
        candidate_config_path=_relative(request.candidate_config_path, request.repository_root),
        candidate_config_sha256=config.sha256,
        selector_config_sha256=checkpoint.selector.config_sha256,
        selector_implementation_sha256=checkpoint.selector.implementation_sha256,
        analysis_implementation_sha256=_sha256(Path(__file__).with_name("cgas_pilot_scope.py").read_bytes()),
        evidence_adapter_sha256=_sha256(Path(__file__).read_bytes()),
        release_sha256=cgas_trace_contract_v3.TRACE_V1_RELEASE_SHA256,
    )
    evidence = PilotScopeEvidence(
        "cgas_phase3_pilot_scope_v1",
        True,
        request.command,
        bindings,
        analyze_rows(rows),
    )
    request.output_root.mkdir(parents=True, exist_ok=True)
    (request.output_root / "report.json").write_text(
        json.dumps(asdict(evidence), allow_nan=False, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (request.output_root / "report.txt").write_text(_render(evidence), encoding="utf-8")
    return evidence


def _rows(checkpoint: CheckpointModel, path: Path) -> tuple[JsonObject, ...]:
    contents = checkpoint.characterization.canonical_jsonl.encode()
    try:
        rows = tuple(TypeAdapter(JsonObject).validate_json(line) for line in contents.splitlines())
    except ValidationError as error:
        raise CandidateCharacterizationError("pilot_scope_rows_invalid", path) from error
    if _sha256(contents) != checkpoint.characterization.sha256 or len(rows) != checkpoint.characterization.row_count:
        raise CandidateCharacterizationError("pilot_scope_rows_invalid", path)
    return rows


def _render(evidence: PilotScopeEvidence) -> str:
    report = evidence.report
    lines = [
        "CGAS Phase 3 pilot-scope analysis",
        "",
        f"checkpoint: {evidence.bindings.checkpoint_sha256}",
        f"approval:   {evidence.bindings.approved_trace_sha256}",
        f"contract:   {evidence.bindings.contract_sha256}",
        f"policy:     {evidence.bindings.policy_sha256}",
        f"config:     {evidence.bindings.candidate_config_sha256}",
        f"command:    {evidence.command}",
        "",
        f"characterized candidates: {report.characterized_candidate_count}",
        f"paired-exact candidates:  {report.paired_exact_count}",
        (
            f"plan length: mean {report.plan_length.mean:.3f}, "
            f"median {report.plan_length.median:g}, max {report.plan_length.maximum}"
        ),
        (
            f"on-plan certificate rows: mean {report.on_plan_certificate_rows.mean:.3f}, "
            f"total {report.on_plan_certificate_rows.total}"
        ),
        (
            f"off-plan certificate capacity: mean {report.off_plan_certificate_rows.mean:.3f}, "
            f"total {report.off_plan_certificate_rows.total}"
        ),
        (
            f"off-plan-only capacity: mean {report.off_plan_only_certificate_rows.mean:.3f}, "
            f"total {report.off_plan_only_certificate_rows.total}"
        ),
        "",
        "object  candidates  compositions  repeated>=2  stack-profiles  goal-edge-levels",
    ]
    lines.extend(
        f"{item.object_count:>6}  {item.candidates:>10}  {item.composition_signatures:>12}  "
        f"{item.repeated_composition_signatures:>11}  {item.structural_profiles:>14}  {item.goal_edge_levels:>16}"
        for item in report.per_object_count
    )
    floor = report.diversity_floor
    lines.extend(
        [
            "",
            "proposed diversity floor: >=30 candidates/object count; >=5 composition signatures/object count",
            "  with >=2 candidates/signature; >=3 stack profiles and >=3 goal-edge levels/object count",
            f"diversity floor passed: {str(floor.passed).lower()}",
            "",
            "bar  fail  harvest   raw-by-count             pilot-by-count           total  pool-feasible",
        ]
    )
    lines.extend(
        f"{item.bar:>3}  {item.failure_rate:>4.0%}  {item.harvest:<9} "
        f"{item.raw_instances_by_object_count!s:<24} {item.pilot_instances_by_object_count!s:<24} "
        f"{item.pilot_instance_count:>5}  {str(item.candidate_pool_feasible).lower()}"
        for item in report.sizing
    )
    lines.extend(
        [
            "",
            "recommendation: propose >=10 observations/cell and the measured 90-instance diversity floor;",
            "the owner must rule on the stability bar and off-plan harvesting before Phase 3 starts.",
            "The 158-candidate pool is infeasible for on-plan sizing and feasible for every off-plan alternative.",
        ]
    )
    return "\n".join(lines) + "\n"


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _sha256(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


def main() -> int:
    root = Path.cwd().resolve()
    command = (
        f"cd {root.as_posix()} && source ~/cd_vlaplan && python "
        ".claude/evidence/cgas-trace-contract-v3/owner-decision-packet/derive_pilot_scope.py"
    )
    evidence = write_signed_evidence(
        AnalysisRequest(
            root,
            root / "tmp/cgas-p0-characterized-v3",
            root / ".claude/evidence/cgas-trace-contract-v3/approved-trace-v3.json",
            root / "configs/cgas/production_p0_candidates.json",
            root / ".claude/evidence/cgas-phase3-pilot-scope",
            command,
        )
    )
    print((root / ".claude/evidence/cgas-phase3-pilot-scope/report.txt").read_text(), end="")
    return 0 if evidence.read_only else 1


if __name__ == "__main__":
    raise SystemExit(main())
