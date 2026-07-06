from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence


REQUIRED_DECISIONS: dict[str, tuple[str, ...]] = {
    "blocksworld_p0_scope_decision": ("blocksworld", "future-compatible", "Phase 1-3 acceptance scope"),
    "algorithm_matrix_decision": ("bfs", "fast_forward", "iterated_width", "graphplan"),
    "modality_matrix_decision": ("vision", "language", "vision_language", "vision_language_tool"),
    "planimation_role_decision": ("Planimation", "offline rendering", "not environment authority"),
    "frozen_world_model_decision": ("frozen world model v0", "deterministic symbolic representation", "No learned encoder"),
    "artifact_policy_decision": ("artifact", "Raw PDDL", "expert demonstrations"),
    "zero_shot_gate_decision": ("zero shot", "go or no go", "parseable JSON", "action is legal"),
}


def _normalize(text: str) -> str:
    return " ".join(text.lower().replace("/", " ").split())


def validate_scope_lock(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"scope lock artifact is missing: {path}")

    text = path.read_text(encoding="utf-8")
    normalized_text = _normalize(text)
    missing_decisions: list[str] = []
    missing_terms: dict[str, list[str]] = {}

    for decision_id, required_terms in REQUIRED_DECISIONS.items():
        decision_missing_terms = [term for term in required_terms if _normalize(term) not in normalized_text]
        if _normalize(decision_id) not in normalized_text:
            decision_missing_terms.insert(0, decision_id)
        if decision_missing_terms:
            missing_decisions.append(decision_id)
            missing_terms[decision_id] = decision_missing_terms

    required_decisions_present = not missing_decisions
    return {
        "path": str(path),
        "valid": required_decisions_present,
        "required_decisions_present": required_decisions_present,
        "missing_decisions": missing_decisions,
        "missing_terms": missing_terms,
        "checked_decisions": sorted(REQUIRED_DECISIONS),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate the Phase 1 planning scope lock artifact.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Validate required scope lock decisions.")
    validate_parser.add_argument("--path", type=Path, required=True, help="Path to the markdown scope lock artifact.")
    validate_parser.add_argument("--json", action="store_true", help="Emit JSON. This is also the default output.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "validate":
            payload = validate_scope_lock(args.path)
        else:
            parser.error(f"unsupported command: {args.command}")
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1

    print(json.dumps(payload, indent=2, sort_keys=True))
    if not payload["valid"]:
        print(f"missing required decisions: {', '.join(payload['missing_decisions'])}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["REQUIRED_DECISIONS", "build_parser", "main", "validate_scope_lock"]
