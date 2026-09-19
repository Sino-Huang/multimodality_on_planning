"""Read-only semantic preparation audits and explicit final-task admission stops."""

from __future__ import annotations

import json
from collections import Counter

from .matched_tasks import exact_reference, require_pool_coverage, retained_tasks, task_semantics
from .modality_corpus import ModalityCorpus, iter_shard, project_record
from .modality_corpus_replay import canonical
from .modality_pages import PageRecipe, fact_blocks, validate_pages
from .modality_view_preparation import _state_goal_checks, frozen_processor
from .pddl_state import PDDLStateAuthority
from .scene_assets import load_scene_task, read_json
from .source_goal import evaluate_goal


def audit_training(root, study, progress):
    membership = read_json(root / study["membership"])
    corpus = ModalityCorpus(root, root / study["corpus_report"])
    if study["search_memory"] != corpus.contract["search_memory"]:
        raise ValueError("Search Memory differs from the shared release")
    if study["model_revision"] != corpus.contract["model_revision"]:
        raise ValueError("model/processor revision differs from the shared release")
    wanted = {}
    for field, split in (("training_record_ids", "train"), ("diagnostic_record_ids", "dev")):
        if set(membership[field]) != set(study["algorithms"]):
            raise ValueError("selected algorithm coverage differs")
        for algorithm, ids in membership[field].items():
            if len(ids) != len(set(ids)):
                raise ValueError("duplicate selected training/diagnostic record")
            for record_id in ids:
                if record_id in wanted:
                    raise ValueError("record crosses training/diagnostic selection")
                wanted[record_id] = (algorithm, split)
    processor = frozen_processor()
    found, semantic_splits, inputs, maxima = set(), {}, {}, Counter()
    contexts = {}
    task_refs = []
    panel = {r["task_id"]: r for r in read_json(root / corpus.contract["panel_manifest"])["selected"]}
    for task in corpus.results.values():
        records = [r for r in iter_shard(root / task["path"]) if r["record_id"] in wanted]
        if not records:
            continue
        manifest = read_json(root / task["view_manifest"])
        catalog = read_json(root / manifest["scene_catalog"])
        domain, problem, _ = load_scene_task(root, panel[task["task_id"]])
        authority = PDDLStateAuthority.from_pddl(domain, problem)
        _state_goal_checks(authority, catalog, manifest["source"])
        semantic_task = canonical(catalog["task_context"])
        if semantic_splits.setdefault(semantic_task, task["split"]) != task["split"]:
            raise ValueError("semantic task crosses selected train/dev splits")
        task_refs.append(
            {
                "task_id": task["task_id"],
                "split": task["split"],
                "source_shard": task["path"],
                "view_manifest": task["view_manifest"],
            }
        )
        for record in records:
            key = record["record_id"]
            if key in found or wanted[key] != (record["algorithm"], record["split"]) or record["split"] != task["split"]:
                raise ValueError("selected record identity/split differs")
            state = catalog["states"][record["state"]]
            target_tokens = len(
                processor.processor.tokenizer.encode(canonical(record["target"]), add_special_tokens=False)
            )
            if target_tokens > study["output_tokens"] or target_tokens != record["tokens"]["target"]:
                raise ValueError("teacher target exceeds or differs from frozen processor output allowance")
            blocks = fact_blocks(catalog["task_context"], state, manifest["source"])
            for role in ("task-context", "current-state", "goal"):
                pages = (
                    manifest["state_recipes"][record["state"]]
                    if role == "current-state"
                    else manifest["reusable_recipes"][role]
                )
                validate_pages(blocks[role], tuple(PageRecipe(**p) for p in pages))
            common = []
            for modality in study["modalities"]:
                messages = project_record(record, manifest, catalog, modality)
                payload = json.loads(messages[-1]["content"][0]["text"])
                if modality != "visual-state" and payload.pop("semantic_blocks") != blocks:
                    raise ValueError("text facts/goals differ from drawing instructions")
                payload.pop("representation")
                common.append(payload)
                if len(canonical(payload).encode()) > study["search_memory"]["max_bytes"]:
                    raise ValueError("common Search Memory exceeds the frozen byte cap")
                count = processor.count(messages)
                if count > study["maximum_input_tokens"]:
                    raise ValueError("complete selected input exceeds 32K")
                if count != record["tokens"]["input"][modality]:
                    raise ValueError("actual processor differs from released complete input measurement")
                maxima[modality] = max(maxima[modality], count)
                # Visual messages contain page references, not the pixels. The
                # same role/index in different tasks is not the same image input.
                input_key = (modality, canonical(messages), canonical(blocks))
                target = canonical(record["target"])
                if input_key in inputs and inputs[input_key] != (record["split"], target):
                    raise ValueError(f"cross-split semantic input overlap or conflicting target at {key}")
                inputs[input_key] = (record["split"], target)
            if common[0] != common[1] or common[0] != common[2]:
                raise ValueError("common search/candidate information differs across modalities")
            for role, index, _ in record["input_pages"]:
                if role == "current-state" and index != record["state"]:
                    raise ValueError("future image in current observation")
            # The source checker was already exercised over the entire release;
            # verify the actual selected states against the retained source goal.
            facts = set(catalog["task_context"]["static_initial_facts"]) | set(state["atoms"])
            goal = evaluate_goal(manifest["source"]["source_goal"], facts, manifest["source"])
            if goal != authority.is_goal(authority.canonical_state(tuple(state["atoms"]), tuple(state["fluents"]))):
                raise ValueError("selected source-goal evaluation differs from trusted checker")
            contexts[(task["task_id"], record["state"])] = goal
            found.add(key)
        progress("prepare:training", completed=len(found), total=len(wanted))
    if found != set(wanted):
        raise ValueError("selected training/diagnostic coverage is incomplete")
    if any(len(ids) != 512 for ids in membership["training_record_ids"].values()):
        raise ValueError("training exposure differs from the frozen 512 records")
    t = study["training"]
    if t["microbatch_size"] * t["gradient_accumulation_steps"] != t["global_batch_size"] or (
        t["records_per_algorithm"] * t["epochs"] != t["global_batch_size"] * t["optimizer_updates"]
    ):
        raise ValueError("training batch/update exposure differs")
    return {
        "outcome": "PASS",
        "records": len(found),
        "training_records": 2048,
        "diagnostic_records": 108,
        "modality_projections": len(found) * 3,
        "maximum_input_tokens": dict(maxima),
        "semantic_task_split_isolation": True,
        "shared_memory_and_candidates": True,
        "drawing_text_semantic_parity": True,
        "no_future_images": True,
        "selected_goal_evaluations": len(contexts),
        "task_bindings": task_refs,
        "record_order_source": study["membership"],
        "gpu_calls": 0,
    }


