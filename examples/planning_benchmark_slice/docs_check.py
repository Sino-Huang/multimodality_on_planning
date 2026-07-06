from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
SUMMARY_DIR = REPO_ROOT / "doc" / "detailed_implementation_summary"
EXECUTION_PLAN = REPO_ROOT / "doc" / "high_level_plans" / "research_execution_plan.md"
EVIDENCE_DIR = REPO_ROOT / ".sisyphus" / "evidence"


@dataclass(frozen=True)
class TextRequirement:
    path: Path
    phrase: str


@dataclass(frozen=True)
class PhaseRequirement:
    phase: int
    label: str
    documents: tuple[Path, ...]
    evidence: tuple[Path, ...]
    phrases: tuple[TextRequirement, ...]


def _summary(name: str) -> Path:
    return SUMMARY_DIR / name


def _evidence(name: str) -> Path:
    return EVIDENCE_DIR / name


PHASE_REQUIREMENTS: dict[int, PhaseRequirement] = {
    1: PhaseRequirement(
        phase=1,
        label="scope_lock_symbolic_core_zero_shot",
        documents=(
            _summary("phase1_scope_lock_and_diagnostic_summary.md"),
            EXECUTION_PLAN,
        ),
        evidence=(
            _evidence("phase1-3-task-1-scope-lock.json"),
            _evidence("phase1-3-task-1-scope-lock-error.txt"),
            _evidence("phase1-3-task-2-valid-instance.json"),
            _evidence("phase1-3-task-2-empty-goal-error.json"),
            _evidence("phase1-3-task-3-zero-shot-build.json"),
            _evidence("phase1-3-task-3-illegal-action.json"),
        ),
        phrases=(
            TextRequirement(_summary("phase1_scope_lock_and_diagnostic_summary.md"), "Blocksworld-only P0"),
            TextRequirement(_summary("phase1_scope_lock_and_diagnostic_summary.md"), "deterministic symbolic world model v0"),
            TextRequirement(_summary("phase1_scope_lock_and_diagnostic_summary.md"), "Planimation is offline rendering and visualization only"),
            TextRequirement(_summary("phase1_scope_lock_and_diagnostic_summary.md"), "without real VLM, GPU, API, or external-service execution"),
            TextRequirement(EXECUTION_PLAN, "Phase 1 complete for Blocksworld-only P0"),
        ),
    ),
    2: PhaseRequirement(
        phase=2,
        label="direct_python_benchmark_loop",
        documents=(
            _summary("phase2_benchmark_loop_summary.md"),
            EXECUTION_PLAN,
        ),
        evidence=(
            _evidence("phase1-3-task-4-oracle-loop.json"),
            _evidence("phase1-3-task-4-invalid-action.json"),
        ),
        phrases=(
            TextRequirement(_summary("phase2_benchmark_loop_summary.md"), "direct Python benchmark loop"),
            TextRequirement(_summary("phase2_benchmark_loop_summary.md"), "no WebSocket"),
            TextRequirement(_summary("phase2_benchmark_loop_summary.md"), "Phase 4 model training remain outside this phase"),
            TextRequirement(EXECUTION_PLAN, "Phase 2 complete for Blocksworld-only P0"),
        ),
    ),
    3: PhaseRequirement(
        phase=3,
        label="expert_trajectories_modalities_registry",
        documents=(
            _summary("phase3_expert_trajectories_summary.md"),
            EXECUTION_PLAN,
        ),
        evidence=(
            _evidence("phase1-3-task-5-schema-valid.json"),
            _evidence("phase1-3-task-5-schema-error.json"),
            _evidence("phase1-3-task-6-bfs-iw.json"),
            _evidence("phase1-3-task-6-determinism.txt"),
            _evidence("phase1-3-task-7-ff.json"),
            _evidence("phase1-3-task-7-validator.json"),
            _evidence("phase1-3-task-7-tiebreak.txt"),
            _evidence("phase1-3-task-8-graphplan.json"),
            _evidence("phase1-3-task-8-validator.json"),
            _evidence("phase1-3-task-8-mutex.txt"),
            _evidence("phase1-3-task-9-serialize.json"),
            _evidence("phase1-3-task-9-vision-leakage.txt"),
            _evidence("phase1-3-task-10-registry.txt"),
            _evidence("phase1-3-task-10-registry-collision.txt"),
        ),
        phrases=(
            TextRequirement(_summary("phase3_expert_trajectories_summary.md"), "Blocksworld-only P0"),
            TextRequirement(_summary("phase3_expert_trajectories_summary.md"), "bfs"),
            TextRequirement(_summary("phase3_expert_trajectories_summary.md"), "fast_forward"),
            TextRequirement(_summary("phase3_expert_trajectories_summary.md"), "iterated_width"),
            TextRequirement(_summary("phase3_expert_trajectories_summary.md"), "graphplan"),
            TextRequirement(_summary("phase3_expert_trajectories_summary.md"), "deterministic_p0_hmax_relaxed_reachability"),
            TextRequirement(_summary("phase3_expert_trajectories_summary.md"), "deterministic_p0_action_mutex_only_graphplan"),
            TextRequirement(_summary("phase3_expert_trajectories_summary.md"), "model_facing"),
            TextRequirement(_summary("phase3_expert_trajectories_summary.md"), "supervised_target"),
            TextRequirement(_summary("phase3_expert_trajectories_summary.md"), "evaluation_metadata"),
            TextRequirement(_summary("phase3_expert_trajectories_summary.md"), "planning_blocksworld_dev_smoke"),
            TextRequirement(_summary("phase3_expert_trajectories_summary.md"), "outputs/planning_artifacts/**"),
            TextRequirement(_summary("phase3_expert_trajectories_summary.md"), "not itself proof of Phase 3 expert demonstrations"),
            TextRequirement(EXECUTION_PLAN, "Phase 3 complete for Blocksworld-only P0"),
        ),
    ),
}

