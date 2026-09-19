"""Frozen-profile generation and reference-only screening of new panel candidates."""

import random
import re
import signal
import math

from src.data_collect.adapters.base import GenerationSpec, GeneratorRejection
from src.data_collect.adapters.registry import CurriculumCommandAdapter, PreparedCommand

from .bfs_generation import _normalize_authority_input
from .expanded_scheduler import read, write
from .matched_tasks import candidate_adapter, exact_reference, task_semantics
from .pddl_state import PDDLStateAuthority
from .source_goal import source_task
from .strips_relaxation import estimated_grounded_operator_count, _parameter_objects, _positive_atoms
from .modality_view_preparation import write_json


def replace_initial(problem, facts):
    match = re.search(r"\(:init\b", problem, flags=re.I)
    if match is None:
        raise ValueError("missing source initial state")
    depth = 0
    for end in range(match.start(), len(problem)):
        depth += (problem[end] == "(") - (problem[end] == ")")
        if depth == 0:
            return problem[: match.start()] + "(:init\n " + "\n ".join(facts) + ")" + problem[end + 1 :]
    raise ValueError("unbalanced source initial state")


def pddl_facts(atoms):
    result = []
    for atom in atoms:
        if atom.startswith("@"):
            continue  # Compiler type facts are regenerated from source declarations.
        name, _, arguments = atom.partition("(")
        result.append("(" + name + (" " + arguments.rstrip(")").replace(",", " ") if arguments else "") + ")")
    return result


def typed_grounding_count(authority):
    """Count exactly the assignments instantiated by the current additive heuristic."""
    objects = tuple(sorted({o for _, values in authority.objects_by_type for o in values}))
    return sum(
        math.prod(
            len(
                _parameter_objects(
                    p.name,
                    _positive_atoms(a.precondition, "action precondition"),
                    objects,
                    authority.static_initial_facts,
                )
            )
            for p in a.parameters
        )
        for a in authority._domain.actions
    )


def walk_initial(domain, problem, profile, seed):
    """Return a new source initial state plus its replayable generating path."""
    authority = PDDLStateAuthority.from_pddl(domain, problem)
    source = source_task(domain, problem)
    start = authority.initial_state
    if profile["walk_origin"] == "goal":
        if profile["domain"] != "15puzzle":
            raise ValueError("goal-start constructor is specific to sliding puzzles")
        atoms = list(authority.goal_atoms)
        occupied = {a.rstrip(")").split(",")[-1] for a in atoms}
        positions = source["objects_by_type"]["position"]
        empty = set(positions) - occupied
        if len(empty) != 1:
            raise ValueError("puzzle source goal must leave one empty position")
        atoms.append(f"empty({next(iter(empty))})")
        problem = replace_initial(problem, pddl_facts([*authority.static_initial_facts, *atoms]))
        authority = PDDLStateAuthority.from_pddl(domain, problem)
        start = authority.initial_state
        if not authority.is_goal(start):
            raise ValueError("puzzle goal-state construction failed")
    origin_problem = problem
    rng = random.Random(seed)
    state, previous = start, None
    actions = []
    for _ in range(profile["walk_steps"]):
        choices = [(a, authority.apply(state, a).target_state) for a in authority.applicable_actions(state)]
        forward = [(a, s) for a, s in choices if s.state_id != previous]
        choices = forward or choices
        if not choices:
            raise ValueError("initial-state walk has no applicable action")
        action, target = rng.choice(choices)
        previous, state = state.state_id, target
        actions.append(f"({action.name} {' '.join(action.args)})".replace(" )", ")"))
    if state.fluents:
        raise ValueError("declared walk domains must have no numeric fluents")
    result = replace_initial(problem, pddl_facts([*authority.static_initial_facts, *state.atoms]))
    if source_task(domain, result) != source:
        raise ValueError("new initial state changed source goal/object context")
    return result, {
        "origin_problem_pddl": origin_problem,
        "actions": actions,
        "final_atoms": list(state.atoms),
        "final_fluents": list(state.fluents),
    }


