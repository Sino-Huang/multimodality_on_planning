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
        session = VisualSession(
            root, row, algorithm, "exact_reference", 17, root, study_id, views=views, input_token_counter=lambda raw: 0
        )
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
