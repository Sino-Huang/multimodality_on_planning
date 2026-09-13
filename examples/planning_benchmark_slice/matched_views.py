"""Complete, read-only final task views, separate from the training corpus."""

from __future__ import annotations

import copy

from .best_first_model_input import expand_compact_best_first_facts
from .bfws_model_input import _group_atoms
from .matched_tasks import require_pool_coverage
from .modality_corpus_replay import canonical
from .modality_pages import PageRecipe, compose_page, fact_blocks, paginate, validate_pages
from .modality_view_preparation import _state_goal_checks, frozen_processor, write_json
from .pddl_state import PDDLStateAuthority
from .scene_assets import collect_task_scenes, load_scene_task, read_json
from .source_goal import source_task
from .visual_episode import VisualSession, VisualTaskViews


def index_for_input(raw, algorithm, catalog):
    if algorithm == "best_first_width":
        symbols = {n: i for i, n in enumerate(raw["task_context"]["objects"])}
        key = canonical([raw["observation"]["state"]["atoms"], raw["observation"]["state"]["fluents"]])
        return next(
            s["index"] for s in catalog["states"] if canonical([_group_atoms(s["atoms"], symbols), s["fluents"]]) == key
        )
    atoms = (
        raw["observation"]["state_atoms"]
        if algorithm == "bfs"
        else expand_compact_best_first_facts(raw["current"]["state_facts"])
    )
    return next(s["index"] for s in catalog["states"] if sorted(s["atoms"]) == sorted(atoms))


def final_view_store(root, study, task, *, read_only=True):
    return VisualTaskViews(
        root,
        task["row"],
        task["view_manifest"],
        root / study["output_root"] / "live-views" / task["row"]["task_id"].replace("/", "__"),
        study["backend_endpoints"][0],
        read_only=read_only,
    )


def check_final_task(root, study, task, progress):
    row = task["row"]
    views = final_view_store(root, study, task)
    manifest, catalog = views.manifest, views.catalog
    if not manifest["complete"] or manifest["split"] != "test":
        raise ValueError("incomplete final view manifest or relabelled split")
    _state_goal_checks(views.authority, catalog, manifest["source"])
    # Prove closure again: no future accepted state may require an unqualified scene.
    known = {canonical([sorted(s["atoms"]), sorted(s["fluents"])]) for s in catalog["states"]}
    for i, state in enumerate(catalog["states"]):
        canonical_state = views.authority.canonical_state(tuple(state["atoms"]), tuple(state["fluents"]))
        for action in views.authority.applicable_actions(canonical_state):
            target = views.authority.apply(canonical_state, action).target_state
            if canonical([sorted(target.atoms), sorted(target.fluents)]) not in known:
                raise ValueError("final state/view catalog is not closed under trusted transitions")
        blocks = fact_blocks(catalog["task_context"], state, manifest["source"])
        for role in ("task-context", "current-state", "goal"):
            recipes = manifest["state_recipes"][i] if role == "current-state" else manifest["reusable_recipes"][role]
            validate_pages(blocks[role], tuple(PageRecipe(**p) for p in recipes))
        if not (root / state["scene_path"]).is_file():
            raise ValueError("missing final scene")
    measurements = []
    processor = frozen_processor()
    for algorithm in study["algorithms"]:
        reference = read_json(root / row["reference_paths"][algorithm])
        session = VisualSession(root, row, algorithm, "exact_reference", 17, root, study["study_id"], views=views)
        for event in reference["events"]:
            request = session.next_request()
            if request is None or dict(request.model_input) != event["input"]:
                raise ValueError("final reference differs from live runtime")
            counts = {}
            for modality in study["modalities"]:
                example = views.observe(dict(request.model_input), algorithm, modality=modality, pixels=False)
                counts[modality] = example["binding"]["input_tokens"]
            # Actual pixels/template cross-check for the first live request per family.
            if not session.events:
                example = views.observe(dict(request.model_input), algorithm, modality="multimodal-state")
                processor.verify_complete(example["messages"], example["images"])
                for image in example["images"]:
                    image.close()
            measurements.append(
                {
                    "algorithm": algorithm,
                    "index": len(session.events),
                    "input_tokens": counts,
                    "state": index_for_input(event["input"], algorithm, catalog),
                }
            )
            session.submit(event["raw_output"])
        if session.next_request() is not None or session.result() != reference["result"]:
            raise ValueError("final reference result or completion differs")
    progress(
        "prepare:final_task_verified",
        completed=len(catalog["states"]),
        total=len(catalog["states"]),
        task=row["task_id"],
    )
    return measurements


