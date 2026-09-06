"""128px scene assets with replay-derived state/decision bindings, not model inputs."""

from __future__ import annotations

import gzip
import json
import re
import shutil
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from .pddl_state import CanonicalState, GroundedAction, PDDLStateAuthority
from .planimation_render import PlanimationRenderRequest, canonical_supplied_actions, produce_planimation_render


def require_resolved_scene_coordinates(stages: list[dict[str, Any]]) -> None:
    """The backend uses False for unresolved coordinates; numeric zero is valid."""
    for stage in stages:
        for sprite in stage.get("visualSprites", []):
            if sprite.get("x") is False or sprite.get("y") is False:
                raise RuntimeError(f"profile leaves scene coordinates unresolved for {sprite.get('name')}")


def typed_puzzle_profile(context: dict[str, Any]) -> str:
    """Adapt the legacy unary-position profile to the selected typed grid tasks.

    Only rendering is changed. Validate the explicit object-coordinate convention
    against the authoritative neighbor graph; do not change PDDL or actions.
    """
    positions = sorted(
        fact[len("@type-position@(") : -1]
        for fact in context["static_initial_facts"]
        if fact.startswith("@type-position@(")
    )
    if not positions:
        raise RuntimeError("typed puzzle profile requires authoritative position type facts")
    coordinates = {}
    for name in positions:
        match = re.fullmatch(r"p_(\d+)_(\d+)", name)
        if match is None:
            raise RuntimeError("typed puzzle profile requires the declared p_row_column naming convention")
        coordinates[name] = tuple(map(int, match.groups()))
    expected = {
        f"neighbor({a},{b})"
        for a, (y, x) in coordinates.items()
        for b, (v, u) in coordinates.items()
        if abs(y - v) + abs(x - u) == 1
    }
    actual = {fact for fact in context["static_initial_facts"] if fact.startswith("neighbor(")}
    if expected != actual:
        raise RuntimeError("typed puzzle profile coordinates do not match the authoritative neighbor graph")
    parts = [
        "(define (animation typed-puzzle-scene)",
        "(:predicate at :parameters (?t ?p) :effect ((equal (?t x) (?p x)) (equal (?t y) (?p y))))",
        "(:visual tile :type default :properties ((showName TRUE) (x 0) (y 0) "
        "(width 84) (height 84) (color CYAN) (depth 2)))",
    ]
    top_row = max(row for row, _column in coordinates.values())
    for index, (name, (y, x)) in enumerate(sorted(coordinates.items())):
        parts.append(
            f"(:visual cell{index} :type predefine :objects ({name}) :properties "
            f"((showName FALSE) (x {(x-1)*100}) (y {(top_row-y)*100}) (width 90) (height 90) (color GRAY) (depth 1)))"
        )
    return "\n".join(parts) + "\n)\n"


def read_json(path: Path) -> Any:
    with gzip.open(path, "rt") if path.suffix == ".gz" else path.open() as stream:
        return json.load(stream)