NO_PHASE4_REQUIRED_PHRASES: tuple[TextRequirement, ...] = (
    TextRequirement(EXECUTION_PLAN, "Phase 4 remains not complete"),
    TextRequirement(EXECUTION_PLAN, "No training, planner model, SFT, real VLM, GPU, API, or external-service result is claimed"),
    TextRequirement(_summary("phase3_expert_trajectories_summary.md"), "No Phase 4 training, model implementation, or SFT run is complete yet"),
)

FORBIDDEN_NO_PHASE4_PHRASES = (
    "Phase 4 complete",
    "Phase 4 is complete",
    "Phase 4 training complete",
    "SFT run completed",
    "real VLM execution complete",
    "GPU run complete",
)


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _contains(text: str, phrase: str) -> bool:
    return _normalize(phrase) in _normalize(text)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _check_text_requirement(requirement: TextRequirement) -> dict[str, Any]:
    if not requirement.path.exists():
        return {
            "path": _rel(requirement.path),
            "phrase": requirement.phrase,
            "present": False,
            "reason": "missing_document",
        }
    text = _read_text(requirement.path)
    present = _contains(text, requirement.phrase)
    return {
        "path": _rel(requirement.path),
        "phrase": requirement.phrase,
        "present": present,
        "reason": None if present else "missing_phrase",
    }


def validate_phase(phase: int) -> dict[str, Any]:
    requirement = PHASE_REQUIREMENTS[phase]
    document_results = [
        {"path": _rel(path), "exists": path.exists()} for path in requirement.documents
    ]
    evidence_results = [
        {"path": _rel(path), "exists": path.exists()} for path in requirement.evidence
    ]
    phrase_results = [_check_text_requirement(phrase) for phrase in requirement.phrases]
    missing_documents = [item["path"] for item in document_results if not item["exists"]]
    missing_evidence = [item["path"] for item in evidence_results if not item["exists"]]
    missing_phrases = [
        {"path": item["path"], "phrase": item["phrase"]}
        for item in phrase_results
        if not item["present"]
    ]
    valid = not missing_documents and not missing_evidence and not missing_phrases
    return {
        "documents": document_results,
        "evidence": evidence_results,
        "label": requirement.label,
        "missing_documents": missing_documents,
        "missing_evidence": missing_evidence,
        "missing_phrases": missing_phrases,
        "phase": phase,
        "phrase_results": phrase_results,
        "valid": valid,
    }


def validate_no_phase4_claims() -> dict[str, Any]:
    required_results = [_check_text_requirement(requirement) for requirement in NO_PHASE4_REQUIRED_PHRASES]
    required_missing = [
        {"path": item["path"], "phrase": item["phrase"]}
        for item in required_results
        if not item["present"]
    ]
    checked_paths = sorted({requirement.path for requirement in NO_PHASE4_REQUIRED_PHRASES} | {EXECUTION_PLAN})
    forbidden_hits: list[dict[str, str]] = []
    for path in checked_paths:
        if not path.exists():
            continue
        text = _read_text(path)
        for phrase in FORBIDDEN_NO_PHASE4_PHRASES:
            if _contains(text, phrase):
                forbidden_hits.append({"path": _rel(path), "phrase": phrase})
    valid = not required_missing and not forbidden_hits
    return {
        "forbidden_hits": forbidden_hits,
        "required_missing": required_missing,
        "required_results": required_results,
        "valid": valid,
    }


def validate_docs(*, phases: Sequence[int], no_phase4_claims: bool) -> dict[str, Any]:
    if not phases and not no_phase4_claims:
        phases = tuple(sorted(PHASE_REQUIREMENTS))
    phase_results = {str(phase): validate_phase(phase) for phase in phases}
    no_phase4 = validate_no_phase4_claims() if no_phase4_claims else None
    valid = all(result["valid"] for result in phase_results.values())
    if no_phase4 is not None:
        valid = valid and no_phase4["valid"]
    return {
        "checked_phases": list(phases),
        "no_phase4_claims": no_phase4,
        "phase_results": phase_results,
        "schema_version": "planning_docs_check_v1",
        "valid": valid,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate Phase 1-3 planning closeout documentation.")
    parser.add_argument("--phase", nargs="+", type=int, choices=sorted(PHASE_REQUIREMENTS), default=[])
    parser.add_argument("--no-phase4-claims", action="store_true")
    parser.add_argument("--json", action="store_true", help="Emit JSON. This is also the default output.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    phases = tuple(args.phase)
    if not phases and not args.no_phase4_claims:
        phases = tuple(sorted(PHASE_REQUIREMENTS))
    payload = validate_docs(phases=phases, no_phase4_claims=args.no_phase4_claims)
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not payload["valid"]:
        print("documentation closeout check failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "PHASE_REQUIREMENTS",
    "build_parser",
    "main",
    "validate_docs",
    "validate_no_phase4_claims",
    "validate_phase",
]