def verify_candidate_stop(root, study, pool, progress):
    """Independently verify every candidate in each exhausted domain through PDDL.

    A single exhausted required domain proves the fixed panel cannot be admitted.
    This check deliberately makes no full validation claim about other domains.
    """
    require_pool_coverage(pool, study)
    missing = [
        d for d in study["final"]["domains"] if not any(c["eligible"] for c in pool["candidates"] if c["domain"] == d)
    ]
    if not missing:
        return {"outcome": "PASS", "missing_domains": [], "resource_stop_verified": False}
    exclusions, _ = retained_tasks(root, set(study["final"]["domains"]))
    checked, counts = [], Counter()
    selected = [c for c in pool["candidates"] if c["domain"] in missing]
    for i, candidate in enumerate(selected):
        domain = candidate["domain"]
        arguments = study["final"]["candidate_profiles"][domain]["arguments"]
        command = candidate.get("generator_command", [])
        if list(command[1 : 1 + len(arguments)]) != arguments or str(candidate["seed"]) not in command:
            raise ValueError("rejected candidate did not use the frozen generator arguments/seed")
        task = read_json(root / candidate["row"]["task_path"])
        semantic = task_semantics(task["domain_pddl"], task["problem_pddl"])
        reason = candidate["reason"]
        if reason == "retained_task_overlap":
            if semantic not in exclusions:
                raise ValueError("reported overlap is not present in retained source tasks")
        elif reason.startswith("exact_reference_failed:"):
            algorithm = reason.split(":")[1]
            try:
                exact_reference(root, candidate["row"], algorithm, study)
            except RuntimeError as error:
                if str(error) != reason:
                    raise ValueError("replayed resource failure differs") from error
            else:
                raise ValueError("reported failed exact reference succeeds on replay")
        else:
            raise ValueError(f"resource-stop evidence needs explicit verification for {reason}")
        checked.append(
            {"domain": domain, "seed": candidate["seed"], "reason": reason, "task_path": candidate["row"]["task_path"]}
        )
        counts[reason] += 1
        progress("verify:exhausted_domain", completed=i + 1, total=len(selected))
    return {
        "outcome": "VALID_STOP",
        "resource_stop_verified": True,
        "missing_domains": missing,
        "scope": "all frozen candidates in exhausted required domains; other domains not fully replay-verified",
        "verified_candidates": checked,
        "rejection_counts": dict(counts),
        "gpu_calls": 0,
    }
