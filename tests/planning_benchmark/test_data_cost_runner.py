import json
import math
import random
import subprocess
import time

import pytest

from examples.planning_benchmark_slice import data_cost_analysis as analysis
from examples.planning_benchmark_slice import data_cost_runner as runner

SIZES = analysis.SIZES


# --------------------------------------------------------------------------------------------- N_q


def test_n_quantile_interpolates_in_log2_at_first_upward_crossing():
    result = analysis.n_quantile(SIZES, [0.0, 0.2, 0.4, 0.6, 0.8, 1.0], 0.5)
    assert result["censoring"] == "none"
    assert result["log2"] == pytest.approx(11.5)
    assert result["value"] == pytest.approx(2**11.5)
    # Non-monotone curve: the first crossing wins even though the curve dips below q later.
    dip = analysis.n_quantile(SIZES, [0.0, 0.6, 0.3, 0.7, 0.9, 1.0], 0.5)
    assert dip["log2"] == pytest.approx(9 + 0.5 / 0.6)
    # Landing exactly on q counts as reaching it at that size.
    exact = analysis.n_quantile(SIZES, [0.0, 0.2, 0.9, 0.9, 0.9, 0.9], 0.9)
    assert exact["log2"] == pytest.approx(11.0)


def test_n_quantile_censoring_and_missing_points():
    left = analysis.n_quantile(SIZES, [0.95, 1.0, 1.0, 1.0, 1.0, 1.0], 0.9)
    assert (left["label"], left["censoring"], left["ordinal"]) == ("<=512", "left", -math.inf)
    right = analysis.n_quantile(SIZES, [0.0, 0.1, 0.2, 0.3, 0.5, 0.89], 0.9)
    assert (right["label"], right["censoring"], right["ordinal"]) == (">16384", "right", math.inf)
    # Missing sizes are skipped; a partial curve is right-censored at its largest evaluated size.
    partial = analysis.n_quantile(SIZES, [0.1, 0.3, None, None, None, None], 0.5)
    assert (partial["label"], partial["censoring"]) == (">1024", "right")
    gap = analysis.n_quantile(SIZES, [0.0, None, 1.0, None, None, None], 0.5)
    assert gap["log2"] == pytest.approx(10.0)
    assert analysis.n_quantile(SIZES, [None] * 6, 0.5)["censoring"] == "missing"


def test_holm_step_down_is_monotone_and_capped():
    assert analysis.holm([0.01, 0.04, 0.03, 0.005]) == pytest.approx([0.03, 0.06, 0.06, 0.02])
    assert analysis.holm([0.5, 0.9]) == pytest.approx([1.0, 1.0])
    assert analysis.holm([]) == []


# --------------------------------------------------------------------------------------------- priority order


def test_unit_priority_order_is_frozen():
    slots = runner.slots()
    assert len(slots) == 115
    units = runner.units()
    assert len(units) == 6 + 109 * 2 and len(set(units)) == len(units)
    assert [s["key"] for s in slots[:6]] == [f"base:{a}:{m}" for a in runner.ALGORITHMS for m in runner.MODALITIES]
    learned = [s["cell"] for s in slots[6:]]
    control_index = next(i for i, c in enumerate(learned) if c["kind"] == "control")
    assert control_index == 36
    assert all(c["seed"] == 17 for c in learned[:36])
    assert [c["seed"] for c in learned[37:]] == [29] * 36 + [71] * 36
    assert [(c["size"], c["algorithm"], c["modality"]) for c in learned[:6]] == [
        (512, a, m) for a in runner.ALGORITHMS for m in runner.MODALITIES
    ]
    assert [c["size"] for c in learned[:36]] == sorted(c["size"] for c in learned[:36])
    for slot in slots[6:]:
        assert slot["stages"] == [f"train:{slot['key']}", f"eval:{slot['key']}"]
    assert slots[42]["key"] == "control:bfs:text-state:2048x8:17"
    assert runner.parse_unit("train:control:bfs:text-state:2048x8:17")[1] == runner.CONTROL_CELL | {"kind": "control"}
    assert runner.expected_steps(runner.CONTROL_CELL) == runner.expected_steps(slots[-1]["cell"]) == 512