def generate(root, profile, seed, output):
    base = candidate_adapter(root, profile["domain"], profile["arguments"])
    if profile["domain"] in ("gripper", "towers_of_hanoi"):
        # Bypass the historical object-renaming/sweep builder. The profile fixes
        # size; the declared legal walk supplies a genuinely different start.
        base = CurriculumCommandAdapter(
            adapter_id=base.adapter_id,
            generator_domain_id=base.generator_domain_id,
            generator_dir=base.generator_dir,
            metadata=base.metadata,
            command_builder=lambda spec: PreparedCommand(command=(base.metadata.generator_path, *profile["arguments"])),
        )
    raw = base.generate_candidate(
        GenerationSpec(f"expanded/{profile['domain']}-{seed}", output, 30, seed, {"preset_id": "matched-final"})
    )
    candidate = base.normalize_outputs(raw)
    if isinstance(candidate, GeneratorRejection):
        raise RuntimeError(candidate.rejection_reason)
    domain, problem, transformations = _normalize_authority_input(
        candidate.domain_path.read_text(), candidate.problem_path.read_text()
    )
    walk = None
    if profile["walk_steps"]:
        problem, walk = walk_initial(domain, problem, profile, seed)
    return dict(
        domain_pddl=domain,
        problem_pddl=problem,
        authority_transformations=transformations,
        generator_command=list(candidate.generator_command),
        initial_walk=walk,
    )


def screen(root, protocol, profile, seed, exclusions):
    output = root / protocol["output_root"] / "candidates" / f"{profile['domain']}-{profile['stratum']}-{seed}"
    saved = output / "candidate.json"
    if saved.exists():
        prior = read(saved)
        if prior["protocol"] != protocol or prior["profile"] != profile:
            raise ValueError("retained candidate differs from frozen profile")
        return prior
    output.mkdir(parents=True, exist_ok=True)
    report = dict(protocol=protocol, profile=profile, seed=seed, reference_eligible=False, final_selected=False)
    limits = protocol["reference"]

    def timeout(*args):
        raise TimeoutError("reference_screen_timeout")

    previous_handler = signal.signal(signal.SIGALRM, timeout)
    signal.setitimer(signal.ITIMER_REAL, limits["seconds_per_candidate"])
    try:
        task_path = output / "task.json"
        if protocol.get("reuse_candidate_root"):
            task_path = root / protocol["reuse_candidate_root"] / "candidates" / output.name / "task.json"
            task = read(task_path)
        else:
            task = generate(root, profile, seed, output / "generator")
            write(task_path, task)
        authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])
        report["task_path"] = str(task_path.relative_to(root))
        report["cartesian_grounding_estimate"] = estimated_grounded_operator_count(authority)
        report["grounding_estimate"] = (
            typed_grounding_count(authority)
            if limits.get("grounding_metric") == "current_additive_type_pruned_assignments"
            else report["cartesian_grounding_estimate"]
        )
        if report["grounding_estimate"] > limits["grounding_estimate_ceiling"]:
            raise RuntimeError("grounding_estimate_ceiling")
        if task_semantics(task["domain_pddl"], task["problem_pddl"]) in exclusions:
            raise RuntimeError("historical_task_overlap")
        if authority.is_goal(authority.initial_state):
            raise RuntimeError("initial_goal")
        row = dict(
            task_id=f"expanded-final/{profile['domain']}-{profile['stratum']}-{seed}",
            domain=profile["domain"],
            difficulty=profile["stratum"],
            split="test",
            task_path=report["task_path"],
            trace_paths={},
            reference_costs={
                a: dict(
                    decisions=limits["max_decisions_per_algorithm"], expansions=limits["max_expansions_per_algorithm"]
                )
                for a in limits["algorithms"]
            },
        )
        study = dict(
            output_root=protocol["output_root"],
            study_id=protocol["study_id"],
            final={"max_exact_decisions_per_algorithm": limits["max_decisions_per_algorithm"]},
        )
        refs = {a: exact_reference(root, row, a, study) for a in limits["algorithms"]}
        row["reference_costs"] = {
            a: dict(decisions=len(r["events"]), expansions=r["result"]["expansion_count"]) for a, r in refs.items()
        }
        if sum(c["decisions"] for c in row["reference_costs"].values()) > limits["max_summed_decisions"]:
            raise RuntimeError("summed_reference_decision_ceiling")
        # Bind references to the resulting per-instance budgets, as in v5.
        for algorithm in limits["algorithms"]:
            write_json(output / f"reference-{algorithm}.json.gz", exact_reference(root, row, algorithm, study))
        report.update(reference_eligible=True, reason="reference_eligible_alias_and_input_audits_pending", row=row)
    except (RuntimeError, ValueError, TimeoutError) as error:
        report["reason"] = str(error)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
    write(saved, report)
    return report
