"""Phase 2 orchestration and evidence I/O for Goal 11 qualification."""

from __future__ import annotations

import copy
import gzip
import hashlib
import json
import re
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .bfs_generation import _normalize_authority_input
from .expanded_candidates import generate as generate_candidate
from .expanded_candidates import typed_grounding_count
from .expanded_generalization import (
    audit_perturbation,
    derive_perturbed_task,
    derive_shifted_initial,
    eligibility_screen,
    load_protocol,
    materialize_view_manifest,
    semantically_disjoint,
    view_information,
)
from .expanded_views import reference_catalog, render_unlabelled_vfg
from .matched_tasks import exact_reference, retained_tasks, task_semantics
from .modality_pages import compose_page, fact_blocks, paginate
from .pddl_state import PDDLStateAuthority
from .scene_assets import catalog_paths, collect_task_scenes
from .scene_only_views import SceneOnlyViews, materialize_task
from .source_goal import source_task
from .task_isomorphism import same_instance
from .visual_episode import VisualSession

FAMILIES = ("scale-up", "shifted-init", "object-renaming", "render-restyle", "name-compression")
STRUCTURAL_FAMILIES = ("scale-up", "shifted-init")
PERTURBATION_FAMILIES = ("object-renaming", "render-restyle", "name-compression")
PROBE_PERSIST_FIELDS = frozenset(
    (
        "call_wall_seconds",
        "input_tokens",
        "output_tokens",
        "algorithm",
        "modality",
        "family",
        "batch_size",
    )
)
_PLANIMATION_RENDER_LOCK = threading.Lock()
_TRANSIENT_PLANIMATION_ERRORS = (
    "connection refused",
    "failed to establish a new connection",
    "connection reset",
    "connection aborted",
    "connect timeout",
    "read timed out",
    "temporarily unavailable",
)
_MAPPED_SCENE_TRANSFORM = "frozen_object_bijection_over_backend_qualified_source_vfg"


def read(path: Path) -> Any:
    with gzip.open(path, "rt") if path.suffix == ".gz" else path.open(encoding="utf-8") as stream:
        return json.load(stream)


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".gz":
        with gzip.open(path, "wt") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
        return
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def output_root(root: Path, protocol: Mapping[str, Any]) -> Path:
    return root / protocol["output_root"]


def variant_id(domain: str, family: str, seed: int) -> str:
    if family not in FAMILIES or not domain or not isinstance(seed, int):
        raise ValueError("invalid generalization variant identity")
    return f"{domain}-{family}-{seed}"


def variant_rows(protocol: Mapping[str, Any]) -> list[dict[str, Any]]:
    result = []
    for source in protocol["source_problems"]:
        for family in STRUCTURAL_FAMILIES:
            result.append(
                {
                    "variant_id": variant_id(source["domain"], family, source["structural_variants"][family]["seed"]),
                    "family": family,
                    "source": source,
                    "profile": copy.deepcopy(source["structural_variants"][family]),
                }
            )
        for family in PERTURBATION_FAMILIES:
            seed = source["perturbation_seeds"][family]
            result.append(
                {
                    "variant_id": variant_id(source["domain"], family, seed),
                    "family": family,
                    "source": source,
                    "profile": {"seed": seed},
                }
            )
    return result