def test_cell_order_nests_sets_and_shuffles_per_cell_and_epoch():
    membership = {"training_record_ids": {"bfs": [f"r{i}" for i in range(16384)]}}
    cell = {"kind": "learned", "algorithm": "bfs", "modality": "text-state", "size": 1024, "epochs": 1, "seed": 17}
    order = runner.cell_order(membership, cell)
    assert set(order) == {f"r{i}" for i in range(1024)} and len(order) == 1024
    expected = [f"r{i}" for i in range(1024)]
    random.Random("data-cost-v1:order:bfs:1024:17").shuffle(expected)
    assert order == expected
    assert runner.cell_order(membership, dict(cell, seed=29)) != order
    control = runner.cell_order(membership, dict(runner.CONTROL_CELL, kind="control"))
    assert len(control) == 16384
    epochs = [control[i * 2048 : (i + 1) * 2048] for i in range(8)]
    assert all(set(e) == {f"r{i}" for i in range(2048)} for e in epochs)
    assert len({tuple(e) for e in epochs}) == 8
    with pytest.raises(ValueError):
        runner.cell_order({"training_record_ids": {"bfs": ["a"] * 600}}, dict(cell, size=512))


# --------------------------------------------------------------------------------------------- queue / resume


def _receipt(root, unit):
    path = runner.receipt_path(root, unit)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"unit": unit, "outcome": "PASS"}))


def _dead_handle():
    process = subprocess.Popen(["true"])
    handle = runner.worker_handle(0)
    handle.update(pid=process.pid, start_ticks=runner.worker_handle(0)["start_ticks"])
    process.wait()
    return handle


def test_claims_skip_completed_and_live_units_and_reclaim_stale(tmp_path):
    slots = runner.slots()
    _receipt(tmp_path, slots[0]["stages"][0])
    sleeper = subprocess.Popen(["sleep", "30"])
    try:
        from examples.planning_benchmark_slice.expanded_scheduler import handle as proc_handle

        live = {**runner.worker_handle(1), **proc_handle(sleeper.pid)}
        with runner.queue_state(tmp_path) as state:
            state["claims"][slots[1]["key"]] = _dead_handle()  # crashed worker
            state["claims"][slots[2]["key"]] = live  # other worker still running
        me = runner.worker_handle(0)
        assert runner.claim_next(tmp_path, 0, handle=me)["key"] == slots[1]["key"]
        assert runner.claim_next(tmp_path, 0, handle=me)["key"] == slots[3]["key"]
        claims = json.loads((tmp_path / runner.QUEUE / "claims.json").read_text())
        assert [h["event"] for h in claims["history"]].count("stale_reclaimed") == 1
        summary = runner.queue_summary(tmp_path)
        assert (summary["done"], summary["running"]) == (1, 3)
        # A claim from a previous boot is stale even if the PID was reused.
        with runner.queue_state(tmp_path) as state:
            state["claims"][slots[2]["key"]] = dict(live, boot_id="previous-boot")
        assert runner.claim_next(tmp_path, 1, handle=me)["key"] == slots[2]["key"]
    finally:
        sleeper.kill()


