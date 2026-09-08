"""Qualification and materialization of the readable-page successor contract."""

from __future__ import annotations

import gzip
import io
import json
import time
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image

from .modality_pages import (
    CACHE_BYTES,
    CONTRACT_ID,
    FONT_SIZE,
    PAGE_SIZE,
    ROLES,
    PageRecipe,
    StatePageCache,
    compose_page,
    fact_blocks,
    paginate,
    project_messages,
    validate_pages,
)
from .pddl_state import GroundedAction, PDDLStateAuthority
from .scene_assets import load_scene_task, read_json
from .source_goal import evaluate_goal, source_task

CONTEXTS = (8192, 16384, 32768)
OUTPUT_TOKENS = 384
EXPECTED = {"tasks": 241, "states": 51208, "decisions": 78230}
MODEL = "Qwen/Qwen3-VL-8B-Instruct"
REVISION = "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b"
CONTRACT = {
    "contract_id": CONTRACT_ID,
    "page_size": list(PAGE_SIZE),
    "font": "DejaVuSans.ttf",
    "font_size": FONT_SIZE,
    "roles": list(ROLES),
    "state_cache_bytes": CACHE_BYTES,
    "contexts": list(CONTEXTS),
    "output_tokens": OUTPUT_TOKENS,
    "model_id": MODEL,
    "model_revision": REVISION,
    "scene_report": "outputs/modality_phase/issue72-scenes128-v1/collect-004/report.json",
    "expected": EXPECTED,
}