def _panel_views(root: Path, protocol: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    panel = read(root / protocol["panel"])
    report = read(root / panel["view_report"])
    rows = {task["row"]["task_id"]: task for task in report["tasks"]}
    if set(rows) != {task["row"]["task_id"] for task in panel["tasks"]}:
        raise ValueError("expanded generalization source views differ from the frozen panel")
    return rows


def _source_asset(root: Path, source: Mapping[str, Any], panel_views: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    task = read(root / source["task_path"])
    prepared = panel_views[source["task_id"]]
    manifest = read(root / prepared["native_views"]["source_manifest"])
    catalog = read(root / manifest["scene_catalog"])
    task.update(
        asset_root=str(root),
        row=copy.deepcopy(prepared["row"]),
        native_views=copy.deepcopy(prepared["native_views"]),
        view_manifest=manifest,
        text_pages=_actual_text_inventory(manifest, catalog),
    )
    return task


def _actual_text_inventory(manifest: Mapping[str, Any], catalog: Mapping[str, Any]) -> dict[str, Any]:
    state = catalog["states"][0]
    semantic = fact_blocks(catalog["task_context"], state, manifest["source"])
    object_types = {}
    for block in semantic["task-context"]:
        if block["id"].startswith("objects:"):
            for item in block["text"].split(";"):
                name, separator, kind = item.strip().partition(" : ")
                if separator:
                    object_types[name] = kind
    atoms = sorted(
        {
            *catalog["task_context"]["static_initial_facts"],
            *state["atoms"],
        }
    )
    identities = set(object_types)
    for atom in atoms:
        term = atom.split("=", 1)[0]
        _name, separator, arguments = term.partition("(")
        if separator:
            identities.update(argument.strip() for argument in arguments.rstrip(")").split(","))
    return {
        "state": {
            "object_identities": sorted(identities),
            "object_types": object_types,
            "atoms": atoms,
            "fluents": list(state["fluents"]),
        }
    }


def validate_stage(root: Path) -> dict[str, Any]:
    protocol = load_protocol(root)
    return {
        "schema_version": "expanded_generalization_validation_v1",
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "variants": len(variant_rows(protocol)),
        "writes": 0,
    }


def generate_stage(
    root: Path,
    *,
    candidate_generator: Callable[[Path, Mapping[str, Any], int, Path], dict[str, Any]] = generate_candidate,
) -> dict[str, Any]:
    protocol = load_protocol(root)
    panel_views = _panel_views(root, protocol)
    records = []
    for variant in variant_rows(protocol):
        source = variant["source"]
        family = variant["family"]
        folder = output_root(root, protocol) / "candidates" / family / variant["variant_id"]
        task_path, map_path = folder / "task.json", folder / "semantic_map.json"
        if task_path.exists() and map_path.exists():
            records.append({**variant, "task_path": str(task_path.relative_to(root)), "retained": True})
            continue
        folder.mkdir(parents=True, exist_ok=False)
        source_asset = _source_asset(root, source, panel_views)
        if family == "scale-up":
            profile = {
                "domain": source["domain"],
                "stratum": family,
                "arguments": variant["profile"]["arguments"],
                "walk_steps": variant["profile"]["walk_steps"],
                "walk_origin": variant["profile"]["walk_origin"],
            }
            task = candidate_generator(root, profile, variant["profile"]["seed"], folder / "generator")
            semantic_map = {"family": family, "seed": variant["profile"]["seed"], "source_task_id": source["task_id"]}
        elif family == "shifted-init":
            profile = {
                "domain": source["domain"],
                "stratum": family,
                "arguments": variant["profile"]["arguments"],
                "walk_steps": 0,
                "walk_origin": variant["profile"]["walk_origin"],
            }
            origin = candidate_generator(root, profile, variant["profile"]["seed"], folder / "generator")
            task, walk_audit = derive_shifted_initial(
                origin,
                source_asset,
                {"domain": source["domain"], **variant["profile"]},
            )
            semantic_map = {
                "family": family,
                "seed": variant["profile"]["seed"],
                "source_task_id": source["task_id"],
                "walk_audit": walk_audit,
            }
        else:
            task, semantic_map = derive_perturbed_task(source_asset, family, variant["profile"]["seed"])
            semantic_map["source_task_id"] = source["task_id"]
        task["variant_id"] = variant["variant_id"]
        task["source_task_id"] = source["task_id"]
        write(task_path, task)
        write(map_path, semantic_map)
        records.append({**variant, "task_path": str(task_path.relative_to(root)), "retained": False})
    report = {"schema_version": "expanded_generalization_generation_v1", "outcome": "PASS", "variants": records}
    write(output_root(root, protocol) / "generation.json", report)
    return report


def _reference_row(root: Path, protocol: Mapping[str, Any], variant: Mapping[str, Any]) -> dict[str, Any]:
    folder = root / variant["task_path"].rsplit("/task.json", 1)[0]
    return {
        "task_id": f"expanded-generalization/{variant['variant_id']}",
        "domain": variant["source"]["domain"],
        "difficulty": variant["source"]["stratum_origin"],
        "split": "test",
        "task_path": str((folder / "task.json").relative_to(root)),
        "trace_paths": {},
        "reference_costs": {
            algorithm: {
                "decisions": protocol["eligibility"]["max_decisions_per_algorithm"],
                "expansions": protocol["eligibility"]["max_expansions_per_algorithm"],
            }
            for algorithm in protocol["algorithms"]
        },
    }


def _rewrite_semantic_payload(value: Any, mapping: Mapping[str, str]) -> Any:
    if isinstance(value, str):
        if not mapping:
            return value
        names = sorted(mapping, key=lambda name: (-len(name), name))
        pattern = re.compile(
            r"(?<![A-Za-z0-9_-])(?:" + "|".join(re.escape(name) for name in names) + r")(?![A-Za-z0-9_-])"
        )
        return pattern.sub(lambda match: mapping[match.group(0)], value)
    if isinstance(value, list):
        return [_rewrite_semantic_payload(item, mapping) for item in value]
    if isinstance(value, dict):
        return {key: _rewrite_semantic_payload(item, mapping) for key, item in value.items()}
    return copy.deepcopy(value)


def _structural_references(
    root: Path, protocol: Mapping[str, Any], variant: Mapping[str, Any], row: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, str]]:
    task = read(root / variant["task_path"])
    authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])
    ceilings = protocol["eligibility"]
    if typed_grounding_count(authority) > ceilings["grounding_estimate_ceiling"]:
        raise RuntimeError("grounding_estimate_ceiling")
    study = {
        "output_root": protocol["output_root"],
        "study_id": protocol["protocol_id"],
        "final": {"max_exact_decisions_per_algorithm": ceilings["max_decisions_per_algorithm"]},
    }
    costs, paths = {}, {}
    folder = (root / variant["task_path"]).parent
    for algorithm in protocol["algorithms"]:
        report = exact_reference(root, row, algorithm, study)
        decisions = len(report["events"])
        expansions = report["result"]["expansion_count"]
        if expansions > ceilings["max_expansions_per_algorithm"]:
            raise RuntimeError("reference_expansion_ceiling")
        path = folder / f"reference-{algorithm}.json.gz"
        write(path, report)
        costs[algorithm] = {"decisions": decisions, "expansions": expansions}
        paths[algorithm] = str(path.relative_to(root))
    if sum(row["decisions"] for row in costs.values()) > ceilings["max_summed_decisions"]:
        raise RuntimeError("summed_reference_decision_ceiling")
    return costs, paths


def _perturbation_references(
    root: Path,
    protocol: Mapping[str, Any],
    variant: Mapping[str, Any],
    row: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, str]]:
    panel = read(root / protocol["panel"])
    source = next(item for item in panel["tasks"] if item["row"]["task_id"] == variant["source"]["task_id"])
    semantic_map = read((root / variant["task_path"]).parent / "semantic_map.json")
    mapping = semantic_map.get("source_to_perturbed", {})
    source_task = read(root / source["row"]["task_path"])
    source_objects = set(PDDLStateAuthority.from_pddl(source_task["domain_pddl"], source_task["problem_pddl"]).objects)
    if set(mapping) != source_objects or len(set(mapping.values())) != len(mapping):
        raise ValueError("semantic map is not a complete object bijection")
    row["semantic_object_order"] = copy.deepcopy(mapping)
    derived_row = copy.deepcopy(row)
    derived_row["reference_costs"] = copy.deepcopy(source["row"]["reference_costs"])
    paths = {}
    for algorithm, source_path in source["reference_paths"].items():
        report = read(root / source_path)
        report = _translate_reference_report(root, derived_row, algorithm, report, mapping, protocol["protocol_id"])
        path = (root / variant["task_path"]).parent / f"reference-{algorithm}.json.gz"
        write(path, report)
        paths[algorithm] = str(path.relative_to(root))
    return copy.deepcopy(source["row"]["reference_costs"]), paths