def test_worker_resumes_mid_slot_after_crash_and_stops_on_budget(tmp_path, monkeypatch):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
    monkeypatch.setenv("MASTER_PORT", "18860")
    monkeypatch.delenv("EXPANDED_ATTEMPT_DIR", raising=False)
    monkeypatch.delenv("EXPANDED_PROGRESS_PATH", raising=False)
    calls = []
    crash = {"unit": "eval:bfs:text-state:512:17"}

    def fake_run_unit(root, unit, *, gpu, deadline, progress):
        calls.append(unit)
        if unit == crash["unit"]:
            crash["unit"] = None
            raise RuntimeError("simulated crash during evaluation")
        _receipt(root, unit)
        return {}

    monkeypatch.setattr(runner, "run_unit", fake_run_unit)
    for slot in runner.slots()[:6]:
        _receipt(tmp_path, slot["stages"][0])
    first = runner.worker(tmp_path, 0, max_slots=1)
    assert first["slots"][0]["outcome"] == "FAILED"
    assert calls == ["train:bfs:text-state:512:17", "eval:bfs:text-state:512:17"]
    second = runner.worker(tmp_path, 0, max_slots=1)
    assert second["slots"][0] == {"slot": "bfs:text-state:512:17", "outcome": "PASS"}
    assert calls[2:] == ["eval:bfs:text-state:512:17"]  # finished training is not repeated
    assert runner.queue_summary(tmp_path)["failures"] == {"bfs:text-state:512:17": 1}

    ledger = {
        "attempts": [
            {"status": "succeeded", "gpus": [0], "gpu_hours": 700.0},
            {"status": "running", "gpus": [1], "started": time.time() - 61 * 3600},
        ]
    }
    (tmp_path / runner.LEDGER).write_text(json.dumps(ledger))
    before = len(calls)
    stopped = runner.worker(tmp_path, 0)
    assert stopped["stop_reason"].startswith("budget") and len(calls) == before
    ledger["attempts"][1]["started"] = time.time() - 59 * 3600
    (tmp_path / runner.LEDGER).write_text(json.dumps(ledger))
    assert runner.worker(tmp_path, 0, max_slots=1)["slots"][0]["outcome"] == "PASS"


def test_slot_failing_twice_is_blocked_not_retried_forever(tmp_path):
    key = runner.slots()[0]["key"]
    runner.release(tmp_path, key, failure="one")
    runner.release(tmp_path, key, failure="two")
    assert runner.claim_next(tmp_path, 0)["key"] == runner.slots()[1]["key"]
    assert runner.queue_summary(tmp_path)["blocked"] == 1


def test_schedule_and_worker_job_documents(tmp_path):
    runner.ensure_schedule(tmp_path)
    schedule = json.loads((tmp_path / runner.SCHEDULE).read_text())
    assert schedule["program_id"] == "data-cost-v1"
    assert schedule["experiment_gpu_hours_cap"] == 800 and schedule["allocations_gpu_hours"] == {"data_cost": 800}
    assert schedule["master_port_pool"] == [18860, 18861, 18862, 18863]
    job = runner.job_document(1, "data-cost-worker-gpu1", 7 * 24 * 3600)
    script = job["command"][-1]
    assert job["command"][:2] == ["bash", "-lc"] and job["gpus"] == [1]
    assert script.index("source ~/cd_vlaplan") < script.index("CUDA_VISIBLE_DEVICES=1") < script.index("--gpu 1")
    (tmp_path / runner.SCHEDULE).write_text(json.dumps(dict(schedule, experiment_gpu_hours_cap=900)))
    with pytest.raises(ValueError):
        runner.ensure_schedule(tmp_path)


# --------------------------------------------------------------------------------------------- analyzer end-to-end


