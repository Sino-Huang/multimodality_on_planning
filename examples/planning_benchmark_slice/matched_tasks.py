"""Bounded, outcome-independent final candidate preparation for the matched study."""

from __future__ import annotations

import concurrent.futures
import json
import signal
import threading
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path

from src.data_collect.adapters.base import GenerationSpec, GeneratorRejection
from src.data_collect.adapters.registry import (
    ADAPTER_TEMPLATES,
    CurriculumCommandAdapter,
    DomainSelection,
    PreparedCommand,
    TargetParameterPreset,
    build_domain_registry,
)
from src.data_collect.config import load_curriculum_config

from .bfs_generation import _normalize_authority_input
from .modality_view_preparation import write_json
from .pddl_state import PDDLStateAuthority
from .scene_assets import read_json
from .visual_episode import VisualSession

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STUDY = ROOT / "configs/experiments/matched-modalities/study.json"


class Progress:
    def __init__(self):
        self.started = time.monotonic()
        self.latest = {"stage": "starting", "completed": 0, "total": 0}
        self.stop = threading.Event()
        self.thread = None

    def __call__(self, stage, **fields):
        elapsed = time.monotonic() - self.started
        completed, total = fields.get("completed", 0), fields.get("total", 0)
        row = {
            "stage": stage,
            "completed": completed,
            "total": total,
            "elapsed_seconds": round(elapsed, 2),
            "eta_seconds": round(elapsed / completed * (total - completed), 2) if completed else None,
            **fields,
        }
        self.latest = row
        print(json.dumps(row), flush=True)

    def __enter__(self):
        def beat():
            while not self.stop.wait(20):
                row = dict(self.latest)
                row["heartbeat_elapsed_seconds"] = round(time.monotonic() - self.started, 2)
                row["heartbeat"] = True
                print(json.dumps(row), flush=True)

        self.thread = threading.Thread(target=beat, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.stop.set()
        assert self.thread is not None
        self.thread.join()


def task_semantics(domain, problem):
    """Compare canonical PDDL task content directly, without file fingerprints."""
    authority = PDDLStateAuthority.from_pddl(domain, problem)
    return json.dumps(authority.task_context(), sort_keys=True, separators=(",", ":"))


def retained_tasks(root, domains):
    """All retained source manifest tasks, including predecessors of released subsets."""
    sources = {}
    manifests = sorted((root / "data").glob("*/*manifest*.jsonl"))
    for path in manifests:
        for line in path.read_text().splitlines():
            row = json.loads(line)
            if row.get("domain_id", row.get("domain")) not in domains:
                continue
            if "domain_path" in row and "problem_path" in row:
                # Older paired manifests use paths relative to their own directory;
                # current BFS/BFWS manifests use repository-relative paths.
                base = path.parent if str(row["domain_path"]).startswith("pddl/") else root
                paths = tuple(str((base / row[k]).relative_to(root)) for k in ("domain_path", "problem_path"))
                sources[paths] = str(path.relative_to(root))
    # Paired teacher tasks retain inline normalized PDDL instead of path pairs.
    inline = sorted((root / "data").glob("*/exact-traces/pairs/*/task.json"))
    identities, evidence = set(), []
    for (domain_path, problem_path), manifest in sources.items():
        domain, problem, _ = _normalize_authority_input(
            (root / domain_path).read_text(), (root / problem_path).read_text()
        )
        identities.add(task_semantics(domain, problem))
        evidence.append({"manifest": manifest, "domain_path": domain_path, "problem_path": problem_path})
    for path in inline:
        row = read_json(path)
        domain = row.get("domain_id", row.get("domain"))
        if domain not in domains:
            continue
        identities.add(task_semantics(row["domain_pddl"], row["problem_pddl"]))
        evidence.append({"task_path": str(path.relative_to(root))})
    if not identities:
        raise ValueError("no retained tasks found for final split exclusion")
    return identities, evidence


def candidate_adapter(root, domain, arguments):
    registry = build_domain_registry(
        load_curriculum_config(root / "src/data_collect/configs/curriculum_15_domains.yaml")
    )
    base = registry[domain]
    preset = TargetParameterPreset("matched-final", tuple(arguments), {}, "fixed matched-modalities-v1 profile")
    metadata = replace(base.metadata, target_parameter_presets=(preset,))
    selection = DomainSelection(domain, base.generator_domain_id, base.generator_dir)
    builder = ADAPTER_TEMPLATES[domain].command_builder_factory(selection, metadata)
    if domain == "storage":
        # The curriculum storage builder chooses from its own variant table,
        # ignoring preset arguments. The final protocol fixes the arguments.
        def storage_builder(spec):
            problem = (spec.output_dir / "raw-problem.pddl").resolve()
            return PreparedCommand(
                command=(metadata.generator_path, *arguments, "-e", str(spec.seed), str(problem)),
                expected_problem_paths=(problem,),
            )

        builder = storage_builder

    return CurriculumCommandAdapter(
        adapter_id=domain,
        generator_domain_id=base.generator_domain_id,
        generator_dir=base.generator_dir,
        metadata=metadata,
        command_builder=builder,
    )


def enumerate_states(authority, maximum):
    states = [authority.initial_state]
    indices = {states[0].state_id: 0}
    parents: list[dict[str, int | str] | None] = [None]
    for i, state in enumerate(states):
        for action in authority.applicable_actions(state):
            target = authority.apply(state, action).target_state
            if target.state_id in indices:
                continue
            if len(states) == maximum:
                raise RuntimeError("reachable_state_ceiling")
            indices[target.state_id] = len(states)
            states.append(target)
            parents.append({"state": i, "action": f"({action.name} {' '.join(action.args)})".replace(" )", ")")})
    return {
        "task_context": authority.task_context(),
        "states": [
            {"index": i, "atoms": list(s.atoms), "fluents": list(s.fluents), "parent": parents[i]}
            for i, s in enumerate(states)
        ],
    }


def exact_reference(root, row, algorithm, study):
    """Use the existing live controller; token qualification is the later #92 stage."""
    session = VisualSession(
        root,
        row,
        algorithm,
        "exact_reference",
        17,
        root / study["output_root"],
        study["study_id"],
        input_token_counter=lambda raw: 0,
    )
    while session.next_request() is not None:
        session.submit(session.reference_output())
    result = session.result()
    if not result["invariant_valid_success"]:
        raise RuntimeError(f"exact_reference_failed:{algorithm}:{result['termination_reason']}")
    if len(session.events) > study["final"]["max_exact_decisions_per_algorithm"]:
        raise RuntimeError(f"exact_decision_ceiling:{algorithm}")
    return {"events": session.events, "result": result}


def prepare_candidate(root, study, domain, seed, exclusions):
    output = root / study["output_root"] / "preparation" / "candidates" / f"{domain}-{seed}"
    result_path = output / "candidate.json"
    if result_path.exists():
        result = read_json(result_path)
        if result["study"] != study:
            raise ValueError("candidate belongs to different study settings")
        arguments = study["final"]["candidate_profiles"][domain]["arguments"]
        if "generator_command" in result and result["generator_command"][1 : 1 + len(arguments)] != arguments:
            raise ValueError("cached candidate did not use the frozen generator arguments")
        return result
    output.mkdir(parents=True, exist_ok=True)
    row = {
        "task_id": f"matched-final/{domain}-{seed}",
        "domain": domain,
        "difficulty": "bounded-final",
        "split": "test",
        "trace_paths": {},
        "task_path": str((output / "task.json").relative_to(root)),
    }
    result = {"study": study, "domain": domain, "seed": seed, "row": row, "eligible": False}
    adapter = candidate_adapter(root, domain, study["final"]["candidate_profiles"][domain]["arguments"])
    spec = GenerationSpec(row["task_id"], output / "generator", 30, seed, {"preset_id": "matched-final"})
    candidate = adapter.normalize_outputs(adapter.generate_candidate(spec))
    if isinstance(candidate, GeneratorRejection):
        result["reason"] = candidate.rejection_reason
        write_json(result_path, result)
        return result
    result["generator_command"] = list(candidate.generator_command)
    raw_domain, raw_problem = candidate.domain_path.read_text(), candidate.problem_path.read_text()
    domain_pddl, problem_pddl, transformations = _normalize_authority_input(raw_domain, raw_problem)
    write_json(
        output / "task.json",
        {"domain_pddl": domain_pddl, "problem_pddl": problem_pddl, "authority_transformations": transformations},
    )

    def timeout(*args):
        raise TimeoutError("candidate_reference_timeout")

    previous = signal.signal(signal.SIGALRM, timeout)
    signal.setitimer(signal.ITIMER_REAL, study["final"]["reference_seconds_per_candidate"])
    try:
        authority = PDDLStateAuthority.from_pddl(domain_pddl, problem_pddl)
        if task_semantics(domain_pddl, problem_pddl) in exclusions:
            raise RuntimeError("retained_task_overlap")
        if authority.is_goal(authority.initial_state):
            raise RuntimeError("initial_goal")
        catalog = enumerate_states(authority, study["final"]["max_reachable_states"])
        row["reference_costs"] = {
            a: {
                "decisions": study["final"]["max_exact_decisions_per_algorithm"],
                "expansions": study["final"]["max_exact_expansions_per_algorithm"],
            }
            for a in study["algorithms"]
        }
        references = {a: exact_reference(root, row, a, study) for a in study["algorithms"]}
        row["reference_costs"] = {
            a: {"decisions": len(r["events"]), "expansions": r["result"]["expansion_count"]}
            for a, r in references.items()
        }
        # Repeat with the actual final episode budgets; otherwise the binding
        # might describe a different observation/call-limit contract.
        references = {a: exact_reference(root, row, a, study) for a in study["algorithms"]}
        for a, reference in references.items():
            write_json(output / f"reference-{a}.json.gz", reference)
        write_json(output / "reachable.json.gz", catalog)
        result.update(
            eligible=True,
            reason="reference_eligible_layout_pending",
            states=len(catalog["states"]),
            reachable=str((output / "reachable.json.gz").relative_to(root)),
        )
    except (RuntimeError, TimeoutError) as error:
        result["reason"] = str(error)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
    write_json(result_path, result)
    return result


def require_pool_coverage(pool, study):
    expected = [
        (d, seed) for d in study["final"]["domains"] for seed in study["final"]["candidate_profiles"][d]["seeds"]
    ]
    if (
        pool["study"] != study
        or not pool.get("candidate_preparation_complete")
        or ([(c["domain"], c["seed"]) for c in pool["candidates"]] != expected)
    ):
        raise ValueError("candidate pool is incomplete, duplicated or belongs to different settings")


def prepare_candidates(root, study, workers, progress, dry_run=False):
    jobs = [(d, seed) for d in study["final"]["domains"] for seed in study["final"]["candidate_profiles"][d]["seeds"]]
    progress("candidates:inspect", total=len(jobs))
    exclusions, sources = retained_tasks(root, set(study["final"]["domains"]))
    if dry_run:
        for domain in study["final"]["domains"]:
            adapter = candidate_adapter(root, domain, study["final"]["candidate_profiles"][domain]["arguments"])
            if not Path(adapter.metadata.generator_path).is_file():
                raise ValueError(f"missing generator for {domain}")
        progress(
            "candidates:dry_run",
            completed=len(jobs),
            total=len(jobs),
            retained_tasks=len(exclusions),
            outcome="PASS",
            model_calls=0,
            writes=0,
        )
        return None
    path = root / study["output_root"] / "preparation" / "candidates.json"
    if path.exists():
        old = read_json(path)
        require_pool_coverage(old, study)
        progress("candidates:reused", completed=len(old["candidates"]), total=len(jobs), outcome=old["outcome"])
        return old
    results = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(prepare_candidate, root, study, d, seed, exclusions) for d, seed in jobs]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
            progress(
                "candidates:progress",
                completed=len(results),
                total=len(jobs),
                domain=results[-1]["domain"],
                seed=results[-1]["seed"],
                reason=results[-1]["reason"],
            )
    results.sort(key=lambda r: (study["final"]["domains"].index(r["domain"]), r["seed"]))
    eligible = Counter(r["domain"] for r in results if r["eligible"])
    missing = [d for d in study["final"]["domains"] if not eligible[d]]
    report = {
        "study": study,
        "outcome": "VALID_STOP" if missing else "PASS",
        "candidate_preparation_complete": True,
        "final_tasks_selected": False,
        "model_input_ready": False,
        "model_calls": 0,
        "missing_domains": missing,
        "exclusion_sources": sources,
        "exclusion_count": len(exclusions),
        "eligible_counts": dict(eligible),
        "candidates": results,
    }
    write_json(path, report)
    progress(
        "candidates:complete",
        completed=len(results),
        total=len(jobs),
        outcome=report["outcome"],
        eligible_counts=dict(eligible),
        missing_domains=missing,
    )
    return report