def _translate_reference_report(
    root: Path,
    row: Mapping[str, Any],
    algorithm: str,
    source_report: Mapping[str, Any],
    mapping: Mapping[str, str],
    protocol_id: str,
) -> dict[str, Any]:
    """Replay mapped source operations and retain the derived runtime's canonical ordering."""

    session_row = dict(row)
    session_row["semantic_object_order"] = dict(mapping)
    session = VisualSession(root, session_row, algorithm, "exact_reference", 17, root, protocol_id)
    inverse = {target: source for source, target in mapping.items()}
    for index, source_event in enumerate(source_report["events"]):
        request = session.next_request()
        if request is None:
            raise ValueError(f"mapped reference ended before source event {index}")
        mapped_payload = json.loads(_rewrite_semantic_payload(source_event["raw_output"], mapping))
        live_payload = json.loads(session.reference_output())
        mapped_operation = (
            mapped_payload if algorithm.startswith("best_first_add") else mapped_payload["typed_operation"]
        )
        live_operation = live_payload if algorithm.startswith("best_first_add") else live_payload["typed_operation"]
        mapped_action = mapped_operation.get("action")
        candidates = []
        if live_operation.get("action") is not None:
            if algorithm.startswith("best_first_add"):
                table = request.model_input["successor_candidates"]
                action_index = table["columns"].index("action")
                candidates = [
                    {"grounded_action": {"name": row[action_index][0], "args": list(row[action_index][1:])}}
                    for row in table["rows"]
                ]
            elif algorithm == "best_first_width":
                candidates = [
                    candidate for candidate in request.observation["successor_candidates"] if not candidate["duplicate"]
                ]
            else:
                candidates = [
                    candidate
                    for candidate in request.model_input["search_memory"]["successor_candidates"]
                    if not candidate.get("visited", False)
                ]
            matches = [candidate for candidate in candidates if candidate["grounded_action"] == mapped_action]
            if algorithm == "best_first_width":
                frontier_size = request.observation["search_memory"]["frontier_size"]
                candidates = [
                    candidate
                    for candidate in candidates
                    if candidate["evaluation"]["frontier_intent"]["target_position"]
                    <= frontier_size - int(candidate["evaluation"]["frontier_intent"]["retire_source"])
                ]
                matches = [candidate for candidate in candidates if candidate["grounded_action"] == mapped_action]
                if not matches and candidates:
                    def source_action(candidate: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
                        action = candidate["grounded_action"]
                        return str(action["name"]), tuple(
                            str(inverse.get(argument, argument)) for argument in action["args"]
                        )

                    matches = [min(candidates, key=source_action)]
            if len(matches) == 1:
                live_operation["action"] = matches[0]["grounded_action"]
                if algorithm == "best_first_width":
                    live_operation["frontier_intent"] = matches[0]["evaluation"]["frontier_intent"]
        session.submit(json.dumps(live_payload, sort_keys=True, separators=(",", ":")))
        if not session.events[-1]["accepted"]:
            raise ValueError("mapped reference operation rejected by derived task")
    if session.next_request() is not None:
        raise ValueError("mapped reference source events ended before derived task")
    result = session.result()
    expected = source_report["result"]
    comparable = (
        "algorithm_invariants_hold",
        "decision_count",
        "expansion_count",
        "goal_reached",
        "invalid_operation_count",
        "invariant_valid_success",
        "termination_reason",
    )
    if any(result[key] != expected[key] for key in comparable):
        raise ValueError("mapped reference result differs from inherited source reference")
    return {"events": session.events, "result": result}


def _normalize_reference_limits(root: Path, variant: Mapping[str, Any], protocol: Mapping[str, Any]) -> None:
    multiplier = protocol["evaluation"]["reference_decision_multiplier"]
    for algorithm, relative in variant["reference_paths"].items():
        path = root / relative
        report = read(path)
        expected = multiplier * variant["row"]["reference_costs"][algorithm]["decisions"]
        if report["result"].get("model_call_limit") != expected:
            report["result"]["model_call_limit"] = expected
            write(path, report)


def screen_stage(root: Path) -> dict[str, Any]:
    protocol = load_protocol(root)
    generation = read(output_root(root, protocol) / "generation.json")
    results = []
    for variant in generation["variants"]:
        folder = (root / variant["task_path"]).parent
        saved = folder / "screen.json"
        if saved.exists():
            results.append(read(saved))
            continue
        row = _reference_row(root, protocol, variant)
        report = {"variant_id": variant["variant_id"], "family": variant["family"], "eligible": False}
        try:
            if variant["family"] in STRUCTURAL_FAMILIES:
                costs, paths = _structural_references(root, protocol, variant, row)
            else:
                costs, paths = _perturbation_references(root, protocol, variant, row)
                task = read(root / variant["task_path"])
                source_task = read(root / variant["source"]["task_path"])
                if variant["family"] in {"object-renaming", "render-restyle"}:
                    left = PDDLStateAuthority.from_pddl(source_task["domain_pddl"], source_task["problem_pddl"])
                    right = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])
                    if not same_instance(left.task_context(), right.task_context()):
                        raise RuntimeError("perturbation_isomorphism_failed")
            row["reference_costs"] = costs
            report.update(eligible=True, reason="reference_and_semantic_screen_pass", row=row, reference_paths=paths)
        except (RuntimeError, ValueError, TimeoutError) as error:
            report.update(reason=str(error), row=row, reference_paths={})
        write(saved, report)
        results.append(report)
    complete = {row["variant_id"] for row in results} == {row["variant_id"] for row in generation["variants"]}
    report = {
        "schema_version": "expanded_generalization_screening_v1",
        "outcome": "PASS" if complete else "INVALID",
        "variants": results,
        "eligible_before_view_audit": sum(row["eligible"] for row in results),
        "replacements": 0,
    }
    write(output_root(root, protocol) / "screening.json", report)
    return report


