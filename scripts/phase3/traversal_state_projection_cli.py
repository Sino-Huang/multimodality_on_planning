from __future__ import annotations

import argparse
import json
from pathlib import Path

from .trace_contracts import FrozenSourceIdentity
from .traversal_states import JSONValue, TraversalProjectionInput, project_traversal_state_candidates


def main() -> int:
    parser = argparse.ArgumentParser(description="Project concrete Phase 3 traversal-state fixtures.")
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--domain", type=Path, required=True)
    parser.add_argument("--problem", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    arguments = parser.parse_args()
    cases = json.loads(arguments.fixtures.read_text(encoding="utf-8"))
    report: list[dict[str, JSONValue]] = []
    for case in cases:
        source_row = case["source_row"]
        identity = FrozenSourceIdentity(
            "fixture-root",
            "train.jsonl",
            0,
            f"hash-{source_row['example_id']}",
            source_row["example_id"],
            source_row["planner"],
        )
        projection = project_traversal_state_candidates(
            TraversalProjectionInput(identity, source_row, arguments.domain, arguments.problem)
        )
        report.append(
            {
                "name": case["name"],
                "candidate_count": len(projection.candidates),
                "candidate_ids": [candidate.event_id for candidate in projection.candidates],
                "event_kinds": [candidate.event_kind for candidate in projection.candidates],
                "extraction_event_ids": [candidate.extraction_event_id for candidate in projection.candidates],
                "exclusions": [item.reason for item in projection.exclusions],
                "state_sources": [candidate.state_source for candidate in projection.candidates],
            }
        )
    arguments.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
