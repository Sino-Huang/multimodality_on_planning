"""Replay-bound new-task state catalogs for expanded panel views."""

from .pddl_state import GroundedAction, PDDLStateAuthority
from .scene_assets import read_json
from .visual_episode import VisualSession, VisualTaskViews


class ReferenceStateCatalog:
    """Register state images only after their producing operation is accepted."""

    state = VisualTaskViews.state

    def __init__(self, authority):
        self.authority = authority
        self.states = [
            dict(
                index=0,
                atoms=list(authority.initial_state.atoms),
                fluents=list(authority.initial_state.fluents),
                parent=None,
            )
        ]
        self.indices = {authority.initial_state.state_id: 0}
        self.symbols = None
        self.symbol_states = {}

    def register(self, source, action):
        target = self.authority.apply(source, GroundedAction(action["name"], tuple(action["args"]))).target_state
        if target.state_id not in self.indices:
            index = len(self.states)
            self.indices[target.state_id] = index
            self.states.append(
                dict(
                    index=index,
                    atoms=list(target.atoms),
                    fluents=list(target.fluents),
                    parent=dict(
                        state=self.indices[source.state_id],
                        action=f"({action['name']} {' '.join(action['args'])})".replace(" )", ")"),
                    ),
                )
            )
            self.symbols = None
        return self.indices[target.state_id]


def reference_catalog(root, row, reference_paths, study_id):
    task = read_json(root / row["task_path"])
    authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])
    views = ReferenceStateCatalog(authority)
    decisions = []
    for algorithm, path in reference_paths.items():
        reference = read_json(root / path)
        session = VisualSession(root, row, algorithm, "exact_reference", 17, root, study_id, views=views)
        for index, event in enumerate(reference["events"]):
            request = session.next_request()
            if request is None or dict(request.model_input) != event["input"]:
                raise ValueError("reference input differs during independent state replay")
            source = views.state(dict(request.model_input), algorithm)
            decisions.append(dict(algorithm=algorithm, index=index, state=views.indices[source.state_id]))
            session.submit(event["raw_output"])
            if not session.events[-1]["accepted"]:
                raise ValueError("retained exact reference operation rejected")
        if session.next_request() is not None or session.result() != reference["result"]:
            raise ValueError("reference result differs during independent state replay")
    return dict(
        task_context=authority.task_context(),
        states=views.states,
        decisions=decisions,
        scope="all source/current and accepted-successor states in frozen exact references; not full reachability closure",
    )


class ExpandedTaskViews(VisualTaskViews):
    """Use retained reference images and materialize new accepted states on demand."""

    def __init__(self, root, task, output, endpoint, *, read_only=False):
        import copy
        from .modality_corpus_replay import canonical
        from .scene_only_views import SceneOnlyViews

        self.root, self.row, self.output, self.endpoint = root, task["row"], output, endpoint
        self.read_only = read_only
        native = copy.deepcopy(task["native_views"])
        self.source_manifest = native["source_manifest"]
        self.manifest = read_json(root / self.source_manifest)
        self.catalog = read_json(root / self.manifest["scene_catalog"])
        self.states = list(self.catalog["states"])
        self.original_count = len(self.states)
        self.dynamic_path = output / "views.json.gz"
        if self.dynamic_path.exists():
            retained = read_json(self.dynamic_path)
            if retained["source_manifest"] != self.source_manifest or retained["task_id"] != self.row["task_id"]:
                raise ValueError("retained expanded live-view binding differs")
            self.states.extend(retained["states"])
        self.recipes = [[] for _ in self.states]
        self.indices = {self.key(s["atoms"], s["fluents"]): i for i, s in enumerate(self.states)}
        self.symbols, self.symbol_states = None, {}
        source = read_json(root / self.row["task_path"])
        self.authority = PDDLStateAuthority.from_pddl(source["domain_pddl"], source["problem_pddl"])
        if canonical(self.catalog["task_context"]) != canonical(self.authority.task_context()):
            raise ValueError("expanded live view task differs from source PDDL")
        replayed = []
        for entry in self.states:
            parent = entry["parent"]
            if parent is None:
                state = self.authority.initial_state
            else:
                words = parent["action"].strip("()").split()
                state = self.authority.apply(
                    replayed[parent["state"]], GroundedAction(words[0], tuple(words[1:]))
                ).target_state
            if list(state.atoms) != entry["atoms"] or list(state.fluents) != entry["fluents"]:
                raise ValueError("stored expanded view state does not replay from its parent")
            replayed.append(state)
        self.scene_views = SceneOnlyViews(root, {self.row["task_id"]: native})
        for state in self.states[self.original_count :]:
            self._bind_native(state["index"])

    def _bind_native(self, index):
        state = self.states[index]
        native = self.scene_views.tasks[self.row["task_id"]]
        native["scenes"][str(index)] = state["scene_path"]
        native["scene_bindings"][str(index)] = {"vfg": state["vfg"], "stage": len(self.path(index))}

    def _render(self, index):
        import json
        import tempfile
        from scripts.planimation_phase1_frames import render_vfg_to_local_png_frames

        super()._render(index)
        state = self.states[index]
        payload = read_json(self.root / state["vfg"])
        stage = len(self.path(index))
        with tempfile.TemporaryDirectory(dir=self.output, prefix="unlabelled-") as directory:
            from pathlib import Path

            folder = Path(directory)
            render_vfg_to_local_png_frames(
                json.dumps(payload).encode(),
                folder,
                stage,
                stage,
                canvas_size=128,
                draw_labels=False,
                object_names=frozenset(self.authority.objects),
            )
            (folder / "frame_000.png").replace(self.root / state["scene_path"])
        self._bind_native(index)