def _materialize_mapped_scenes(
    root: Path,
    row: Mapping[str, Any],
    task: Mapping[str, Any],
    catalog: dict[str, Any],
    output: Path,
    mapping: Mapping[str, str],
) -> None:
    """Rebind backend-qualified source VFGs through a frozen object bijection."""

    source_catalog = read(root / task["view_manifest"]["scene_catalog"])
    source_bindings: dict[tuple[str, ...], Mapping[str, Any]] = {}
    for binding in source_catalog["path_bindings"]:
        mapped_actions = tuple(_rewrite_semantic_payload(binding["supplied_actions"], mapping))
        if mapped_actions in source_bindings:
            raise ValueError("source scene catalog has duplicate mapped action paths")
        source_bindings[mapped_actions] = binding
    objects = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"]).objects
    output.mkdir(parents=True, exist_ok=False)
    (output / "frames").mkdir()
    (output / "domain.pddl").write_text(task["domain_pddl"], encoding="utf-8")
    (output / "problem.pddl").write_text(task["problem_pddl"], encoding="utf-8")
    rendered: set[int] = set()
    bindings = []
    for position, (indices, actions) in enumerate(catalog_paths(catalog)):
        source_binding = source_bindings.get(actions)
        if source_binding is None:
            raise ValueError("derived scene path has no mapped source VFG")
        payload = _rewrite_semantic_payload(read(root / source_binding["vfg"]), mapping)
        stages = payload.get("visualStages", [])
        if len(stages) != len(indices):
            raise ValueError("mapped source VFG stage count differs from derived scene path")
        vfg_path = output / f"path-{position:06d}.vfg.json.gz"
        write(vfg_path, payload)
        for state_index, stage in zip(indices, range(len(stages)), strict=True):
            if state_index in rendered:
                continue
            with tempfile.TemporaryDirectory(prefix="mapped-vfg-", dir=output) as temporary:
                temporary_path = Path(temporary)
                render_unlabelled_vfg(json.dumps(payload).encode(), temporary_path, stage, objects)
                (temporary_path / "frame_000.png").replace(output / "frames" / f"state-{state_index:06d}.png")
            rendered.add(state_index)
        bindings.append(
            {
                "supplied_actions": list(actions),
                "state_indices": indices,
                "vfg": str(vfg_path.relative_to(root)),
                "source_vfg": source_binding["vfg"],
                "endpoint": "retained-source-vfg-semantic-map",
                "semantic_validation": "source_vfg_rebound_by_frozen_object_bijection",
            }
        )
    for state in catalog["states"]:
        state["scene_path"] = str(
            (output / "frames" / f"state-{state['index']:06d}.png").relative_to(root)
        )
    catalog.update(
        task_id=row["task_id"],
        split=row["split"],
        reference_costs=row["reference_costs"],
        source_trace_paths=row["trace_paths"],
        path_bindings=bindings,
        stored_scene_size=[128, 128],
        canonical_goal=catalog["task_context"]["canonical_goal"],
        model_input_ready=False,
        partial_goal_images_complete=False,
        scene_transform=_MAPPED_SCENE_TRANSFORM,
    )
    write(output / "catalog.json.gz", catalog)


def _preserve_interrupted_scenes(scene_output: Path) -> None:
    if not scene_output.exists():
        return
    number = 1
    while scene_output.with_name(f"scenes-interrupted-{number}").exists():
        number += 1
    scene_output.rename(scene_output.with_name(f"scenes-interrupted-{number}"))


def _collect_task_scenes_with_retry(
    *,
    root: Path,
    row: dict[str, Any],
    profile: Path,
    endpoint: str,
    output: Path,
    catalog: dict[str, Any],
    attempts: int = 4,
    base_delay_seconds: float = 0.25,
) -> None:
    """Serialize the single-worker backend and retry only transient transport failures."""

    from scripts.planimation_phase1_client import preflight_host

    if attempts < 1:
        raise ValueError("Planimation render attempts must be positive")
    errors = []
    with _PLANIMATION_RENDER_LOCK:
        for attempt in range(attempts):
            _preserve_interrupted_scenes(output)
            readiness = preflight_host(endpoint, timeout=5)
            if not readiness.get("reachable"):
                error: RuntimeError | OSError = RuntimeError(
                    f"Planimation endpoint not ready: {readiness.get('error', 'unreachable')}"
                )
            else:
                try:
                    collect_task_scenes(
                        root=root,
                        row=row,
                        profile=profile,
                        endpoint=endpoint,
                        output=output,
                        timeout=30,
                        preflight=False,
                        progress=lambda _detail: None,
                        catalog=catalog,
                    )
                    return
                except (RuntimeError, OSError) as caught:
                    error = caught
            message = str(error).lower()
            if not any(marker in message for marker in _TRANSIENT_PLANIMATION_ERRORS):
                raise error
            errors.append(str(error))
            if attempt + 1 < attempts:
                time.sleep(base_delay_seconds * (2**attempt))
    raise RuntimeError(f"Planimation transient failure after {attempts} attempts: {' | '.join(errors)}")


