"""Run issue #135 CPU-only choice-frontier selector ladder on the frozen v2 panel.

Copy of ``scripts/run_choice_frontier_o4_zoo.py`` (#133) extended with the graded
``exact-eps-E`` ladder and the privileged ``hadd-greedy`` selector
(docs/experiments/choice-frontier/issue-135-protocol.md). The stored ``arm``
remains a frozen session arm so the unmodified #132 replay contract applies; the
selector identity is recorded independently in each episode and in the binding
manifest. No visual observations are rendered.
"""

from __future__ import annotations

import argparse
import gzip
import itertools
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from examples.planning_benchmark_slice.choice_frontier import (  # noqa: E402
    ChoiceFrontierModelSession,
    ChoiceFrontierTask,
    canonical_choice,
    replay_choice_episode,
)
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority  # noqa: E402
from examples.planning_benchmark_slice.scene_assets import read_json  # noqa: E402

MEMBERSHIP = ROOT / "configs/experiments/choice-frontier-v2/membership.json"
PROTOCOL = "docs/experiments/choice-frontier/issue-135-protocol.md"
OUTPUT = ROOT / "outputs/choice-frontier/v2/zoo"
ALGORITHMS = ("best_first_add_greedy", "best_first_add_w3")
EPSILONS = {"exact-eps-0.25": 0.25, "exact-eps-0.50": 0.50, "exact-eps-0.75": 0.75}
DETERMINISTIC = ("bfs-order", "novelty-first", "worst-first")
SELECTORS = (*EPSILONS, "hadd-greedy", *DETERMINISTIC)
EVALUATION_SEEDS = (17, 5077, 6131, 7409, 8527)
EXACT_SEED = 17
MULTIPLIERS = (2,)


