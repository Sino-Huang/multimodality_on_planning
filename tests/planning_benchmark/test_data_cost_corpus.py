import json
import random

import pytest
from PIL import Image

from examples.planning_benchmark_slice.data_cost_corpus import (
    OUTPUT_TOKENS,
    STUDY_ID,
    _hash_task,
    nested_sets,
    task_order,
)

LIMIT = 32768


def _pool(tasks):
    """tasks: [(task_id, domain, records)] in pool order."""
    return [
        {"record_id": f"{task}:bfs:{i}", "task_id": task, "domain": domain}
        for task, domain, count in tasks
        for i in range(count)
    ]


def _inputs(pool, over=()):
    counts = {r["record_id"]: {"text-state": 100, "visual-state": 100, "multimodal-state": 100} for r in pool}
    for record_id, modality in over:
        counts[record_id] = {**counts[record_id], modality: LIMIT}
    return counts


def test_smaller_sets_are_prefixes_of_larger_sets_and_cut_tasks_are_partial():
    pool = _pool([("t1", "a", 3), ("t2", "b", 3), ("t3", "a", 3)])
    result = nested_sets(pool, _inputs(pool), sizes=(2, 4, 8))
    retained = result["retained"]
    assert retained == [r["record_id"] for r in pool][:8]
    sets = result["sets"]
    for small, large in ((2, 4), (4, 8)):
        assert sets[str(small)]["task_ids"] == sets[str(large)]["task_ids"][: len(sets[str(small)]["task_ids"])]
        assert all(n <= sets[str(large)]["domain_records"][d] for d, n in sets[str(small)]["domain_records"].items())
        assert sets[str(small)]["last_record_id"] == retained[small - 1]
    assert sets["4"]["tasks"] == {
        "total": 2,
        "whole": 1,
        "partial": 1,
        "partial_tasks": [{"task_id": "t2", "records": 1, "task_retained_records": 3}],
    }
    assert sets["8"]["domain_records"] == {"a": 5, "b": 3}
    assert sets["8"]["tasks"]["partial_tasks"][0]["task_id"] == "t3"


def test_tasks_interleave_round_robin_over_seeded_domain_order():
    tasks = {"a": ["a1", "a2", "a3"], "b": ["b1"], "c": ["c1", "c2"]}
    domains, order = task_order(tasks, "bfs")
    expected_domains = sorted(tasks)
    random.Random(f"{STUDY_ID}:domains:bfs").shuffle(expected_domains)
    assert domains == expected_domains
    per_domain = {}
    for d in domains:
        ids = sorted(tasks[d])
        random.Random(f"{STUDY_ID}:tasks:bfs:{d}").shuffle(ids)
        per_domain[d] = ids
    # Round 1 visits every domain in order; later rounds skip exhausted domains.
    expected = [per_domain[d][r] for r in range(3) for d in domains if r < len(per_domain[d])]
    assert order == expected
    assert [t[0] for t in order[:3]] == domains


def test_record_over_bound_in_any_single_modality_is_skipped_for_all():
    pool = _pool([("t1", "a", 4)])
    inputs = _inputs(pool, over=[("t1:bfs:1", "visual-state")])
    inputs["t1:bfs:2"]["multimodal-state"] = LIMIT - OUTPUT_TOKENS  # exactly at the bound stays
    result = nested_sets(pool, inputs, sizes=(3,))
    assert result["retained"] == ["t1:bfs:0", "t1:bfs:2", "t1:bfs:3"]
    assert [s["record_id"] for s in result["skipped"]] == ["t1:bfs:1"]
    with pytest.raises(ValueError, match="retains only"):
        nested_sets(pool, inputs, sizes=(4,))


def test_sufficiency_flags_distinct_states_with_identical_pixels(tmp_path):
    states = [
        {"atoms": ["at(r, p1)"], "fluents": []},
        {"atoms": ["at(r, p2)"], "fluents": []},  # different state, same pixels as 0
        {"atoms": ["at(r, p1)"], "fluents": []},  # same state as 0, same pixels: not a collision
        {"atoms": ["at(r, p3)"], "fluents": []},  # different pixels
    ]
    (tmp_path / "catalog.json").write_text(json.dumps({"states": states}))
    (tmp_path / "manifest.json").write_text(json.dumps({"scene_catalog": "catalog.json"}))
    scenes = {}
    for index, colour in enumerate([(0, 0, 0), (0, 0, 0), (0, 0, 0), (0, 0, 1)]):
        Image.new("RGB", (128, 128), colour).save(tmp_path / f"s{index}.png")
        scenes[str(index)] = f"s{index}.png"
    result = _hash_task((tmp_path, "training", "t", "d", scenes, "manifest.json"))
    assert result["colliding_groups"] == [[[0, 2], [1]]]
    assert result["colliding_pairs"] == 1
    assert result["colliding_states"] == 3
    assert result["distinct_dynamic_states"] == 3