def materialize_final_task(root, study, candidate, progress):
    row = copy.deepcopy(candidate["row"])
    base = root / study["output_root"] / "preparation" / "final" / f"{candidate['domain']}-{candidate['seed']}"
    saved = base / "result.json"
    if saved.exists():
        result = read_json(saved)
        if result["study"] != study:
            raise ValueError("existing final views differ from study")
        check_final_task(root, study, result, progress)
        return result
    catalog = read_json(root / candidate["reachable"])
    domain, problem, _ = load_scene_task(root, row)
    source = source_task(domain, problem)
    authority = PDDLStateAuthority.from_pddl(domain, problem)
    _state_goal_checks(authority, catalog, source)
    row["reference_paths"] = {
        a: str((root / row["task_path"]).parent.relative_to(root) / f"reference-{a}.json.gz")
        for a in study["algorithms"]
    }
    catalog["decisions"] = []
    for algorithm, path in row["reference_paths"].items():
        for i, event in enumerate(read_json(root / path)["events"]):
            catalog["decisions"].append(
                {"algorithm": algorithm, "index": i, "state": index_for_input(event["input"], algorithm, catalog)}
            )
    scene_output = base / "scenes"
    catalog_path = scene_output / "catalog.json.gz"
    if not catalog_path.exists():
        if scene_output.exists():
            # Preserve interrupted renderer output; a new directory is explicit.
            n = 1
            while scene_output.with_name(f"scenes-interrupted-{n}").exists():
                n += 1
            scene_output.rename(scene_output.with_name(f"scenes-interrupted-{n}"))
        render = read_json(root / "configs/experiments/issue71/v2/render.json")
        collect_task_scenes(
            root=root,
            row=row,
            profile=root / render["domain_profiles"][row["domain"]],
            endpoint=study["backend_endpoints"][0],
            output=scene_output,
            timeout=30,
            preflight=False,
            progress=lambda fields: progress("prepare:render", task=row["task_id"], detail=fields),
            catalog=catalog,
        )
    catalog = read_json(catalog_path)
    blocks = fact_blocks(catalog["task_context"], catalog["states"][0], source)
    reusable = {role: paginate(role, blocks[role]) for role in ("task-context", "goal")}
    recipes = [
        paginate(
            "current-state", fact_blocks(catalog["task_context"], state, source)["current-state"], state["scene_path"]
        )
        for state in catalog["states"]
    ]
    pages = {}
    for role, role_recipes in reusable.items():
        pages[role] = []
        for page in role_recipes:
            path = base / f"{role}-{page.index}.png"
            compose_page(page, root).save(path)
            pages[role].append(str(path.relative_to(root)))
    manifest = {
        "task_id": row["task_id"],
        "split": "test",
        "scene_catalog": str(catalog_path.relative_to(root)),
        "source": source,
        "task_context": catalog["task_context"],
        "reference_costs": row["reference_costs"],
        "reusable_pages": pages,
        "reusable_recipes": {r: [p.to_dict() for p in ps] for r, ps in reusable.items()},
        "state_recipes": [[p.to_dict() for p in ps] for ps in recipes],
        "complete": True,
    }
    manifest_path = base / "manifest.json.gz"
    write_json(manifest_path, manifest)
    result = {
        "study": study,
        "row": row,
        "view_manifest": str(manifest_path.relative_to(root)),
        "states": len(catalog["states"]),
        "outcome": "PASS",
    }
    measurements = check_final_task(root, study, result, progress)
    result["measurements"] = measurements
    result["maximum_input_tokens"] = {m: max(x["input_tokens"][m] for x in measurements) for m in study["modalities"]}
    dense = max(
        range(len(recipes)),
        key=lambda i: (len(recipes[i]), sum(len(f["text"]) for p in recipes[i] for f in p.fragments)),
    )
    previews = []
    for page in (*reusable["task-context"], *recipes[dense], *reusable["goal"]):
        path = base / f"preview-{page.role}-{page.index}.png"
        image = compose_page(page, root)
        frozen_processor().preview(image).save(path)
        image.close()
        previews.append(str(path.relative_to(root)))
    result["processed_previews"] = previews
    write_json(saved, result)
    return result


def prepare_final_panel(root, study, pool, progress):
    require_pool_coverage(pool, study)
    selected = []
    for domain in study["final"]["domains"]:
        candidates = [c for c in pool["candidates"] if c["domain"] == domain and c["eligible"]]
        if not candidates:
            raise RuntimeError(f"VALID_STOP: no eligible {domain} candidate")
        # No model outcomes are observed here; candidates are in frozen seed order.
        for candidate in candidates:
            try:
                task = materialize_final_task(root, study, candidate, progress)
            except RuntimeError as error:
                if "input exceeds" not in str(error):
                    raise
                path = root / study["output_root"] / "preparation" / f"layout-rejected-{domain}-{candidate['seed']}.json"
                write_json(path, {"reason": str(error), "seed": candidate["seed"], "domain": domain})
                continue
            selected.append(task)
            break
        else:
            raise RuntimeError(f"VALID_STOP: no input-size-qualified {domain} candidate")
    return selected
