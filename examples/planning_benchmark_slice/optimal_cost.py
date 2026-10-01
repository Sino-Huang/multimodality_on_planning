"""Optimal cost-to-go h* with Fast Downward A*(LM-cut) (#149 §5; shared with #158).

Fast Downward is the ``up_fast_downward`` manylinux wheel (GPL-3.0), called as a subprocess
through its ``fast-downward.py`` driver; it is not vendored or imported. Every returned plan is
replayed through ``PDDLStateAuthority`` from the queried state and must reach the goal, so h* is the
verified length of an optimal plan (LM-cut is admissible, A* without reopening limits is optimal).
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from .expanded_candidates import pddl_facts, replace_initial
from .pddl_state import CanonicalState, GroundedAction, PDDLStateAuthority

SEARCH = "astar(lmcut())"
SEARCH_TIME_LIMIT = 600
UNSOLVABLE_EXIT_CODES = (10, 11, 12)  # FD: translator / search proved unsolvable, or no plan from incomplete search
TIMEOUT_EXIT_CODES = (23,)  # FD: search out of time


def fast_downward_driver() -> Path:
    spec = importlib.util.find_spec("up_fast_downward")
    if spec is None or not spec.submodule_search_locations:
        raise RuntimeError("up_fast_downward is not installed (pip install up_fast_downward==0.5.2)")
    driver = Path(next(iter(spec.submodule_search_locations))) / "downward" / "fast-downward.py"
    if not driver.is_file():
        raise RuntimeError(f"Fast Downward driver missing: {driver}")
    return driver


def state_problem(problem_pddl: str, authority: PDDLStateAuthority, state: CanonicalState) -> str:
    """The task problem with ``:init`` = static initial facts + the state's atoms."""

    if state.fluents:
        raise ValueError("h* labels support propositional states only")
    return replace_initial(problem_pddl, pddl_facts([*authority.static_initial_facts, *state.atoms]))


def _plan_actions(text: str) -> list[GroundedAction]:
    actions = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        name, *args = line.strip("()").split()
        actions.append(GroundedAction(name, tuple(args)))
    return actions

def state_authority(domain_pddl: str, problem: str, state: CanonicalState) -> PDDLStateAuthority:
    """A transition authority whose initial state is ``state`` (checked atom for atom)."""

    rooted = PDDLStateAuthority.from_pddl(domain_pddl, problem)
    if tuple(rooted.initial_state.atoms) != tuple(state.atoms):
        raise ValueError("state-rooted problem does not reproduce the state's atoms")
    return rooted



def optimal_cost(
    domain_pddl: str,
    problem_pddl: str,
    authority: PDDLStateAuthority,
    state: CanonicalState,
    *,
    time_limit: int = SEARCH_TIME_LIMIT,
) -> dict:
    """h* of ``state``: {"status": "solved"|"dead_end"|"timeout", "hstar", "plan", "seconds"}.

    ``state`` may come from a stored catalog (atoms only); the plan is verified on a fresh authority
    rooted at it (``state_authority``), so it need not be registered with ``authority``.
    """

    problem = state_problem(problem_pddl, authority, state)
    rooted = state_authority(domain_pddl, problem, state)
    if rooted.is_goal(rooted.initial_state):
        return {"status": "solved", "hstar": 0, "plan": [], "seconds": 0.0}
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="fd-hstar-") as directory:
        folder = Path(directory)
        (folder / "domain.pddl").write_text(domain_pddl)
        (folder / "problem.pddl").write_text(problem)
        completed = subprocess.run(
            [
                sys.executable,
                str(fast_downward_driver()),
                "--plan-file",
                "plan",
                "--search-time-limit",
                str(time_limit),
                "domain.pddl",
                "problem.pddl",
                "--search",
                SEARCH,
            ],
            cwd=folder,
            capture_output=True,
            text=True,
            check=False,
        )
        seconds = time.monotonic() - started
        if completed.returncode in UNSOLVABLE_EXIT_CODES:
            return {"status": "dead_end", "hstar": None, "plan": None, "seconds": seconds}
        if completed.returncode in TIMEOUT_EXIT_CODES:
            return {"status": "timeout", "hstar": None, "plan": None, "seconds": seconds}
        if completed.returncode != 0:
            raise RuntimeError(f"Fast Downward failed ({completed.returncode}): {completed.stdout[-2000:]}")
        actions = _plan_actions((folder / "plan").read_text())
    cursor = rooted.initial_state
    for action in actions:
        if action not in rooted.applicable_actions(cursor):
            raise ValueError(f"Fast Downward plan step is not applicable: {action.serialize()}")
        cursor = rooted.apply(cursor, action).target_state
    if not rooted.is_goal(cursor):
        raise ValueError("Fast Downward plan does not reach the goal")
    return {"status": "solved", "hstar": len(actions), "plan": [a.serialize() for a in actions], "seconds": seconds}


def blind_distance(authority: PDDLStateAuthority, state: CanonicalState, *, state_limit: int) -> int | None:
    """Breadth-first goal distance (None when the limit is hit or no goal is reachable)."""

    from collections import deque

    if authority.is_goal(state):
        return 0
    seen = {state.state_id}
    queue = deque([(state, 0)])
    while queue:
        current, depth = queue.popleft()
        for action in authority.applicable_actions(current):
            target = authority.apply(current, action).target_state
            if target.state_id in seen:
                continue
            if authority.is_goal(target):
                return depth + 1
            seen.add(target.state_id)
            if len(seen) > state_limit:
                return None
            queue.append((target, depth + 1))
    return None


__all__ = ["SEARCH", "SEARCH_TIME_LIMIT", "blind_distance", "fast_downward_driver", "optimal_cost", "state_problem"]