def load_episode(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def save_episode(path: Path, episode: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=6) as stream:
        json.dump(episode, stream, sort_keys=True, separators=(",", ":"))


def load_tasks() -> list[dict]:
    membership = read_json(MEMBERSHIP)
    tasks = membership["tasks"]
    if [task["row"]["task_id"] for task in tasks] != membership["task_ids"]:
        raise ValueError("v2 panel rows differ from the frozen membership")
    return tasks


def reference_expansions(task: dict, algorithm: str) -> int:
    return int(task["row"]["reference_costs"][algorithm]["expansions"])


def task_identity(row: dict, algorithm: str) -> ChoiceFrontierTask:
    return ChoiceFrontierTask(
        instance_id=row["task_id"],
        pair_id=row["task_id"],
        domain=row["domain"],
        algorithm=algorithm,
        exact_expansions=reference_expansions({"row": row}, algorithm),
    )


def authority_for(row: dict) -> PDDLStateAuthority:
    source = read_json(ROOT / row["task_path"])
    return PDDLStateAuthority.from_pddl(source["domain_pddl"], source["problem_pddl"])


class NoveltyMemory:
    """Expanded-state positive features only; no generation-time updates/pruning."""

    def __init__(self) -> None:
        self.singletons: set[str] = set()
        self.pairs: set[tuple[str, str]] = set()

    def score(self, atoms: tuple[str, ...]) -> tuple[int, int]:
        # Zero means at least one novel feature at that width. Seen sets are
        # immutable throughout a menu selection, even for generated states.
        return (
            0 if any(atom not in self.singletons for atom in atoms) else 1,
            0 if any(pair not in self.pairs for pair in itertools.combinations(atoms, 2)) else 1,
        )

    def expand(self, atoms: tuple[str, ...]) -> None:
        self.singletons.update(atoms)
        self.pairs.update(itertools.combinations(atoms, 2))


def decision_rng(seed: int, task_id: str, algorithm: str, decision_index: int) -> random.Random:
    return random.Random(f"{seed}:{task_id}:{algorithm}:{decision_index}")


def select_ref(session: ChoiceFrontierModelSession, selector: str, memory: NoveltyMemory, request):
    controller = session.controller
    entries = controller._frontier_entries
    if selector in EPSILONS or selector == "hadd-greedy":
        rng = decision_rng(session.seed, session.task.instance_id, session.task.algorithm, request.decision_index)
        menu_refs = [entry["state_ref"] for entry in request.menu_binding]
        evidence: dict = {"frontier_size": len(entries)}
        if selector == "hadd-greedy":
            # Frontier entries are (priority, generation_serial, g, h); h is the
            # controller's own AdditiveHeuristic value stored at admission.
            h_by_ref = {controller._state_ref_by_id[state_id]: entry[3] for state_id, entry in entries.items()}
            best = min(h_by_ref.values())
            tied = [ref for ref in menu_refs if h_by_ref[ref] == best]
            state_ref = rng.choice(tied)
            evidence.update(h_add=best, tied_menu_states=len(tied))
        else:
            u = rng.random()
            if u < EPSILONS[selector]:
                state_ref = rng.choice(menu_refs)
                branch = "random"
            else:
                head = controller.frontier_head_state_id()
                if head is None:
                    raise ValueError("exact-eps lost the frontier head")
                state_ref = controller._state_ref_by_id[head]
                branch = "exact_head"
            evidence.update(u=u, branch=branch)
        state_id = controller._states_by_ref[state_ref].state_id
        entry = entries[state_id]
        evidence.update(
            generation_serial=entry[1],
            g=entry[2],
            additive_priority=entry[0],
            h=entry[3],
            selected_state_ref=state_ref,
        )
        return state_ref, controller.states[state_id].atoms, evidence
    if selector == "bfs-order":

        def key(item):
            return (item[1][2], item[1][1])
    elif selector == "worst-first":

        def key(item):
            return (-item[1][0], item[1][1])
    else:

        def key(item):
            return (*memory.score(controller.states[item[0]].atoms), item[1][1])

    state_id, entry = min(entries.items(), key=key)
    evidence = {
        "frontier_size": len(entries),
        "generation_serial": entry[1],
        "g": entry[2],
        "additive_priority": entry[0],
        "selected_state_ref": controller._state_ref_by_id[state_id],
        "selection_key": list(key((state_id, entry))),
    }
    if selector == "novelty-first":
        evidence["expanded_feature_memory_before"] = {
            "atoms": len(memory.singletons),
            "pairs": len(memory.pairs),
        }
    return controller._state_ref_by_id[state_id], controller.states[state_id].atoms, evidence


def run_episode(row: dict, algorithm: str, arm: str, multiplier: int, seed: int) -> dict:
    task = task_identity(row, algorithm)
    session = ChoiceFrontierModelSession(
        authority=authority_for(row),
        task=task,
        arm="random_valid" if arm == "random_valid" else "exact_reference",
        seed=seed,
        decision_cap=multiplier * task.exact_expansions,
    )
    novelty = NoveltyMemory()
    selection_evidence = []
    while (request := session.next_request()) is not None:
        if arm in ("random_valid", "exact_reference"):
            output = session.reference_output()
            atoms = ()
        else:
            state_ref, atoms, evidence = select_ref(session, arm, novelty, request)
            label = next(item["choice"] for item in request.menu_binding if item["state_ref"] == state_ref)
            evidence["decision_index"] = request.decision_index
            selection_evidence.append(evidence)
            output = canonical_choice(label)
        session.submit_output(output)
        if arm == "novelty-first" and session.events[-1]["trusted_runtime_result"]["status"] == "expanded":
            novelty.expand(atoms)
    episode = session.episode()
    if arm in SELECTORS:
        episode["selector"] = arm
        episode["selector_evidence"] = selection_evidence
    statuses: dict[str, int] = {}
    for event in episode["events"]:
        for admission in event["trusted_runtime_result"].get("admissions", []):
            status = admission["trusted_runtime_result"]["status"]
            statuses[status] = statuses.get(status, 0) + 1
    episode["admission_status_counts"] = statuses
    return episode


def bindings(tasks: list[dict]) -> list[dict]:
    result = []
    for task in tasks:
        task_id = task["row"]["task_id"]
        directory = task_id.replace("/", "__")
        for algorithm in ALGORITHMS:
            for multiplier in MULTIPLIERS:
                for arm in ("exact_reference", "random_valid", *SELECTORS):
                    seeds = [EXACT_SEED] if arm == "exact_reference" or arm in DETERMINISTIC else EVALUATION_SEEDS
                    for seed in seeds:
                        path = OUTPUT / "episodes" / directory / f"{algorithm}-{arm}-m{multiplier}-{seed}.json.gz"
                        result.append(
                            {
                                "task_id": task_id,
                                "algorithm": algorithm,
                                "arm": arm,
                                "selector": arm if arm in SELECTORS else None,
                                "multiplier": multiplier,
                                "seed": seed,
                                "source": "v2",
                                "episode_path": str(path.relative_to(ROOT)),
                                "expected_decision_cap": multiplier * reference_expansions(task, algorithm),
                                "status": "pending",
                                "replay_status": "pending",
                            }
                        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, help="Run only the first N missing new episodes (smoke)")
    args = parser.parse_args()
    tasks = load_tasks()
    task_by_id = {task["row"]["task_id"]: task["row"] for task in tasks}
    expected = bindings(tasks)
    if len(expected) != 58 * len(tasks):
        raise ValueError("v2 zoo binding matrix differs from the frozen protocol")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUTPUT / "manifest.json"
    ran = 0
    for binding in expected:
        row = task_by_id[binding["task_id"]]
        task = task_identity(row, binding["algorithm"])
        path = ROOT / binding["episode_path"]
        try:
            if not path.exists() and (args.limit is None or ran < args.limit):
                episode = run_episode(row, binding["algorithm"], binding["arm"], binding["multiplier"], binding["seed"])
                save_episode(path, episode)
                ran += 1
            if path.exists():
                episode = load_episode(path)
                if episode["instance_id"] != binding["task_id"] or binding["selector"] != episode.get("selector"):
                    raise ValueError("v2 episode identity or selector mismatch")
                if (
                    episode["algorithm"] != binding["algorithm"]
                    or episode["seed"] != binding["seed"]
                    or episode["decision_cap"] != binding["expected_decision_cap"]
                ):
                    raise ValueError("stored episode algorithm, seed or decision cap mismatch")
                replay_choice_episode(authority_for(row), task, episode)
                binding["status"] = "observed"
                binding["replay_status"] = "passed"
                binding["result"] = episode["result"]
                binding["admission_status_counts"] = episode.get("admission_status_counts")
            else:
                binding["status"] = "missing"
                binding["replay_status"] = "not_run"
        except Exception as error:
            binding["status"] = "error"
            binding["replay_status"] = "failed"
            binding["error"] = f"{type(error).__name__}: {error}"
            print(f"ERROR {binding['episode_path']}: {error}", flush=True)
        # Write on each binding so interruption retains explicit expected and
        # observed coverage rather than relying on filenames for recovery.
        counts = {
            status: sum(item["status"] == status for item in expected)
            for status in ("observed", "missing", "error", "pending")
        }
        payload = {
            "schema_version": "choice_frontier_v2_zoo_manifest_v1",
            "protocol": PROTOCOL,
            "membership": str(MEMBERSHIP.relative_to(ROOT)),
            "episode_format": (
                "#133 envelope: frozen session arm (exact_reference for rule selectors) plus "
                "top-level selector identity and per-decision selector_evidence. CPU selectors "
                "use identical model_input and permuted menu, without image or scene rendering."
            ),
            "expected_bindings": len(expected),
            "counts": counts,
            "complete": counts["observed"] == len(expected),
            "bindings": expected,
        }
        manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(
            f"{counts['observed']}/{len(expected)} {binding['arm']} m{binding['multiplier']} "
            f"{binding['task_id']} {binding['algorithm']} seed{binding['seed']} "
            f"{binding['replay_status']}",
            flush=True,
        )
    if args.limit is None and any(item["status"] != "observed" for item in expected):
        raise SystemExit("v2 zoo incomplete; inspect manifest missing/error bindings")


if __name__ == "__main__":
    main()
