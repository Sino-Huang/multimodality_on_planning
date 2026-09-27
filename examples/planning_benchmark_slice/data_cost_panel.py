"""#147 data-cost evaluation panel: exclusions, stratum selection and frozen membership."""

from collections import Counter, defaultdict
import hashlib
import json

from .bfs_generation import _normalize_authority_input
from .expanded_scheduler import read
from .matched_tasks import task_semantics
from .scene_assets import load_scene_task
from .task_isomorphism import context_shape, same_instance

SELECTED = "selected"


def exclusion_inventory(root, protocol, progress):
    """Canonical task contexts of every #74 corpus task and every expanded-study candidate."""
    sources = []
    for row in read(root / protocol["exclusions"]["corpus_report"])["results"]:
        domain, problem, _ = load_scene_task(root, {"task_id": row["task_id"], "trace_paths": row["source_trace_paths"]})
        sources.append(("corpus", row["task_id"], domain, problem))
    for pattern in protocol["exclusions"]["candidate_globs"]:
        for path in sorted(root.glob(pattern)):
            task = read(path)
            sources.append(("expanded_candidate", str(path.relative_to(root)), task["domain_pddl"], task["problem_pddl"]))
    semantics = set()
    for index, (_, _, domain, problem) in enumerate(sources):
        domain, problem, _ = _normalize_authority_input(domain, problem)
        semantics.add(task_semantics(domain, problem))
        progress("exclusion_inventory", completed=index + 1, total=len(sources))
    return dict(
        protocol=protocol,
        counts=dict(Counter(kind for kind, _, _, _ in sources)),
        sources=[dict(kind=k, source=s) for k, s, _, _ in sources],
        distinct_semantics=len(semantics),
        task_semantics=sorted(semantics),
        identity_scope="canonical normalized task context; object-renaming equivalence audited at selection",
        model_calls=0,
    )


def select_strata(groups, historical_contexts, candidate_context):
    """First reference-eligible, renaming-disjoint candidate per stratum in the given seed order.

    `groups` keep protocol stratum order; a stratum never borrows another stratum's seeds.
    Disjointness covers the historical contexts and every task selected so far.
    """
    index = defaultdict(list)
    for number, context in enumerate(historical_contexts):
        index[context_shape(context)].append((number, context))
    strata, chosen = [], []
    for group in groups:
        record = dict(domain=group["domain"], stratum=group["stratum"], selected=None, decisions=[])
        for candidate in group["candidates"]:
            decision = dict(seed=candidate["seed"], disposition=candidate["reason"])
            record["decisions"].append(decision)
            if not candidate["reference_eligible"]:
                continue
            context = candidate_context(candidate)
            match = next((n for n, c in index[context_shape(context)] if same_instance(context, c)), None)
            if match is not None:
                decision.update(disposition="historical_object_renaming_overlap", historical_context_index=match)
                continue
            if any(same_instance(context, c) for c in chosen):
                decision["disposition"] = "within_panel_object_renaming_overlap"
                continue
            chosen.append(context)
            record["selected"] = candidate
            decision["disposition"] = SELECTED
            break
        strata.append(record)
    missing = [
        dict(domain=g["domain"], stratum=g["stratum"], reason="frozen_seed_pool_exhausted")
        for g in strata
        if g["selected"] is None
    ]
    return strata, missing


def membership_sha256(tasks):
    """Hash sorted task ids with their frozen reference costs."""
    rows = sorted((t["row"]["task_id"], t["row"]["reference_costs"]) for t in tasks)
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
