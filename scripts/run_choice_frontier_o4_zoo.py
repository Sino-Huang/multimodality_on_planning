"""Run issue #133 CPU-only choice-frontier selectors and expanded random controls.

The stored ``arm`` remains a frozen session arm so the unmodified #132 replay
contract applies. The new selector identity is recorded independently in each
comparator episode and in the binding manifest. No visual observations are
rendered: session model_input and permuted menu are the frozen #132 contract.
"""

from __future__ import annotations

import argparse
import gzip
import itertools
import json
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
from scripts.run_choice_frontier import load_protocol, load_tasks, reference_expansions  # noqa: E402

OUTPUT = ROOT / "outputs/choice-frontier/o4/zoo"
ORIGINAL = ROOT / "outputs/choice-frontier/v1/evaluation/episodes"
SELECTORS = ("bfs-order", "novelty-first", "worst-first")
MULTIPLIERS = (2, 3, 4)


def load_episode(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def save_episode(path: Path, episode: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=6) as stream:
        json.dump(episode, stream, sort_keys=True, separators=(",", ":"))


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


def select_ref(session: ChoiceFrontierModelSession, selector: str, memory: NoveltyMemory):
    controller = session.controller
    entries = controller._frontier_entries
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
        arm="exact_reference" if arm in SELECTORS else "random_valid",
        seed=seed,
        decision_cap=multiplier * task.exact_expansions,
    )
    novelty = NoveltyMemory()
    selection_evidence = []
    while (request := session.next_request()) is not None:
        if arm == "random_valid":
            output = session.reference_output()
            atoms = ()
        else:
            state_ref, atoms, evidence = select_ref(session, arm, novelty)
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


def bindings(protocol: dict, tasks: list[dict]) -> list[dict]:
    result = []
    seeds = [int(seed) for seed in protocol["evaluation"]["seeds"]["random_valid"]]
    for task in tasks:
        task_id = task["row"]["task_id"]
        directory = task_id.replace("/", "__")
        for algorithm in protocol["learned_algorithms"]:
            for multiplier in MULTIPLIERS:
                for arm in (*SELECTORS, "random_valid"):
                    for seed in seeds if arm == "random_valid" else [17]:
                        if arm == "random_valid" and multiplier == 2:
                            path = ORIGINAL / directory / f"{algorithm}-random_valid-{seed}.json.gz"
                            source = "frozen-132"
                        else:
                            path = OUTPUT / "episodes" / directory / f"{algorithm}-{arm}-m{multiplier}-{seed}.json.gz"
                            source = "o4"
                        result.append(
                            {
                                "task_id": task_id,
                                "algorithm": algorithm,
                                "arm": arm,
                                "selector": arm if arm in SELECTORS else None,
                                "multiplier": multiplier,
                                "seed": seed,
                                "source": source,
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
    protocol = load_protocol()
    tasks = load_tasks(protocol)
    task_by_id = {task["row"]["task_id"]: task["row"] for task in tasks}
    expected = bindings(protocol, tasks)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUTPUT / "manifest.json"
    ran = 0
    for binding in expected:
        row = task_by_id[binding["task_id"]]
        task = task_identity(row, binding["algorithm"])
        path = ROOT / binding["episode_path"]
        try:
            if (
                binding["source"] == "o4"
                and (
                    not path.exists() or (binding["arm"] in SELECTORS and "selector_evidence" not in load_episode(path))
                )
                and (args.limit is None or ran < args.limit)
            ):
                episode = run_episode(row, binding["algorithm"], binding["arm"], binding["multiplier"], binding["seed"])
                save_episode(path, episode)
                ran += 1
            if path.exists():
                episode = load_episode(path)
                if binding["source"] == "frozen-132":
                    if episode["task_id"] != binding["task_id"] or episode["condition"] != "random_valid":
                        raise ValueError("frozen random episode identity mismatch")
                    replay_report = {
                        "arm": "random_valid",
                        "adapter_id": None,
                        "seed": episode["seed"],
                        "decision_cap": episode["decision_cap"],
                        "events": episode["events"],
                        "result": episode["result"],
                    }
                else:
                    if episode["instance_id"] != binding["task_id"] or binding["selector"] != episode.get("selector"):
                        raise ValueError("O4 episode identity or selector mismatch")
                    replay_report = episode
                if (
                    episode["algorithm"] != binding["algorithm"]
                    or episode["seed"] != binding["seed"]
                    or episode["decision_cap"] != binding["expected_decision_cap"]
                ):
                    raise ValueError("stored episode algorithm, seed or decision cap mismatch")
                replay_choice_episode(authority_for(row), task, replay_report)
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
            "schema_version": "choice_frontier_o4_zoo_manifest_v1",
            "protocol": "docs/experiments/choice-frontier/issue-133-protocol.md",
            "episode_format": (
                "Frozen #132 envelopes unchanged; O4 episodes use frozen session arm and "
                "top-level selector identity. CPU selector uses identical model_input and "
                "permuted menu, without image or scene rendering; view bindings are not "
                "generated or replayed."
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
        raise SystemExit("O4 zoo incomplete; inspect manifest missing/error bindings")


if __name__ == "__main__":
    main()
