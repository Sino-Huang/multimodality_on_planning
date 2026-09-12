"""Live annotated visual observations around the existing trusted family sessions."""

from __future__ import annotations

import gzip
import json
import random
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image

from .best_first_development import (
    BestFirstDevelopmentTask,
    BestFirstModelSession,
    exact_best_first_output,
    random_valid_best_first_output,
)
from .best_first_model_input import expand_compact_best_first_facts
from .bfws_issue59 import BFWSModelSession, exact_bfws_model_output, random_valid_bfws_model_output
from .bfws_model_input import bfws_text_policy_training_messages
from .modality_corpus_replay import canonical
from .modality_pages import PageRecipe, fact_blocks, paginate, project_messages, shared_state_page_cache
from .modality_view_preparation import frozen_processor, validate_process_state, write_json
from .pddl_state import GroundedAction, PDDLStateAuthority
from .planimation_render import PlanimationRenderRequest, canonical_supplied_actions, produce_planimation_render
from .scene_assets import load_scene_task, read_json, require_resolved_scene_coordinates
from .scene_profiles import require_grid_shape_icons
from .visual_bfs import VisualBFSSession


class VisualTaskViews:
    """Reuse collected states; render new accepted states via supplied localhost paths."""

    def __init__(self, root: Path, row: dict, view_manifest: str, output: Path, endpoint: str, *, read_only=False):
        self.root, self.row, self.output, self.endpoint = root, row, output, endpoint
        self.read_only = read_only
        self.manifest = read_json(root / view_manifest)
        self.catalog = read_json(root / self.manifest["scene_catalog"])
        self.states = list(self.catalog["states"])
        self.recipes = list(self.manifest["state_recipes"])
        self.dynamic_path = output / "views.json.gz"
        if self.dynamic_path.exists():
            retained = read_json(self.dynamic_path)
            if retained["source_manifest"] != view_manifest or retained["task_id"] != row["task_id"]:
                raise ValueError("live view task binding differs")
            self.states.extend(retained["states"])
            self.recipes.extend(retained["recipes"])
        self.source_manifest = view_manifest
        self.original_count = len(self.catalog["states"])
        self.indices = {self.key(s["atoms"], s["fluents"]): i for i, s in enumerate(self.states)}
        self.symbols = None
        self.symbol_states = {}
        self.cache = shared_state_page_cache(root)
        domain, problem, _ = load_scene_task(root, row)
        self.authority = PDDLStateAuthority.from_pddl(domain, problem)
        if self.manifest["task_id"] != row["task_id"] or canonical(self.authority.task_context()) != canonical(
            self.catalog["task_context"]
        ):
            raise ValueError("live view source task/context differs from authoritative PDDL")

    @staticmethod
    def key(atoms, fluents):
        return canonical([sorted(atoms), sorted(fluents)])

    def state(self, raw, algorithm):
        if algorithm == "bfs":
            return self.authority.canonical_state(tuple(raw["observation"]["state_atoms"]), ())
        if algorithm == "best_first_width":
            # The symbol-compact input is checked against the live request's state below.
            from .bfws_model_input import _group_atoms

            if self.symbols is None:
                self.symbols = {name: i for i, name in enumerate(raw["task_context"]["objects"])}
                self.symbol_states = {
                    canonical([_group_atoms(entry["atoms"], self.symbols), entry["fluents"]]): i
                    for i, entry in enumerate(self.states)
                }
            key = canonical([raw["observation"]["state"]["atoms"], raw["observation"]["state"]["fluents"]])
            if key not in self.symbol_states:
                raise ValueError("BFWS requested a state without accepted provenance")
            entry = self.states[self.symbol_states[key]]
            return self.authority.canonical_state(tuple(entry["atoms"]), tuple(entry["fluents"]))

        return self.authority.canonical_state(tuple(expand_compact_best_first_facts(raw["current"]["state_facts"])), ())

    def register(self, source, action):
        """Called only after the trusted runtime accepts the producing operation."""
        target = self.authority.apply(source, GroundedAction(action["name"], tuple(action["args"]))).target_state
        key = self.key(target.atoms, target.fluents)
        if key not in self.indices:
            if self.read_only:
                raise ValueError("replay lacks accepted state/scene provenance")
            index = len(self.states)
            self.indices[key] = index
            self.states.append(
                {
                    "index": index,
                    "atoms": list(target.atoms),
                    "fluents": list(target.fluents),
                    "parent": {
                        "state": self.indices[self.key(source.atoms, source.fluents)],
                        "action": f"({action['name']} {' '.join(action['args'])})".replace(" )", ")"),
                    },
                    "scene_path": None,
                }
            )
            self.recipes.append([])
            if self.symbols is not None:
                from .bfws_model_input import _group_atoms

                self.symbol_states[canonical([_group_atoms(list(target.atoms), self.symbols), list(target.fluents)])] = (
                    index
                )
        index = self.indices[key]
        if not self.states[index]["scene_path"]:
            self._render(index)
        return index

    def path(self, index):
        actions = []
        while self.states[index]["parent"] is not None:
            parent = self.states[index]["parent"]
            actions.append(parent["action"])
            index = parent["state"]
        return tuple(reversed(actions))

    def _render(self, index):
        if self.read_only:
            raise ValueError("replay cannot render missing scenes")
        actions = self.path(index)
        self.output.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self.output, prefix="render-") as temporary:
            domain_path = self.root / self.catalog["render_domain"]
            problem_path = (self.root / self.manifest["scene_catalog"]).parent / "problem.pddl"
            result = produce_planimation_render(
                PlanimationRenderRequest(
                    self.endpoint,
                    domain_path,
                    problem_path,
                    self.root / self.catalog["used_profile"],
                    actions,
                    Path(temporary),
                    30,
                    canvas_size=128,
                )
            )
            stages = read_json(result.trace_path)["visualStages"]
            if (
                len(result.frame_paths) != len(actions) + 1
                or stages[0]["stageName"].strip().lower() != "initial stage"
                or canonical_supplied_actions(tuple(s["stageName"] for s in stages[1:])) != actions
            ):
                raise ValueError("live rendering supplied Action Sequence differs")
            require_resolved_scene_coordinates(stages)
            if self.row["domain"] == "grid":
                require_grid_shape_icons(self.catalog["task_context"], stages)
            frame = self.output / f"state-{index:06d}.png"
            result.frame_paths[-1].replace(frame)
            vfg = self.output / f"state-{index:06d}.vfg.json.gz"
            with gzip.open(vfg, "wb") as stream:
                stream.write(result.trace_path.read_bytes())
            self.states[index].update(
                scene_path=str(frame.relative_to(self.root)),
                supplied_actions=list(actions),
                vfg=str(vfg.relative_to(self.root)),
            )
        blocks = fact_blocks(self.catalog["task_context"], self.states[index], self.manifest["source"])
        self.recipes[index] = json.loads(
            json.dumps(
                [
                    p.to_dict()
                    for p in paginate("current-state", blocks["current-state"], self.states[index]["scene_path"])
                ]
            )
        )

    def observe(self, raw, algorithm, *, modality="visual-state", pixels=True):
        state = self.state(raw, algorithm)
        index = self.indices[self.key(state.atoms, state.fluents)]
        entry = self.states[index]
        validate_process_state(raw, algorithm, entry)
        if not entry["scene_path"]:
            self._render(index)
        if not (self.root / entry["scene_path"]).is_file():
            raise ValueError("missing bound observation scene")
        semantic = fact_blocks(self.catalog["task_context"], entry, self.manifest["source"])
        expected = [p.to_dict() for p in paginate("current-state", semantic["current-state"], entry["scene_path"])]
        if self.recipes[index] != json.loads(json.dumps(expected)):
            raise ValueError("live state recipe does not expose complete current facts")
        pages = []
        bindings = []
        for role in ("task-context", "current-state", "goal"):
            recipes = self.recipes[index] if role == "current-state" else self.manifest["reusable_recipes"][role]
            for i, raw_page in enumerate(recipes):
                bindings.append([role, index if role == "current-state" else None, i])
                image = f"{role}/{index}/{i}"
                if pixels and modality != "text-state":
                    if role == "current-state":
                        image = self.cache.get(
                            self.row["task_id"] + ":" + str(self.output), index, PageRecipe(**raw_page)
                        )
                    else:
                        with Image.open(self.root / self.manifest["reusable_pages"][role][i]) as stored:
                            image = stored.convert("RGB")
                pages.append((role, image))
        messages = project_messages(raw, algorithm, modality, semantic, pages)
        count = frozen_processor().count(messages)
        if count + 384 > 32768:
            raise RuntimeError("VALID_STOP: live input exceeds the approved 32K context")
        return {
            "messages": messages,
            "images": [image for _, image in pages] if modality != "text-state" else [],
            "binding": {"state": index, "input_pages": bindings, "input_tokens": count},
        }

    def save(self):
        if not self.read_only:
            write_json(
                self.dynamic_path,
                {
                    "task_id": self.row["task_id"],
                    "source_manifest": self.source_manifest,
                    "states": self.states[self.original_count :],
                    "recipes": self.recipes[self.original_count :],
                },
            )