def _render_variant_assets(
    root: Path,
    protocol: Mapping[str, Any],
    variant: Mapping[str, Any],
    *,
    endpoint: str,
) -> dict[str, Any]:
    folder = (root / variant["row"]["task_path"]).parent
    task = read(folder / "task.json")
    row = copy.deepcopy(variant["row"])
    references = variant["reference_paths"]
    catalog = reference_catalog(root, row, references, protocol["protocol_id"])
    views_root = folder / "views"
    profiles = read(root / "configs/experiments/issue71/v2/render.json")["domain_profiles"]
    scene_output = views_root / "scenes"
    retained_catalog = (
        read(scene_output / "catalog.json.gz") if (scene_output / "catalog.json.gz").exists() else None
    )
    migrate_perturbation_scenes = (
        variant["family"] in PERTURBATION_FAMILIES
        and retained_catalog is not None
        and retained_catalog.get("scene_transform") != _MAPPED_SCENE_TRANSFORM
    )
    if retained_catalog is None or migrate_perturbation_scenes:
        _preserve_interrupted_scenes(scene_output)
        if variant["family"] in PERTURBATION_FAMILIES:
            semantic_map = read(folder / "semantic_map.json")
            _materialize_mapped_scenes(
                root,
                row,
                task,
                catalog,
                scene_output,
                semantic_map["source_to_perturbed"],
            )
        else:
            _collect_task_scenes_with_retry(
                root=root,
                row=row,
                profile=root / profiles[row["domain"]],
                endpoint=endpoint,
                output=scene_output,
                catalog=catalog,
            )
    catalog = read(scene_output / "catalog.json.gz")
    source = source_task(task["domain_pddl"], task["problem_pddl"])
    goal_paths = []
    for recipe in paginate("goal", fact_blocks(catalog["task_context"], catalog["states"][0], source)["goal"]):
        path = views_root / f"goal-{recipe.index}.png"
        if not path.exists():
            image = compose_page(recipe, root)
            image.save(path)
            image.close()
        goal_paths.append(str(path.relative_to(root)))
    manifest_source = source
    manifest = {
        "task_id": row["task_id"],
        "split": "test",
        "scene_catalog": str((scene_output / "catalog.json.gz").relative_to(root)),
        "source": manifest_source,
        "task_context": catalog["task_context"],
        "reusable_pages": {"goal": goal_paths},
        "reference_costs": row["reference_costs"],
        "complete_reference_coverage": True,
        "full_reachable_closure": False,
    }
    prior_manifest = task.get("view_manifest", {})
    if variant["family"] == "name-compression":
        manifest["audit_source"] = copy.deepcopy(source)
        manifest["source"] = {
            **copy.deepcopy(source),
            "objects_by_type": {},
            "type_parents": {},
        }
    if variant["family"] == "render-restyle":
        manifest["render_overrides"] = materialize_view_manifest(task)["render_overrides"]
    manifest_path = views_root / "manifest.json"
    write(manifest_path, manifest)
    native = materialize_task(
        root,
        row["task_id"],
        str(manifest_path.relative_to(root)),
        range(len(catalog["states"])),
        views_root / "unlabelled",
        lambda *_args, **_kwargs: None,
    )
    if variant["family"] == "render-restyle":
        for state, binding in native["scene_bindings"].items():
            payload = read(root / binding["vfg"])
            with tempfile.TemporaryDirectory(dir=views_root, prefix="override-") as temporary:
                temporary_path = Path(temporary)
                render_unlabelled_vfg(
                    json.dumps(payload).encode(),
                    temporary_path,
                    binding["stage"],
                    PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"]).objects,
                    manifest["render_overrides"],
                )
                (temporary_path / "frame_000.png").replace(root / native["scenes"][state])
    task.update(
        asset_root=str(root),
        row=row,
        native_views=native,
        view_manifest=manifest,
        text_pages=_actual_text_inventory(manifest, catalog),
    )
    write(folder / "task-with-views.json", task)
    measurements = _measure_inputs(root, task, references)
    return {"task": task, "measurements": measurements, "source_manifest": prior_manifest}


def _measure_inputs(root: Path, task: Mapping[str, Any], references: Mapping[str, str]) -> list[dict[str, Any]]:
    from .visual_episode import VisualSession

    views = SceneOnlyViews(root, {task["row"]["task_id"]: task["native_views"]})
    catalog = _asset_catalog(root, task)
    measurements = []
    for algorithm, path in references.items():
        events = read(root / path)["events"]
        if not events:
            continue
        session = VisualSession(root, task["row"], algorithm, "exact_reference", 17, root, "probe", views=None)
        for event in events:
            request = session.next_request()
            state = next(
                row["state"]
                for row in catalog["decisions"]
                if row["algorithm"] == algorithm and row["index"] == len(session.events)
            )
            semantic = fact_blocks(catalog["task_context"], catalog["states"][state], task["view_manifest"]["source"])
            counts = {}
            for modality in ("text-state", "visual-state", "multimodal-state"):
                example = views.observe(
                    task["row"]["task_id"],
                    state,
                    dict(request.model_input),
                    algorithm,
                    semantic,
                    modality,
                )
                counts[modality] = example["binding"]["input_tokens"]
                for image in example["images"]:
                    image.close()
            measurements.append({"algorithm": algorithm, "index": len(session.events), "input_tokens": counts})
            session.submit(event["raw_output"])
    return measurements


def _asset_catalog(root: Path, task: Mapping[str, Any]) -> dict[str, Any]:
    return read(root / task["view_manifest"]["scene_catalog"])


