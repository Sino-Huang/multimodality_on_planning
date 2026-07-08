from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import DEFAULT_PLANNERS, RESOURCE_LIMITS, generate_supervised_data, print_payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, default=Path("data/curriculum_pddl"))
    parser.add_argument("--output-root", type=Path, default=Path("data/phase3_supervised_planning"))
    parser.add_argument("--planners", nargs="+", default=list(DEFAULT_PLANNERS), choices=list(DEFAULT_PLANNERS))
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--planner-attempt-timeout-seconds", type=int, default=RESOURCE_LIMITS["planner_attempt_timeout_seconds"])
    parser.add_argument("--domain-timeout-seconds", type=int, default=RESOURCE_LIMITS["domain_timeout_seconds"])
    parser.add_argument("--gbfs-max-applicable-actions", type=int, default=RESOURCE_LIMITS["gbfs_max_applicable_actions"])
    parser.add_argument("--gbfs-max-expansions", type=int, default=RESOURCE_LIMITS["gbfs_max_expansions"])
    parser.add_argument("--gbfs-max-depth", type=int, default=RESOURCE_LIMITS["gbfs_max_depth"])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be at least 1")
    if args.planner_attempt_timeout_seconds < 0:
        parser.error("--planner-attempt-timeout-seconds must be non-negative")
    if args.domain_timeout_seconds < 0:
        parser.error("--domain-timeout-seconds must be non-negative")
    limits = {
        "planner_attempt_timeout_seconds": args.planner_attempt_timeout_seconds,
        "domain_timeout_seconds": args.domain_timeout_seconds,
        "gbfs_max_applicable_actions": args.gbfs_max_applicable_actions,
        "gbfs_max_expansions": args.gbfs_max_expansions,
        "gbfs_max_depth": args.gbfs_max_depth,
    }
    payload = generate_supervised_data(args.input_root, args.output_root, planners=tuple(args.planners), limits=limits, jobs=args.jobs)
    print_payload(payload["summary"], as_json=args.json)


if __name__ == "__main__":
    main()
