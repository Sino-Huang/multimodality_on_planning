"""Issue #139 panel-construction contracts (scripts/build_choice_frontier_v4_panels.py)."""

from __future__ import annotations

import hashlib
import json

import pytest

from scripts.build_choice_frontier_v4_panels import (
    ALGORITHMS,
    ROOT,
    exclusion_hashes,
    exclusion_reason,
    select_p2,
    select_p2u,
)

RANDOM_SCREEN_KEYS = {"screen_random_goals", "screen_random_episodes", "screen_detail", "admitted"}


class NoRandomScreen(dict):
    """A candidate record that fails loudly if a random-screening field is read."""

    def __getitem__(self, key):
        assert key not in RANDOM_SCREEN_KEYS, f"P2u selection read {key}"
        return super().__getitem__(key)

    def get(self, key, default=None):
        assert key not in RANDOM_SCREEN_KEYS, f"P2u selection read {key}"
        return super().get(key, default)


def candidate(domain: str, seed: int, *, kept=True, exact=(True, True), random_goals=5) -> dict:
    return {
        "task_id": f"choice-frontier-v4/{domain}-expanded-{seed}",
        "domain": domain,
        "seed": seed,
        "cstar_status": "kept" if kept else "rejected",
        "screen_exact_goal": all(exact),
        "screen_exact_goal_by_algorithm": dict(zip(ALGORITHMS, exact, strict=True)),
        "screen_random_goals": random_goals,
        "screen_random_episodes": 10,
        "screen_detail": {},
        "admitted": kept and all(exact) and 1 <= random_goals <= 9,
    }


def pool() -> list[dict]:
    records = []
    for domain in ("blocksworld", "driverlog", "grid", "gripper", "15puzzle", "visitall"):
        for offset in range(5):
            records.append(candidate(domain, 955000 + offset, random_goals=(0, 5, 10, 3, 9)[offset]))
    records.append(candidate("ferry", 955000, exact=(True, False)))
    records.append(candidate("ferry", 955001, kept=False))
    return records


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def test_a_sha_matching_any_source_is_dropped():
    excluded_by = {"h-a": "a:x:t1", "h-b": "b:x:t2", "h-c": "c:x:t3", "h-d": "d:x:t4"}
    for key, label in excluded_by.items():
        assert exclusion_reason(key, excluded_by, {}) == "overlap:" + label
    assert exclusion_reason("h-new", excluded_by, {"h-new": "v4/first"}) == "duplicate_candidate:v4/first"
    assert exclusion_reason("h-new", excluded_by, {}) is None


def test_exclusion_hashes_cover_every_source():
    hashes = exclusion_hashes()
    v2 = json.loads((ROOT / "configs/experiments/choice-frontier-v2/candidates.json").read_text())["candidates"]
    v3 = json.loads((ROOT / "configs/experiments/choice-frontier-v3/training-tasks.json").read_text())["tasks"]
    assert all(r["problem_sha256"] in hashes for r in v2 if r.get("problem_sha256"))
    # All #136 rows count, including rows #136 itself excluded.
    assert all(r["problem_sha256"] in hashes for r in v3 if r.get("problem_sha256"))
    panel = json.loads((ROOT / "configs/experiments/expanded-study/final-panel.json").read_text())["tasks"]
    for task in panel:
        row = task.get("row", task)
        assert sha(json.loads((ROOT / row["task_path"]).read_text())["problem_pddl"]) in hashes
    assert any(label.startswith("d:") for label in hashes.values())


def test_p2u_selection_never_reads_random_screening():
    records = pool()
    p2_ids = {r["task_id"] for r in select_p2(records)}
    guarded = [NoRandomScreen(r) for r in records]
    chosen = select_p2u(guarded, p2_ids)
    # Same selection whatever the random-screen outcomes were.
    flipped = [NoRandomScreen({**r, "screen_random_goals": 10 - r["screen_random_goals"]}) for r in records]
    assert [r["task_id"] for r in select_p2u(flipped, p2_ids)] == [r["task_id"] for r in chosen]
    assert all(all(r["screen_exact_goal_by_algorithm"].values()) and r["cstar_status"] == "kept" for r in chosen)


def test_p2_and_p2u_are_disjoint_and_follow_the_freeze_walk():
    records = pool()
    p2 = select_p2(records)
    p2u = select_p2u(records, {r["task_id"] for r in p2})
    assert not {r["task_id"] for r in p2} & {r["task_id"] for r in p2u}
    for panel in (p2, p2u):
        assert len(panel) == 12
        per_domain = {}
        for r in panel:
            per_domain[r["domain"]] = per_domain.get(r["domain"], 0) + 1
        assert max(per_domain.values()) <= 2
    # P2 admits only 1..9 random goals; P2u takes the random-degenerate tasks P2 cannot.
    assert all(1 <= r["screen_random_goals"] <= 9 for r in p2)
    assert any(r["screen_random_goals"] in (0, 10) for r in p2u)
    assert "choice-frontier-v4/ferry-expanded-955000" not in {r["task_id"] for r in p2u}


@pytest.mark.parametrize("exact", [(True, False), (False, True), (False, False)])
def test_p2u_requires_exact_goal_for_both_algorithms(exact):
    records = [candidate("grid", 955000, exact=exact)]
    assert select_p2u(records, set()) == []
