"""Whole-task historical exclusion inventory for the expanded unseen panel."""

from collections import Counter

from .bfs_generation import _normalize_authority_input
from .expanded_scheduler import read
from .matched_tasks import retained_tasks, task_semantics


def matched_candidate_sources(root, domains):
    """Include prior final candidates, including rejected/unselected candidates."""
    sources = []
    for path in sorted((root / "outputs/matched_modalities").glob("*/preparation/candidates/*/candidate.json")):
        candidate = read(path)
        if candidate["domain"] not in domains:
            continue
        task_path = root / candidate["row"]["task_path"]
        if task_path.exists():
            sources.append(
                {
                    "task_path": str(task_path.relative_to(root)),
                    "candidate_report": str(path.relative_to(root)),
                    "domain": candidate["domain"],
                }
            )
    return sources


def inventory(root, progress):
    panel = read(root / "configs/experiments/issue72/views-panel-32k-v2.json")
    domains = sorted({r["domain"] for r in panel["selected"]})
    progress("historical_sources", completed=0, total=1)
    identities, sources = retained_tasks(root, set(domains))
    candidates = matched_candidate_sources(root, set(domains))
    previous_count = len(identities)
    for index, source in enumerate(candidates):
        task = read(root / source["task_path"])
        domain, problem, _ = _normalize_authority_input(task["domain_pddl"], task["problem_pddl"])
        identities.add(task_semantics(domain, problem))
        progress("historical_candidates", completed=index + 1, total=len(candidates))
    # Store canonical content directly so candidate admission can compare tasks.
    # This includes goals, quantified scope, static facts and initial dynamics.
    return {
        "status": "historical_inventory_complete_panel_not_selected",
        "domains": domains,
        "planned_domain_count": 12,
        "source_domain_count": len(domains),
        "domain_scope_resolved": len(domains) == 12,
        "source_panel": "configs/experiments/issue72/views-panel-32k-v2.json",
        "source_task_count": len(sources),
        "source_distinct_semantics": previous_count,
        "matched_candidate_count": len(candidates),
        "matched_candidates_by_domain": dict(Counter(s["domain"] for s in candidates)),
        "distinct_semantics": len(identities),
        "source_evidence": sources + candidates,
        "task_semantics": sorted(identities),
        "identity_scope": (
            "canonical task context independent of problem name; object-renaming equivalence still requires audit"
        ),
        "new_tasks_generated": 0,
        "model_calls": 0,
    }