class VisualBFWSSession(BFWSModelSession):
    """Match the released teacher's explicit zero-size partition bookkeeping."""

    def next_request(self):
        request = super().next_request()
        if request is not None:
            first = next((c for c in request.observation["successor_candidates"] if not c["duplicate"]), None)
            if first is not None:
                partition = first["evaluation"]["partition"]
                if partition not in self.partition_tables:
                    # The expert ensures this table exists before recording its
                    # observation. An empty table adds no novelty or pruning facts.
                    self.partition_tables[partition] = set()
                    self._pending = None
                    request = super().next_request()
        return request


class VisualSession:
    """The family session remains authoritative; only its observation modality changes."""

    def __init__(self, root, row, algorithm, arm, seed, output, contract_id, *, views=None):
        self.row, self.algorithm, self.arm, self.seed, self.views = row, algorithm, arm, seed, views
        domain, problem, _ = load_scene_task(root, row)
        self.authority = PDDLStateAuthority.from_pddl(domain, problem)
        self.events = []
        self.random = random.Random(seed)
        cost = row["reference_costs"][algorithm]
        self.limit = 2 * cost["decisions"]
        self.pending: Any = None
        self.session: Any
        if algorithm.startswith("best_first_add"):
            task = BestFirstDevelopmentTask(
                row["task_id"],
                row["task_id"],
                row["domain"],
                row["difficulty"],
                root / next(iter(row["trace_paths"].values())),
                cost["decisions"],
                cost["expansions"],
                algorithm,
                75,
            )
            self.session = BestFirstModelSession(authority=self.authority, task=task, arm=arm, seed=seed)
        elif algorithm == "best_first_width":

            def counter(raw):
                p = frozen_processor().processor
                return len(
                    p.tokenizer.apply_chat_template(
                        bfws_text_policy_training_messages(raw), tokenize=True, add_generation_prompt=True
                    )
                )

            self.session = VisualBFWSSession(
                authority=self.authority,
                instance_id=row["task_id"],
                arm="exact_bfws" if arm == "exact_reference" else arm,
                seed=seed,
                max_model_calls=self.limit,
                max_expansions=cost["expansions"],
                accepted_delta_limit=16,
                max_input_bytes=3840,
                max_input_tokens=7808,
                input_token_counter=counter,
            )
        else:
            self.session = VisualBFSSession(self.authority, self.limit, cost["expansions"])

    def next_request(self):
        self.pending = self.session.next_request()
        return self.pending

    def reference_output(self):
        raw = self.pending.model_input
        if self.algorithm.startswith("best_first_add"):
            return (
                exact_best_first_output(raw)
                if self.arm == "exact_reference"
                else random_valid_best_first_output(raw, self.random)
            )
        if self.algorithm == "best_first_width":
            obs = self.pending.observation
            return (
                exact_bfws_model_output(obs)
                if self.arm == "exact_reference"
                else random_valid_bfws_model_output(obs, self.random)
            )
        candidates = [c for c in raw["search_memory"]["successor_candidates"] if not c["visited"]]
        source = raw["observation"]["state_id"]
        if candidates:
            candidate = candidates[0] if self.arm == "exact_reference" else self.random.choice(candidates)
            frontier = self.session.context.memory.frontier
            retire = source in frontier
            operation = {
                "source_state_id": source,
                "action": candidate["grounded_action"],
                "frontier_intent": {"retire_source": retire, "target_position": len(frontier) - int(retire)},
                "visit_target": True,
                "evaluate_target": False,
            }
        else:
            operation = {"operation_type": "retire_frontier", "state_id": source}
        return canonical({"canonical_rationale": "reference", "runtime_result": None, "typed_operation": operation})

    def submit(self, output, binding=None):
        raw = dict(self.pending.model_input)
        source = self.views.state(raw, self.algorithm) if self.views else None
        before = self.invalid_count()
        self.session.submit_output(output)
        accepted = self.invalid_count() == before
        successor = None
        if accepted and self.views:
            parsed = json.loads(output)
            operation = parsed if self.algorithm.startswith("best_first_add") else parsed["typed_operation"]
            if "action" in operation:
                successor = self.views.register(source, operation["action"])
        self.events.append(
            {
                "index": len(self.events),
                "input": raw,
                "raw_output": output,
                "accepted": accepted,
                "view": binding,
                "successor_state": successor,
            }
        )
        self.pending = None

    def invalid_count(self):
        if self.algorithm.startswith("best_first_add"):
            return self.session.controller.invalid_operation_count
        return self.session.invalid_operation_count

    def result(self):
        if self.algorithm != "bfs":
            return {**self.session.result(), "model_call_limit": self.limit}
        success = self.session.termination_reason == "goal_reached" and self.invalid_count() == 0
        return {
            "invariant_valid_success": success,
            "goal_reached": self.session.exited_through_goal_check,
            "algorithm_invariants_hold": self.invalid_count() == 0,
            "decision_count": len(self.events),
            "expansion_count": len(self.session.expansions),
            "invalid_operation_count": self.invalid_count(),
            "invalid_operation_rate": self.invalid_count() / max(1, len(self.events)),
            "model_call_limit": self.limit,
            "termination_reason": self.session.termination_reason,
        }


def replay_visual_episode(root, row, report, views=None):
    original_read_only = views.read_only if views is not None else False
    if views is not None:
        views.read_only = True
    try:
        session = VisualSession(
            root,
            row,
            report["algorithm"],
            report["arm"],
            report["seed"],
            root / report["output"],
            report["contract_id"],
            views=views,
        )
        for event in report["events"]:
            request = session.next_request()
            if request is None or dict(request.model_input) != event["input"]:
                raise ValueError("visual episode replay input differs")
            binding = (
                views.observe(
                    dict(request.model_input),
                    report["algorithm"],
                    modality=report.get("modality", "visual-state"),
                    pixels=False,
                )["binding"]
                if views
                else None
            )
            if binding != event["view"]:
                raise ValueError("visual episode page binding differs")
            session.submit(event["raw_output"], binding)
            if session.events[-1] != event:
                raise ValueError("visual episode replay operation/result differs")
        if session.next_request() is not None or session.result() != report["result"]:
            raise ValueError("visual episode replay completion differs")
        return session.result()
    finally:
        if views is not None:
            views.read_only = original_read_only