def write_json(path: Path, value: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    if path.suffix == ".gz":
        with gzip.open(temporary, "wt") as stream:
            json.dump(value, stream, separators=(",", ":"))
    else:
        temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def recommend_context(maximum: int) -> int | None:
    return next((size for size in CONTEXTS if maximum + OUTPUT_TOKENS <= size), None)


def require_approval(approval: dict, qualification: dict, output: Path, contract: dict = CONTRACT) -> None:
    if qualification.get("contract") != contract or not qualification.get("complete_selected_coverage"):
        raise ValueError("approval requires complete qualification under this exact view contract")
    if qualification.get("outcome") != "PASS" or not qualification.get("processor_qualified"):
        raise ValueError("qualification did not pass processor/context checks")
    if qualification.get("counts") != contract["expected"] or qualification.get("recommended_context") not in CONTEXTS:
        raise ValueError("qualification coverage or context is incomplete")
    expected = {
        "contract_id": contract["contract_id"],
        "qualification_attempt": qualification["attempt_id"],
        "materialization_output": str(output.resolve()),
        "approved_context": qualification["recommended_context"],
        "readability_approved": True,
        "preview_index": qualification["preview_index"],
    }
    if any(approval.get(k) != v for k, v in expected.items()) or not approval.get("approved_by"):
        raise ValueError("missing or mismatched human readability/context/materialization authorization")


def validate_scene_selection(root: Path, panel: list[dict], report: dict) -> dict[str, dict]:
    if (
        report.get("outcome") != "PASS"
        or not report.get("scene_asset_completion")
        or not report.get("complete_selected_coverage")
        or not report.get("permission", {}).get("start_permitted")
    ):
        raise ValueError("complete authorized scene collection is required")
    if (
        report.get("permission", {}).get("binding") != report.get("binding")
        or report.get("permission", {}).get("outcome") != "PASS"
    ):
        raise ValueError("scene authorization binding differs")
    results = {r["task_id"]: r for r in report["results"]}
    if len(results) != len(report["results"]) or set(results) != {r["task_id"] for r in panel}:
        raise ValueError("scene selection differs from the unchanged panel")
    for row in panel:
        result = results[row["task_id"]]
        if result["outcome"] != "PASS" or not result["complete_state_coverage"]:
            raise ValueError("partial scene task cannot authorize views")
        if not (root / result["catalog"]).is_file():
            raise ValueError("referenced scene catalog is absent; retain collect-003 and collect-004")
    return results


def process_rows(root: Path, row: dict):
    """Read frozen family-builder projections; never infer memory from scene metadata."""
    task_id = row["task_id"]
    if task_id.startswith("astar-pair-"):
        base = root / "data/best_first_paired_phase_v3/corpus-release-v3"
        paths = sorted((base / "corpus/process" / row["split"] / row["domain"]).glob(f"*/{task_id}/*.jsonl.gz"))
    elif task_id.startswith("bfs/"):
        paths = [root / "data/bfs_pilot_v6/process-release/corpus/process.jsonl"]
    else:
        base = root / "data/bfws_phase_v1/corpus-release"
        instance = task_id.split("/", 1)[1]
        paths = sorted((base / "corpus/process" / row["split"] / row["domain"]).glob(f"*/{instance}.jsonl"))
    if not paths:
        raise ValueError(f"missing family-builder process inputs: {task_id}")
    for path in paths:
        with gzip.open(path, "rt") if path.suffix == ".gz" else path.open() as stream:
            for line in stream:
                record = json.loads(line)
                identity = record.get("pair_id") or f"{record['algorithm']}/{record['instance_id']}"
                if identity == task_id:
                    if record["split"] != row["split"]:
                        raise ValueError("source process split differs from selected task")
                    yield record, str(path.relative_to(root))


def validate_process_state(raw: dict, algorithm: str, state: dict) -> None:
    """Bind a retained family input to the observed catalog state before projecting."""
    if algorithm.startswith("best_first_add"):
        from .best_first_model_input import expand_compact_best_first_facts

        atoms = expand_compact_best_first_facts(raw["current"]["state_facts"])
        fluents = []
    elif algorithm == "bfs":
        atoms, fluents = raw["observation"]["state_atoms"], []
    elif algorithm == "best_first_width":
        from .bfws_model_input import _group_atoms

        symbols = {obj: i for i, obj in enumerate(raw["task_context"]["objects"])}
        if _group_atoms(state["atoms"], symbols) != raw["observation"]["state"]["atoms"]:
            raise ValueError("BFWS process input has the wrong observed state")
        atoms, fluents = state["atoms"], raw["observation"]["state"]["fluents"]
    else:
        raise ValueError("unsupported process input family")
    if sorted(atoms) != sorted(state["atoms"]) or sorted(fluents) != sorted(state["fluents"]):
        raise ValueError("process input has the wrong observed state")


class FrozenPageProcessor:
    """Exact chat token counts for fixed-size pages; no model weights or GPU calls.

    Qwen expands each image marker to grid.prod()/merge_size**2 special tokens.
    Measure that grid with the actual processor, then count complete templated text
    at every decision. The first complete input is cross-checked by __call__.
    """

    def __init__(self):
        from transformers import AutoProcessor

        self.processor = AutoProcessor.from_pretrained(MODEL, revision=REVISION, local_files_only=True)
        if type(self.processor).__name__ != "Qwen3VLProcessor":
            raise ValueError("frozen processor class differs")
        page = Image.new("RGB", PAGE_SIZE, "white")
        processed = self.processor.image_processor(images=[page], return_tensors="pt")
        grid = processed["image_grid_thw"][0]
        self.grid = [int(n) for n in grid]
        self.image_tokens = int(grid.prod()) // self.processor.image_processor.merge_size**2
        self.cross_checked = False

    def count(self, messages):
        processor = self.processor
        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        count = len(processor.tokenizer(text)["input_ids"])
        count += text.count(processor.image_token) * (self.image_tokens - 1)
        return count

    def verify_complete(self, messages, images):
        text = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        actual = self.processor(text=[text], images=images or None, return_tensors="pt")
        if len(actual["input_ids"][0]) != self.count(messages):
            raise ValueError("complete processor input disagrees with measured image-grid token expansion")
        self.cross_checked = True

    def preview(self, image: Image.Image) -> Image.Image:
        """Undo patch packing/normalization to retain the actual processed pixels."""
        import numpy as np

        ip = self.processor.image_processor
        batch = ip(images=[image], return_tensors="pt")
        t, h, w = map(int, batch["image_grid_thw"][0])
        merge, patch, temporal = ip.merge_size, ip.patch_size, ip.temporal_patch_size
        pixels = (
            batch["pixel_values"]
            .cpu()
            .numpy()
            .reshape(t, h // merge, w // merge, merge, merge, 3, temporal, patch, patch)
        )
        pixels = pixels.transpose(0, 6, 5, 1, 3, 7, 2, 4, 8).reshape(t * temporal, 3, h * patch, w * patch)[0]
        pixels = pixels.transpose(1, 2, 0)
        pixels = (pixels * np.asarray(ip.image_std) + np.asarray(ip.image_mean)) * 255
        return Image.fromarray(np.clip(np.rint(pixels), 0, 255).astype("uint8"))


@lru_cache(maxsize=1)
def frozen_processor():
    return FrozenPageProcessor()


def _state_goal_checks(authority, catalog, source):
    states = []
    for record in catalog["states"]:
        parent = record["parent"]
        if parent is None:
            state = authority.initial_state
        else:
            parts = parent["action"][1:-1].split()
            state = authority.apply(states[parent["state"]], GroundedAction(parts[0], tuple(parts[1:]))).target_state
        if list(state.atoms) != record["atoms"] or list(state.fluents) != record["fluents"]:
            raise ValueError("goal checker state does not match collected state")
        facts = set(state.atoms) | set(authority.static_initial_facts)
        if evaluate_goal(source["source_goal"], facts, source) != authority.is_goal(state):
            raise ValueError(f"source goal disagrees with trusted checker at state {record['index']}")
        states.append(state)
        authority.discard_transient_search_caches()


def prepare_task(
    root: Path, row: dict, scene_result: dict, mode: str, output: Path | None, contract: dict = CONTRACT
) -> dict:
    started = time.monotonic()
    catalog = read_json(root / scene_result["catalog"])
    if (
        catalog["split"] != row["split"]
        or catalog["source_trace_paths"] != row["trace_paths"]
        or catalog["reference_costs"] != row["reference_costs"]
    ):
        raise ValueError("catalog task/split/source bindings differ from selected panel")
    domain, problem, _ = load_scene_task(root, row)
    source = source_task(domain, problem)
    if Counter(d["algorithm"] for d in catalog["decisions"]) != Counter(
        {algorithm: cost["decisions"] for algorithm, cost in row["reference_costs"].items()}
    ):
        raise ValueError("per-family decision coverage differs from exact reference costs")
    if mode not in ("dry-run", "measure"):
        _state_goal_checks(PDDLStateAuthority.from_pddl(domain, problem), catalog, source)
    blocks = fact_blocks(catalog["task_context"], catalog["states"][0], source)
    reusable = {role: paginate(role, blocks[role]) for role in ("task-context", "goal")}
    recipes = []
    page_counts = Counter()
    for index, state in enumerate(catalog["states"]):
        if state["index"] != index or not state.get("scene_path") or not (root / state["scene_path"]).is_file():
            raise ValueError("incomplete state/scene coverage")
        state_blocks = fact_blocks(catalog["task_context"], state, source)["current-state"]
        pages = paginate("current-state", state_blocks, state["scene_path"])
        recipes.append(pages)
        page_counts[len(pages)] += 1
    bindings = []
    seen = set()
    for decision in catalog["decisions"]:
        key = (decision["algorithm"], decision["index"])
        if key in seen or not 0 <= decision["state"] < len(recipes):
            raise ValueError("duplicate decision or missing source state")
        seen.add(key)
        for state_index in [decision.get("successor"), *decision.get("candidate_states", [])]:
            if state_index is not None and not 0 <= state_index < len(recipes):
                raise ValueError("missing result or candidate recipe")
        bindings.append(
            {
                **decision,
                "input_pages": [
                    [role, decision["state"] if role == "current-state" else None, i]
                    for role in ROLES
                    for i in range(len(recipes[decision["state"]]) if role == "current-state" else len(reusable[role]))
                ],
            }
        )
    result = {
        "task_id": row["task_id"],
        "domain": row["domain"],
        "split": row["split"],
        "catalog": scene_result["catalog"],
        "states": len(recipes),
        "decisions": len(bindings),
        "context_pages": len(reusable["task-context"]),
        "goal_pages": len(reusable["goal"]),
        "state_page_distribution": dict(page_counts),
        "source_goal": source["source_goal"],
        "max_state_pages": max(page_counts),
        "goal_checker_states": len(recipes) if mode not in ("dry-run", "measure") else 0,
    }
    if mode == "dry-run":
        result["elapsed_seconds"] = time.monotonic() - started
        return result
    if output is None:
        raise ValueError("qualification/materialization needs an output location")
    if mode in ("qualify", "measure"):
        processor = frozen_processor()
        cache = StatePageCache(root)
        tokens = {modality: Counter() for modality in ("text-state", "visual-state", "multimodal-state")}
        decision_map = {(d["algorithm"], d["index"]): d for d in bindings}
        qualified = set()
        measurements = []
        for record, source_path in process_rows(root, row):
            index = record.get("record_index", record.get("trace_record_index"))
            key = (record["algorithm"], index)
            if key not in decision_map or key in qualified:
                raise ValueError("family process input differs from decision coverage")
            decision = decision_map[key]
            state_index = decision["state"]
            validate_process_state(record["input"], record["algorithm"], catalog["states"][state_index])
            semantic = fact_blocks(catalog["task_context"], catalog["states"][state_index], source)
            all_pages = [*reusable["task-context"], *recipes[state_index], *reusable["goal"]]
            # Paths are placeholders in the chat template; dimensions were measured above.
            images = [(page.role, "annotation-page.png") for page in all_pages]
            measured = {}
            for modality in tokens:
                messages = project_messages(record["input"], record["algorithm"], modality, semantic, images)
                count = processor.count(messages)
                tokens[modality][count] += 1
                measured[modality] = count
                if modality == "multimodal-state" and not processor.cross_checked:
                    live_images = (
                        [Image.new("RGB", PAGE_SIZE, "white") for _ in all_pages]
                        if mode == "measure"
                        else [
                            (
                                cache.get(row["task_id"], state_index, p)
                                if p.role == "current-state"
                                else compose_page(p, root)
                            )
                            for p in all_pages
                        ]
                    )
                    processor.verify_complete(messages, live_images)
                    for image in live_images:
                        image.close()
            qualified.add(key)
            measurements.append(
                {
                    "algorithm": key[0],
                    "index": index,
                    "state": state_index,
                    "input_pages": decision["input_pages"],
                    "input_tokens": measured,
                    "source_process_path": source_path,
                }
            )
        if qualified != seen:
            raise ValueError("partial family model-input coverage cannot pass")
        measurement_path = output / "decision-measurements.json.gz"
        write_json(measurement_path, measurements)
        result["decision_measurements"] = str(measurement_path.relative_to(root))
        result.update(
            token_distributions={k: dict(v) for k, v in tokens.items()},
            processor_grid=processor.grid,
            image_tokens_per_page=processor.image_tokens,
            processor_cross_checked=processor.cross_checked,
            maximum_input_tokens=max(max(v) for v in tokens.values()),
        )
        if mode == "measure":
            result["elapsed_seconds"] = time.monotonic() - started
            return result
        # Every task's densest observation includes all goal forms and every domain.
        dense = max(
            range(len(recipes)),
            key=lambda i: (len(recipes[i]), sum(len(f["text"]) for p in recipes[i] for f in p.fragments)),
        )
        previews, sizes, composition = [], [], []
        for page in [*reusable["task-context"], *recipes[dense], *reusable["goal"]]:
            begin = time.monotonic()
            image = compose_page(page, root)
            composition.append(time.monotonic() - begin)
            encoded = io.BytesIO()
            image.save(encoded, format="PNG")
            sizes.append(len(encoded.getvalue()))
            path = output / "previews" / f"{page.role}-{page.index:04d}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(encoded.getvalue())
            processed_path = path.with_name(path.stem + "-processed.png")
            processor.preview(image).save(processed_path)
            image.close()
            previews.append(
                {
                    "role": page.role,
                    "page": page.index,
                    "state": dense if page.role == "current-state" else None,
                    "input": str(path),
                    "processed": str(processed_path),
                }
            )
        result.update(
            token_distributions={k: dict(v) for k, v in tokens.items()},
            processor_grid=processor.grid,
            image_tokens_per_page=processor.image_tokens,
            processor_cross_checked=processor.cross_checked,
            previews=previews,
            preview_png_bytes=sizes,
            composition_seconds=composition,
            maximum_input_tokens=max(max(v) for v in tokens.values()),
        )
    elif mode == "materialize":
        reusable_paths = {}
        for role, pages in reusable.items():
            reusable_paths[role] = []
            for page in pages:
                path = output / f"{role}-{page.index:04d}.png"
                path.parent.mkdir(parents=True, exist_ok=True)
                compose_page(page, root).save(path)
                reusable_paths[role].append(str(path.relative_to(root)))
        manifest = {
            "contract": contract,
            "task_id": row["task_id"],
            "split": row["split"],
            "scene_catalog": scene_result["catalog"],
            "source": source,
            "normalized_goal_execution_metadata": catalog["canonical_goal"],
            "task_context": catalog["task_context"],
            "reference_costs": row["reference_costs"],
            "source_trace_paths": row["trace_paths"],
            "reusable_pages": reusable_paths,
            "reusable_recipes": {role: [p.to_dict() for p in pages] for role, pages in reusable.items()},
            "state_recipes": [[p.to_dict() for p in pages] for pages in recipes],
            "decisions": bindings,
            "complete": True,
        }
        path = output / "manifest.json.gz"
        write_json(path, manifest)
        result["manifest"] = str(path.relative_to(root))
        result["asset_bytes"] = sum(p.stat().st_size for p in output.iterdir() if p.is_file())
    result["elapsed_seconds"] = time.monotonic() - started
    return result


def check_task(root: Path, result: dict, row: dict, contract: dict = CONTRACT) -> dict:
    manifest = read_json(root / result["manifest"])
    if (
        manifest.get("contract") != contract
        or not manifest.get("complete")
        or manifest["task_id"] != row["task_id"]
        or manifest["split"] != row["split"]
    ):
        raise ValueError("partial or mismatched task manifest")
    catalog = read_json(root / manifest["scene_catalog"])
    if (
        catalog["task_id"] != row["task_id"]
        or manifest["normalized_goal_execution_metadata"] != catalog["canonical_goal"]
    ):
        raise ValueError("task identity or normalized execution goal differs")
    domain, problem, _ = load_scene_task(root, row)
    source = source_task(domain, problem)
    if (
        source != manifest["source"]
        or manifest["task_context"] != catalog["task_context"]
        or manifest["source_trace_paths"] != row["trace_paths"]
        or manifest["reference_costs"] != row["reference_costs"]
    ):
        raise ValueError("manifest source-goal/task/split binding differs")
    _state_goal_checks(PDDLStateAuthority.from_pddl(domain, problem), catalog, source)
    if len(manifest["state_recipes"]) != len(catalog["states"]) or len(manifest["decisions"]) != len(
        catalog["decisions"]
    ):
        raise ValueError("partial manifest coverage")
    for state, raw_pages in zip(catalog["states"], manifest["state_recipes"], strict=True):
        blocks = fact_blocks(catalog["task_context"], state, manifest["source"])
        for role in ROLES:
            pages = tuple(
                PageRecipe(**p) for p in (raw_pages if role == "current-state" else manifest["reusable_recipes"][role])
            )
            validate_pages(blocks[role], pages)
            if pages != paginate(role, blocks[role], state["scene_path"] if role == "current-state" else None):
                # JSON loads lists for fragments: compare the serialized recipe representation.
                if json.dumps([p.to_dict() for p in pages], sort_keys=True) != json.dumps(
                    [
                        p.to_dict()
                        for p in paginate(role, blocks[role], state["scene_path"] if role == "current-state" else None)
                    ],
                    sort_keys=True,
                ):
                    raise ValueError("drawing recipe differs from qualified layout")
    for decision, original in zip(manifest["decisions"], catalog["decisions"], strict=True):
        if {k: v for k, v in decision.items() if k != "input_pages"} != original:
            raise ValueError("decision source/successor binding changed")
        expected = [
            [role, decision["state"] if role == "current-state" else None, i]
            for role in ROLES
            for i in range(
                len(manifest["state_recipes"][decision["state"]])
                if role == "current-state"
                else len(manifest["reusable_recipes"][role])
            )
        ]
        if decision["input_pages"] != expected:
            raise ValueError("incomplete pages or future-image leakage")
    for paths in manifest["reusable_pages"].values():
        for path in paths:
            with Image.open(root / path) as image:
                if image.size != PAGE_SIZE:
                    raise ValueError("reusable image has wrong dimensions")
    return {"task_id": row["task_id"], "states": len(catalog["states"]), "decisions": len(catalog["decisions"])}


def reuse_task(root: Path, result: dict, row: dict, contract: dict = CONTRACT) -> dict:
    check_task(root, result, row, contract)
    return result