def _source_audit_task(
    root: Path, source: Mapping[str, Any], panel_views: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    return _source_asset(root, source, panel_views)


def _inventory_record(task_id: str, domain: str, problem: str) -> dict[str, Any]:
    authority = PDDLStateAuthority.from_pddl(domain, problem)
    return {
        "task_id": task_id,
        "task_semantics": task_semantics(domain, problem),
        "task_context": authority.task_context(),
    }


def disjointness_inventory(root: Path, protocol: Mapping[str, Any]) -> list[dict[str, Any]]:
    domains = {row["domain"] for row in protocol["source_problems"]}
    _identities, retained = retained_tasks(root, domains)
    result = []
    for index, evidence in enumerate(retained):
        if "task_path" in evidence:
            task = read(root / evidence["task_path"])
            domain, problem = task["domain_pddl"], task["problem_pddl"]
        else:
            domain, problem, _changes = _normalize_authority_input(
                (root / evidence["domain_path"]).read_text(),
                (root / evidence["problem_path"]).read_text(),
            )
        result.append(_inventory_record(f"historical:{index}", domain, problem))
    panels = [
        read(root / protocol["panel"]),
        read(root / "outputs/matched_modalities/v5/preparation/final-panel.json"),
    ]
    for panel in panels:
        for item in panel["tasks"]:
            row = item["row"]
            task = read(root / row["task_path"])
            result.append(_inventory_record(row["task_id"], task["domain_pddl"], task["problem_pddl"]))
    deduplicated = {}
    for row in result:
        deduplicated[(row["task_id"], row["task_semantics"])] = row
    return list(deduplicated.values())


def audit_stage(
    root: Path,
    *,
    endpoint: str = "http://127.0.0.1:18092",
    renderer: Callable[..., dict[str, Any]] = _render_variant_assets,
    disjointness_inventory_rows: Iterable[Mapping[str, Any]] | None = None,
    only: Iterable[str] | None = None,
) -> dict[str, Any]:
    protocol = load_protocol(root)
    inventory = (
        list(disjointness_inventory_rows)
        if disjointness_inventory_rows is not None
        else disjointness_inventory(root, protocol)
    )
    screening = read(output_root(root, protocol) / "screening.json")
    panel_views = _panel_views(root, protocol)
    selected = set(only or (row["variant_id"] for row in screening["variants"]))
    known = {row["variant_id"] for row in screening["variants"]}
    if not selected or not selected <= known:
        raise ValueError(f"unknown or empty audit subset: {sorted(selected - known)}")
    generation = {
        row["variant_id"]: row for row in read(output_root(root, protocol) / "generation.json")["variants"]
    }
    results = []
    for screened in screening["variants"]:
        if screened["variant_id"] not in selected:
            continue
        folder = (root / screened["row"]["task_path"]).parent
        saved = folder / "audit.json"
        report = {"variant_id": screened["variant_id"], "family": screened["family"], "eligible": False}
        if not screened["eligible"]:
            report["reason"] = screened["reason"]
            write(saved, report)
            results.append(report)
            continue
        generated = generation[screened["variant_id"]]
        try:
            if screened["family"] in PERTURBATION_FAMILIES:
                costs, paths = _perturbation_references(root, protocol, generated, screened["row"])
                if costs != screened["row"]["reference_costs"]:
                    raise ValueError("retranslated perturbation reference costs differ")
                screened = {**screened, "reference_paths": paths}
            else:
                _normalize_reference_limits(root, screened, protocol)
            assets = renderer(root, protocol, screened, endpoint=endpoint)
            task = assets["task"]
            integrity = {
                "initial_view": Path(root / task["native_views"]["scenes"]["0"]).is_file(),
                "goal_view": all((root / path).is_file() for path in task["native_views"]["goal_pages"]),
                "view_manifest": bool(materialize_view_manifest(task)),
            }
            input_max = max(
                (
                    value
                    for measurement in assets["measurements"]
                    for value in measurement["input_tokens"].values()
                ),
                default=0,
            )
            eligibility = eligibility_screen(
                task,
                screened["row"]["reference_costs"],
                protocol["eligibility"],
                input_tokens=input_max,
                view_integrity=integrity,
            )
            audits = {"eligibility": eligibility, "recoverability": {}}
            semantic_map = read(folder / "semantic_map.json")
            source_task = _source_audit_task(root, generated["source"], panel_views)
            if screened["family"] in PERTURBATION_FAMILIES:
                if not semantically_disjoint(
                    task,
                    inventory,
                    candidate_kind="perturbation",
                    source_task_id=generated["source"]["task_id"],
                ):
                    raise ValueError("perturbation overlaps a non-source retained task")
                for modality in protocol["modalities"]:
                    audits["recoverability"][modality] = audit_perturbation(
                        source_task,
                        task,
                        screened["family"],
                        semantic_map,
                        modality,
                        source_reference_costs=screened["row"]["reference_costs"],
                        perturbed_reference_costs=screened["row"]["reference_costs"],
                    )
                if (
                    screened["family"] == "object-renaming"
                    and not audits["recoverability"]["text-state"]["same_instance"]
                ):
                    raise ValueError("P1 isomorphism audit failed")
                if screened["family"] == "render-restyle":
                    source_scene = root / source_task["native_views"]["scenes"]["0"]
                    target_scene = root / task["native_views"]["scenes"]["0"]
                    audits["render_restyle"] = {
                        "manifest_override": materialize_view_manifest(task)["render_overrides"],
                        "bytes_differ": sha256(source_scene) != sha256(target_scene),
                        "visibility_preserved": view_information(source_task, "visual-state")["object_identities"]
                        == view_information(task, "visual-state")["object_identities"],
                    }
                    if not all(value for key, value in audits["render_restyle"].items() if key != "manifest_override"):
                        raise ValueError("P2 render audit failed")
            else:
                if not semantically_disjoint(task, inventory, candidate_kind="structural"):
                    raise ValueError("structural whole-instance overlap")
                audits["structural_disjoint"] = True
            report.update(
                eligible=eligibility["eligible"],
                reason="audit_pass" if eligibility["eligible"] else ",".join(eligibility["reasons"]),
                audits=audits,
                task_path=str((folder / "task-with-views.json").relative_to(root)),
                row=task["row"],
                native_views=task["native_views"],
                view_manifest=task["view_manifest"],
                measurements=assets["measurements"],
                reference_paths=screened["reference_paths"],
                source_stratum=generated["source"]["stratum_origin"],
            )
        except (RuntimeError, ValueError, OSError) as error:
            report["reason"] = str(error)
        write(saved, report)
        results.append(report)
    aggregate_path = output_root(root, protocol) / "audit.json"
    prior = read(aggregate_path).get("variants", []) if aggregate_path.exists() and only is not None else []
    merged = {row["variant_id"]: row for row in prior}
    merged.update({row["variant_id"]: row for row in results})
    report = {
        "schema_version": "expanded_generalization_audit_v1",
        "outcome": "PASS",
        "variants": [merged[key] for key in sorted(merged)],
        "audited_subset": sorted(selected),
    }
    write(aggregate_path, report)
    return {**report, "variants": results}


def _asset_hashes(root: Path, report: Mapping[str, Any]) -> dict[str, str]:
    task_path = root / report["task_path"]
    paths = [task_path, task_path.parent / "semantic_map.json"]
    paths.extend(root / path for path in report["native_views"].get("scenes", {}).values())
    paths.extend(root / path for path in report["native_views"].get("goal_pages", []))
    paths.extend(root / path for path in report["native_views"].get("static_pages", []))
    source_manifest = report["native_views"].get("source_manifest")
    if source_manifest:
        paths.append(root / source_manifest)
    scene_catalog = report["view_manifest"].get("scene_catalog")
    if scene_catalog:
        catalog_path = root / scene_catalog
        paths.append(catalog_path)
        if catalog_path.is_file():
            catalog = read(catalog_path)
            paths.extend(root / binding["vfg"] for binding in catalog.get("path_bindings", []))
    paths.extend(root / path for path in report.get("reference_paths", {}).values())
    return {str(path.relative_to(root)): sha256(path) for path in sorted(set(paths)) if path.is_file()}


def freeze_stage(root: Path) -> dict[str, Any]:
    protocol = load_protocol(root)
    audit = read(output_root(root, protocol) / "audit.json")
    tasks = []
    qualification = []
    for report in audit["variants"]:
        qualification.append(
            {
                "variant_id": report["variant_id"],
                "family": report["family"],
                "eligible": report["eligible"],
                "reason": report["reason"],
                "audits": report.get("audits", {}),
                "audit_status": "present" if report.get("audits") else "absent-because-ineligible",
                "audit_absence_reason": None if report.get("audits") else report["reason"],
                "reference_costs": report.get("row", {}).get("reference_costs", {}),
                "asset_sha256": _asset_hashes(root, report) if report.get("task_path") else {},
            }
        )
        if report["eligible"]:
            tasks.append(
                {
                    "variant_id": report["variant_id"],
                    "family": report["family"],
                    "row": report["row"],
                    "native_views": report["native_views"],
                    "view_manifest": report["view_manifest"],
                    "task_path": report["task_path"],
                    "reference_paths": report["reference_paths"],
                    "measurements": report["measurements"],
                    "source_stratum": report["source_stratum"],
                }
            )
    tasks.sort(key=lambda row: row["variant_id"])
    suite = {
        "schema_version": "expanded_generalization_suite_v1",
        "protocol_id": protocol["protocol_id"],
        "tasks": tasks,
        "eligible": len(tasks),
        "missing": len(qualification) - len(tasks),
        "outcome": "PASS" if tasks else "BLOCKED",
    }
    suite_path = output_root(root, protocol) / "suite.json"
    qualification_path = output_root(root, protocol) / "qualification.json"
    write(suite_path, suite)
    write(qualification_path, {"outcome": "PASS" if tasks else "BLOCKED", "variants": qualification})
    manifest = {
        "schema_version": "expanded_generalization_suite_sha256_v1",
        "files": {
            str(suite_path.relative_to(root)): sha256(suite_path),
            str(qualification_path.relative_to(root)): sha256(qualification_path),
        },
    }
    write(output_root(root, protocol) / "suite-sha256.json", manifest)
    if not tasks:
        raise RuntimeError("BLOCKED: zero eligible Goal 11 variants; empty suite cannot pass qualification")
    return suite


def select_probe_inputs(tasks: Iterable[Mapping[str, Any]], protocol: Mapping[str, Any]) -> list[dict[str, Any]]:
    selected = []
    for family in FAMILIES:
        candidates = [task for task in tasks if task["family"] == family]
        if not candidates:
            raise ValueError(f"probe family has no eligible task: {family}")
        hardest = min(
            candidates,
            key=lambda task: (
                -sum(cost["decisions"] for cost in task["row"]["reference_costs"].values()),
                task["row"]["task_id"],
            ),
        )
        for algorithm in protocol["algorithms"]:
            for modality in protocol["modalities"]:
                selected.append(
                    {
                        "probe_id": f"{family}:{algorithm}:{modality}",
                        "family": family,
                        "algorithm": algorithm,
                        "modality": modality,
                        "variant_id": hardest["variant_id"],
                        "task": copy.deepcopy(hardest),
                    }
                )
    if len(selected) != 60 or len({row["probe_id"] for row in selected}) != 60:
        raise ValueError("frozen probe input coverage differs")
    return selected


def probe_inputs_stage(root: Path) -> dict[str, Any]:
    protocol = load_protocol(root)
    suite = read(output_root(root, protocol) / "suite.json")
    inputs = select_probe_inputs(suite["tasks"], protocol)
    path = output_root(root, protocol) / "probe-inputs.json"
    write(path, {"schema_version": "expanded_generalization_probe_inputs_v1", "inputs": inputs})
    job = {
        "job_id": "generalization-probe",
        "branch": protocol["budget_branch"],
        "gpus": [0],
        "max_seconds": 14400,
        "total": protocol["throughput_probe"]["timing_calls"],
        "command": ["python", "scripts/run_expanded_generalization.py", "probe-worker", "--worker", "0"],
        "completion_hook": ["python", "scripts/run_expanded_generalization.py", "probe-finalize"],
    }
    write(output_root(root, protocol) / "probe-job.json", job)
    return {"inputs": inputs, "job": job}


def aggregate_probe(
    measurements: Iterable[Mapping[str, Any]],
    overheads: Iterable[Mapping[str, Any]],
    *,
    probe_gpu_hours: float,
    margin: float = 1.5,
) -> dict[str, Any]:
    grouped: dict[tuple[str, str], list[float]] = {}
    rows = []
    for measurement in measurements:
        if set(measurement) - PROBE_PERSIST_FIELDS:
            raise ValueError("probe measurement retained non-whitelisted fields")
        key = (measurement["algorithm"], measurement["modality"])
        grouped.setdefault(key, []).append(float(measurement["call_wall_seconds"]))
        rows.append(dict(measurement))
    bounds = {
        f"{algorithm}__{modality}": {
            "max_observed_call_seconds": max(values),
            "bound_seconds": max(values) * margin,
            "samples": len(values),
        }
        for (algorithm, modality), values in sorted(grouped.items())
    }
    overhead_rows = [dict(row) for row in overheads]
    return {
        "schema_version": "expanded_generalization_probe_v1",
        "outcome": "PASS",
        "measurements": rows,
        "per_combo_bounds": bounds,
        "worker_overheads": overhead_rows,
        "planned_worker_overhead_seconds": max(
            (float(row["model_load_wall_seconds"]) + float(row["model_save_wall_seconds"]) for row in overhead_rows),
            default=0.0,
        ),
        "probe_gpu_hours": probe_gpu_hours,
        "margin": margin,
    }


def _branch_spend(ledger: Mapping[str, Any], branch: str) -> float:
    total = 0.0
    for attempt in ledger["attempts"]:
        if attempt["branch"] != branch:
            continue
        total += (
            attempt["max_seconds"] * len(attempt["gpus"]) / 3600
            if attempt["status"] in {"reserved", "running"}
            else attempt["gpu_hours"]
        )
    return total


def probe_finalize_stage(root: Path) -> dict[str, Any]:
    protocol = load_protocol(root)
    ledger = read(root / "outputs/expanded-study/v1/budget.json")
    attempts = [row for row in ledger["attempts"] if row["job_id"] == "generalization-probe"]
    if not attempts or attempts[-1]["status"] != "succeeded":
        raise ValueError("generalization probe scheduler attempt is incomplete")
    attempt = attempts[-1]
    worker = read(Path(attempt["directory"]) / "probe-worker.json")
    report = aggregate_probe(
        worker["measurements"],
        worker["worker_overheads"],
        probe_gpu_hours=sum(row["gpu_hours"] for row in attempts),
        margin=protocol["throughput_probe"]["call_time_margin"],
    )
    write(output_root(root, protocol) / "probe.json", report)
    return report


def matrix_gpu_hours(
    tasks: Iterable[Mapping[str, Any]],
    bounds: Mapping[str, Mapping[str, float]],
    protocol: Mapping[str, Any],
) -> float:
    seconds = 0.0
    for task in tasks:
        for algorithm in protocol["algorithms"]:
            cap = protocol["evaluation"]["reference_decision_multiplier"] * task["row"]["reference_costs"][algorithm][
                "decisions"
            ]
            for modality in protocol["modalities"]:
                seconds += 2 * cap * bounds[f"{algorithm}__{modality}"]["bound_seconds"]
    return seconds / 3600


def decide_admission(
    tasks: Iterable[Mapping[str, Any]],
    probe: Mapping[str, Any],
    protocol: Mapping[str, Any],
    *,
    branch_spent_gpu_hours: float,
    recovery_available_gpu_hours: float,
    planned_worker_jobs: int = 2,
) -> dict[str, Any]:
    rows = list(tasks)
    levels = {
        "L0": rows,
        "L2": [row for row in rows if row["family"] != "name-compression"],
        "L3": [
            row
            for row in rows
            if row["source_stratum"] == "expanded"
            and row["family"] in {"scale-up", "shifted-init", "object-renaming", "render-restyle"}
        ],
    }
    branch_cap = protocol["budget_gpu_hours"]
    remainder = branch_cap - branch_spent_gpu_hours
    probe_spend = float(probe["probe_gpu_hours"])
    overhead = planned_worker_jobs * float(probe["planned_worker_overhead_seconds"]) / 3600
    arithmetic = {}
    for level, members in levels.items():
        matrix = matrix_gpu_hours(members, probe["per_combo_bounds"], protocol)
        required = matrix * protocol["admission"]["safety_factor"] + probe_spend + overhead
        arithmetic[level] = {
            "tasks": len(members),
            "matrix_gpu_hours": matrix,
            "safety_factor": protocol["admission"]["safety_factor"],
            "probe_gpu_hours": probe_spend,
            "planned_worker_overhead_gpu_hours": overhead,
            "required_gpu_hours": required,
            "fits_branch_remainder": required <= remainder,
        }
    transfer = None
    if arithmetic["L0"]["fits_branch_remainder"]:
        decision = "L0"
    elif arithmetic["L0"]["required_gpu_hours"] <= remainder + recovery_available_gpu_hours:
        decision = "L1"
        transfer = {
            "from": "recovery_reserve",
            "to": protocol["budget_branch"],
            "gpu_hours": arithmetic["L0"]["required_gpu_hours"] - remainder,
            "reason": "Minimum sufficient prospective transfer to admit frozen Goal 11 L0 before outcomes.",
            "executed": False,
        }
    elif arithmetic["L2"]["fits_branch_remainder"]:
        decision = "L2"
    elif arithmetic["L3"]["fits_branch_remainder"]:
        decision = "L3"
    else:
        decision = "L4"
    return {
        "schema_version": "expanded_generalization_admission_v1",
        "decision": decision,
        "outcome": "VALID_STOP" if decision == "L4" else "PASS",
        "branch_cap_gpu_hours": branch_cap,
        "branch_spent_gpu_hours": branch_spent_gpu_hours,
        "branch_remainder_gpu_hours": remainder,
        "recovery_available_gpu_hours": recovery_available_gpu_hours,
        "arithmetic": arithmetic,
        "transfer_request": transfer,
        "ledger_mutated": False,
    }


def admit_stage(root: Path) -> dict[str, Any]:
    protocol = load_protocol(root)
    suite = read(output_root(root, protocol) / "suite.json")
    probe = read(output_root(root, protocol) / "probe.json")
    ledger = read(root / "outputs/expanded-study/v1/budget.json")
    tasks = suite["tasks"]
    recovery_spent = _branch_spend(ledger, "recovery_reserve")
    result = decide_admission(
        tasks,
        probe,
        protocol,
        branch_spent_gpu_hours=_branch_spend(ledger, protocol["budget_branch"]),
        recovery_available_gpu_hours=ledger["allocations_gpu_hours"]["recovery_reserve"] - recovery_spent,
    )
    write(output_root(root, protocol) / "admission.json", result)
    return result