def _synthetic_rows(tasks, drop=()):
    rng = random.Random(5)
    rows = []

    def add(kind, algorithm, modality, size, epochs, seed, p):
        for task in tasks:
            if (kind, algorithm, modality, size, seed) in drop:
                continue
            success = rng.random() < p
            calls = rng.randint(4, 40)
            invalid = None if success else rng.randint(1, calls)
            rows.append(
                {
                    "kind": kind,
                    "algorithm": algorithm,
                    "modality": modality,
                    "size": size,
                    "epochs": epochs,
                    "seed": seed,
                    "task_id": task,
                    "success": success,
                    "calls": calls,
                    "accepted": calls - (0 if success else 1),
                    "valid_op_rate": 1 - (0 if success else 1 / calls),
                    "first_invalid_step": invalid,
                }
            )

    for algorithm in analysis.ALGORITHMS:
        for m_index, modality in enumerate(analysis.MODALITIES):
            for s_index, size in enumerate(SIZES):
                for seed in analysis.SEEDS:
                    # bfs learns fast; best_first_width never learns (planted separation).
                    p = min(1.0, 0.2 * s_index - 0.05 * m_index) if algorithm == "bfs" else 0.0
                    add("learned", algorithm, modality, size, 1, seed, max(0.0, p))
            add("base", algorithm, modality, None, None, None, 0.0)
        add("exact_reference", algorithm, "text-state", None, None, 17, 1.0)
        for seed in analysis.RANDOM_VALID_SEEDS:
            add("random_valid", algorithm, "text-state", None, None, seed, 0.05)
    add("control", "bfs", "text-state", 2048, 8, 17, 0.7)
    return rows


def test_analyzer_end_to_end_on_synthetic_episodes(tmp_path):
    tasks = [f"data-cost/d{i // 2}-{'compact' if i % 2 == 0 else 'expanded'}-{i}" for i in range(30)]
    domains = {task: task.split("/")[1].split("-")[0] for task in tasks}
    dropped = ("learned", "best_first_width", "visual-state", 16384, 71)
    rows = _synthetic_rows(tasks, drop={dropped})
    sufficiency = {"domains": {"d0": {"verdict": "FAIL"}, **{f"d{i}": {"verdict": "PASS"} for i in range(1, 15)}}}
    node_choice = (
        json.loads((runner.ROOT / "outputs/choice-frontier/v4/seeds/metrics/analysis.json").read_text())
        if (runner.ROOT / "outputs/choice-frontier/v4/seeds/metrics/analysis.json").exists()
        else None
    )
    result = analysis.analyze(
        rows, tasks, task_domains=domains, sufficiency=sufficiency, node_choice=node_choice, draws=400
    )
    json.dumps(result, allow_nan=False)
    assert result["missingness"]["learned_cells_missing"] == ["best_first_width/visual-state/16384/seed-71"]
    assert result["missingness"]["complete"] is False
    cells = {(c["algorithm"], c["modality"], c["size"]): c for c in result["cells"]}
    assert cells[("best_first_width", "visual-state", 16384)]["episodes_present"] == 60
    assert cells[("bfs", "text-state", 512)]["success_3seed_mean"] == 0.0
    bfs_text = result["n_quantiles"]["bfs/text-state"]
    assert bfs_text["N50"]["censoring"] == "none" and 2048 < bfs_text["N50"]["value"] < 8192
    assert result["n_quantiles"]["best_first_width/text-state"]["N50"]["label"] == ">16384"
    tests = result["success_contrasts"]["tests"]
    assert result["success_contrasts"]["family_size"] == len(tests) == 54
    verdict = {(t["contrast"], t["size"]): t["verdict"] for t in tests}
    assert verdict[("bfs-best_first_width | text-state", 16384)] == "SEPARATED"
    assert verdict[("bfs-best_first_width | text-state", 512)] == "NOT_SEPARATED"  # both arms all-zero
    assert all(t["holm_p"] >= t["p"] for t in tests)
    control = result["compute_matched_control"]["comparisons"]
    assert control["control-minus-16384x1-seed17_paired"]["pairs"] == 30
    assert result["controls"]["exact_reference/bfs"]["success"] == 1.0
    assert result["secondary_sufficiency"]["failed_domains"] == ["d0"]
    assert result["secondary_sufficiency"]["tasks_kept"] == 28
    assert all(c["modality"] != "text-state" for c in result["secondary_sufficiency"]["cells"])
    outputs = analysis.figure(result, str(tmp_path / "data-cost-curves"))
    assert all((tmp_path / f"data-cost-curves.{s}").stat().st_size > 1000 for s in ("pdf", "png")) and len(outputs) == 2