def load_scene_task(root: Path, row: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    traces = {algorithm: read_json(root / path) for algorithm, path in row["trace_paths"].items()}
    if row["task_id"].startswith("astar-pair-"):
        source = read_json((root / next(iter(row["trace_paths"].values()))).parent / "task.json")
        return source["domain_pddl"], source["problem_pddl"], traces
    family, instance = row["task_id"].split("/", 1)
    manifest = (
        "data/bfs_pilot_v6/selected-manifest.jsonl"
        if family == "bfs"
        else "data/bfws_phase_v1/development-manifest.jsonl"
    )
    source = next(
        item for item in map(json.loads, (root / manifest).read_text().splitlines()) if item["instance_id"] == instance
    )
    return (root / source["domain_path"]).read_text(), (root / source["problem_path"]).read_text(), traces


def build_scene_catalog(domain: str, problem: str, traces: dict[str, Any]) -> dict[str, Any]:
    """Replay supplied transitions and exposed BFWS candidates into one first-parent tree.

    Algorithm invariant qualification remains in the existing source trace stage.
    This boundary checks physical transitions and image associations, without
    consuming historical digest fields or regenerating search traces.
    """
    authority = PDDLStateAuthority.from_pddl(domain, problem)
    states: list[CanonicalState] = [authority.initial_state]
    indices = {authority.initial_state.state_id: 0}
    parents: list[dict[str, Any] | None] = [None]
    decisions = []

    def state_from(payload):
        return authority.canonical_state(tuple(payload["atoms"]), tuple(payload.get("fluents", [])))

    def index_of(state):
        if state.state_id not in indices:
            raise ValueError("trace source has no replayed path from the initial state")
        return indices[state.state_id]

    def transition(source, operation, expected=None):
        source_index = index_of(source)
        action = GroundedAction(operation["name"], tuple(operation["args"]))
        target = authority.apply(source, action).target_state
        if expected is not None and target != state_from(expected):
            raise ValueError("recorded successor differs from authoritative PDDL progression")
        if target.state_id not in indices:
            indices[target.state_id] = len(states)
            states.append(target)
            parents.append(
                {"state": source_index, "action": f"({action.name} {' '.join(action.args)})".replace(" )", ")")}
            )
        return indices[target.state_id]

    for algorithm, trace in sorted(traces.items()):
        position = 0
        if "events" in trace:
            refs = trace["states"]
            bound_refs = {name: state_from(value).state_id for name, value in refs.items()}
            for event in trace["events"]:
                source = state_from(refs[event["expanded_state_id"]])
                index_of(source)
                for decision in event["decisions"]:
                    operation = json.loads(decision["target"])
                    if operation["source_state_id"] != event["expanded_state_id"]:
                        raise ValueError("decision source differs from expanded state")
                    target_ref = decision["runtime"]["target_state_id"]
                    target = transition(source, operation["action"], refs.get(target_ref))
                    if target_ref in bound_refs and bound_refs[target_ref] != states[target].state_id:
                        raise ValueError("target reference has conflicting replayed state semantics")
                    bound_refs[target_ref] = states[target].state_id
                    decisions.append(
                        {"algorithm": algorithm, "index": position, "state": index_of(source), "successor": target}
                    )
                    position += 1
        else:
            for record in trace["records"]:
                observation = record["observation"]
                source_payload = observation.get("expanded_state", {"atoms": observation.get("state_atoms", [])})
                source = state_from(source_payload)
                source_index = index_of(source)
                candidates = []
                for candidate in observation.get("successor_candidates", []):
                    evaluation = candidate["evaluation"]
                    expected = (
                        {"atoms": evaluation["target_atoms"], "fluents": evaluation.get("target_fluents", [])}
                        if evaluation
                        else None
                    )
                    candidate_index = transition(source, candidate["grounded_action"], expected)
                    if states[candidate_index].state_id != candidate["target_state_id"]:
                        raise ValueError("candidate state reference differs from PDDL progression")
                    candidates.append(candidate_index)
                result = record["result"].get("transition")
                target = None
                if result is not None:
                    if source != state_from(result["source_state"]):
                        raise ValueError("observation and transition source mismatch")
                    target = transition(source, record["operation"]["action"], result["target_state"])
                decisions.append(
                    {
                        "algorithm": algorithm,
                        "index": position,
                        "state": source_index,
                        "successor": target,
                        "candidate_states": candidates,
                    }
                )
                position += 1
    return {
        "task_context": authority.task_context(),
        "states": [
            {"index": i, "atoms": list(state.atoms), "fluents": list(state.fluents), "parent": parents[i]}
            for i, state in enumerate(states)
        ],
        "decisions": decisions,
    }


def catalog_paths(catalog: dict[str, Any]) -> list[tuple[list[int], tuple[str, ...]]]:
    """Leaf paths cover every first-discovered state, including non-solution branches."""
    states = catalog["states"]
    parents = {row["parent"]["state"] for row in states if row["parent"] is not None}
    paths = []
    for state in states:
        if state["index"] in parents or state["parent"] is None:
            continue
        indices, actions = [state["index"]], []
        while state["parent"] is not None:
            actions.append(state["parent"]["action"])
            state = states[state["parent"]["state"]]
            indices.append(state["index"])
        paths.append((list(reversed(indices)), tuple(reversed(actions))))
    if not paths:
        raise ValueError("scene task has no non-empty supplied path")
    return paths


def collect_task_scenes(
    *,
    root: Path,
    row: dict[str, Any],
    profile: Path,
    endpoint: str,
    output: Path,
    timeout: int,
    preflight: bool,
    progress: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    """Persist only small scene PNGs, compressed VFG evidence and exact semantic metadata."""
    domain, problem, traces = load_scene_task(root, row)
    catalog = build_scene_catalog(domain, problem, traces)
    expected = {algorithm: cost["decisions"] for algorithm, cost in row["reference_costs"].items()}
    if Counter(decision["algorithm"] for decision in catalog["decisions"]) != expected:
        raise ValueError("replayed decision coverage differs from the frozen task costs")
    paths = catalog_paths(catalog)
    if preflight:
        path, actions = paths[0]
        paths = [(path[:2], actions[:1])]
    output.mkdir(parents=True, exist_ok=False)
    (output / "domain.pddl").write_text(domain)
    (output / "problem.pddl").write_text(problem)
    source_profile = profile
    profile_transform = None
    if row["domain"] == "15puzzle":
        profile = output / "typed-puzzle-animation.pddl"
        profile.write_text(typed_puzzle_profile(catalog["task_context"]))
        profile_transform = "typed_position_grid_validated_against_neighbor_graph"
    (output / "frames").mkdir()
    rendered: set[int] = set()
    bindings = []
    for position, (indices, actions) in enumerate(paths):
        if set(indices).issubset(rendered):
            continue
        progress({"stage": "path_started", "path": position + 1, "paths": len(paths), "unique_frames": len(rendered)})
        with tempfile.TemporaryDirectory(prefix="render-path-", dir=output) as temporary:
            request = PlanimationRenderRequest(
                endpoint,
                output / "domain.pddl",
                output / "problem.pddl",
                profile,
                actions,
                Path(temporary),
                timeout,
                canvas_size=128,
            )
            result = produce_planimation_render(request)
            stages = read_json(result.trace_path)["visualStages"]
            interpreted = canonical_supplied_actions(tuple(stage["stageName"] for stage in stages[1:]))
            if stages[0]["stageName"].strip().lower() != "initial stage" or interpreted != canonical_supplied_actions(
                actions
            ):
                raise ValueError("backend interpretation differs from supplied actions")
            if len(result.frame_paths) != len(indices):
                raise ValueError("backend stage count differs from replayed states")
            vfg_path = output / f"path-{position:06d}.vfg.json.gz"
            with result.trace_path.open("rb") as source, gzip.open(vfg_path, "wb") as destination:
                shutil.copyfileobj(source, destination)
            require_resolved_scene_coordinates(stages)
            for state_index, frame in zip(indices, result.frame_paths, strict=True):
                if state_index not in rendered:
                    frame.replace(output / "frames" / f"state-{state_index:06d}.png")
                    rendered.add(state_index)
            bindings.append(
                {
                    "supplied_actions": list(actions),
                    "state_indices": indices,
                    "vfg": str(vfg_path.relative_to(root)),
                    "endpoint": result.used_endpoint,
                    "semantic_validation": "supplied_actions_and_PDDL_state_sequence_match",
                }
            )
        progress({"stage": "path_complete", "path": position + 1, "paths": len(paths), "unique_frames": len(rendered)})
    for state in catalog["states"]:
        state["scene_path"] = (
            str((output / "frames" / f"state-{state['index']:06d}.png").relative_to(root))
            if state["index"] in rendered
            else None
        )
    catalog.update(
        task_id=row["task_id"],
        source_profile=str(source_profile.relative_to(root)),
        used_profile=str(profile.relative_to(root)),
        profile_transform=profile_transform,
        split=row["split"],
        reference_costs=row["reference_costs"],
        source_trace_paths=row["trace_paths"],
        path_bindings=bindings,
        stored_scene_size=[128, 128],
        canonical_goal=catalog["task_context"]["canonical_goal"],
        model_input_ready=False,
        partial_goal_images_complete=False,
    )
    with gzip.open(output / "catalog.json.gz", "wt") as stream:
        json.dump(catalog, stream)
    return {
        "task_id": row["task_id"],
        "outcome": "PASS",
        "scene_frames": len(rendered),
        "catalog_states": len(catalog["states"]),
        "catalog": str((output / "catalog.json.gz").relative_to(root)),
        "complete_state_coverage": len(rendered) == len(catalog["states"]),
        "model_input_ready": False,
        "partial_goal_images_complete": False,
    }
