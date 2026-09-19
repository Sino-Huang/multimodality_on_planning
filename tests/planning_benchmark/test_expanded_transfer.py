"""CPU-only tests for the transfer (#104-#107) branch machinery."""

import gzip
import json
import math
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from examples.planning_benchmark_slice import expanded_transfer as branch
from examples.planning_benchmark_slice.modality_view_preparation import write_json

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = ROOT / "configs/experiments/expanded-study/transfer-protocol.json"


def repository_protocol():
    return json.loads(PROTOCOL_PATH.read_text())


# ---------------------------------------------------------------------------
# Subset arithmetic
# ---------------------------------------------------------------------------


def test_hamilton_apportionment_folio_seats():
    seats = branch.hamilton_apportionment({"True": 72, "Uncertain": 69, "False": 63}, 200)
    assert seats == {"True": 70, "Uncertain": 68, "False": 62}
    assert sum(seats.values()) == 200
    assert branch._audit_apportionment({"True": 72, "Uncertain": 69, "False": 63}, 200) == seats


def test_hamilton_apportionment_deterministic_tie_break():
    sizes = {"b": 10, "a": 10, "c": 11}
    first = branch.hamilton_apportionment(sizes, 16)
    assert first == branch.hamilton_apportionment(dict(reversed(list(sizes.items()))), 16)
    assert sum(first.values()) == 16
    assert first == branch._audit_apportionment(sizes, 16)
    assert branch.hamilton_apportionment({"x": 1}, 0) == {"x": 0}


def test_folio_subset_first_k_per_stratum_in_file_order():
    labels = ["True"] * 36 + ["Uncertain"] * 34 + ["False"] * 32 + ["True"] * 36 + ["Uncertain"] * 35 + ["False"] * 31
    assert len(labels) == 204
    selected, seats = branch.folio_subset_indices(labels, 200)
    assert seats == {"True": 70, "Uncertain": 68, "False": 62}
    assert selected == sorted(selected)
    per_label = {label: [i for i in selected if labels[i] == label] for label in branch.FOLIO_LABELS}
    for label, expected in seats.items():
        members = [i for i, value in enumerate(labels) if value == label]
        assert per_label[label] == members[:expected]
    audit = branch._audit_folio_indices(labels, 200)
    assert audit == selected


def test_folio_subset_below_cap_keeps_everything():
    selected, seats = branch.folio_subset_indices(["True", "False"], 200)
    assert selected == [0, 1]
    assert seats == {"True": 1, "Uncertain": 0, "False": 1}


def test_gsm8k_step_count_annotations_and_fallback():
    assert branch.gsm8k_step_count("a <<1+1=2>> b <<2*2=4>> #### 4") == 2
    assert branch.gsm8k_step_count("line one\n\nline two\n#### 3") == 2
    assert branch.gsm8k_step_count("#### 3") == 0


def test_quartile_stratification_determinism():
    counts = [(index * 37) % 23 for index in range(1319)]
    first = branch.quartile_strata(counts)
    again = branch.quartile_strata(counts)
    assert first == again
    assert [len(stratum) for stratum in first] == [330, 330, 330, 329]
    for stratum in first:
        assert stratum == sorted(stratum)
    ordered = sorted(range(1319), key=lambda i: (counts[i], i))
    for quarter, stratum in enumerate(first):
        ranks = {index: rank for rank, index in enumerate(ordered)}
        assert all(min(3, (4 * ranks[i]) // 1319) == quarter for i in stratum)
    selected, seats = branch.gsm8k_subset_indices(counts, 200)
    assert seats == {"q0": 50, "q1": 50, "q2": 50, "q3": 50}
    assert len(selected) == 200
    assert selected == branch._audit_gsm8k_indices(counts, 200)
    per_stratum = {
        quarter: [i for i in selected if i in set(first[quarter])] for quarter in range(4)
    }
    for quarter in range(4):
        assert per_stratum[quarter] == first[quarter][:50]


def test_l1_is_even_positions_of_l0():
    l0 = [f"folio-{i}" for i in range(200)]
    l1 = branch.l1_order(l0)
    assert l1 == l0[::2]
    assert len(l1) == 100
    assert len(branch.l1_order([str(i) for i in range(164)])) == 82
    assert branch._audit_l1(l0) == l1


# ---------------------------------------------------------------------------
# Prompt rendering and message builders
# ---------------------------------------------------------------------------


def test_repository_protocol_prompt_constants_match_module():
    protocol = repository_protocol()
    assert protocol["benchmarks"]["folio"]["prompt"]["system"] == branch.FOLIO_SYSTEM
    assert protocol["benchmarks"]["folio"]["prompt"]["user_template"] == branch.FOLIO_USER_TEMPLATE
    assert protocol["benchmarks"]["gsm8k"]["prompt"]["user_template"] == branch.GSM8K_USER_TEMPLATE
    assert protocol["benchmarks"]["humaneval"]["prompt"]["user_template"] == branch.HUMANEVAL_USER_TEMPLATE


def test_repository_protocol_validates_against_live_repo():
    report = branch.validate_protocol(ROOT, repository_protocol())
    assert report["outcome"] == "PASS"
    assert report["l0_sizes"] == {"folio": 200, "gsm8k": 200, "humaneval": 164}
    assert report["l1_sizes"] == {"folio": 100, "gsm8k": 100, "humaneval": 82}
    changed = json.loads(PROTOCOL_PATH.read_text())
    changed["benchmarks"]["folio"]["subset_size"] = 201
    with pytest.raises(ValueError, match="transfer protocol validation failed"):
        branch.validate_protocol(ROOT, changed)
    changed = json.loads(PROTOCOL_PATH.read_text())
    changed["benchmarks"]["gsm8k"]["prompt"]["user_template"] = "different"
    with pytest.raises(ValueError, match="transfer protocol validation failed"):
        branch.validate_protocol(ROOT, changed)


def test_message_builders_render_frozen_prompts():
    model_input = {
        "benchmark": "folio",
        "example_id": "folio-0",
        "premises": ["All cats are mammals.", "Tom is a cat."],
        "conclusion": "Tom is a mammal.",
    }
    training = branch.folio_training_messages(model_input)
    assert training[0] == {"role": "system", "content": "You are a careful logical reasoner."}
    assert "All cats are mammals.\nTom is a cat." in training[1]["content"]
    policy = branch.folio_policy_messages(model_input)
    assert policy[1]["content"] == [{"type": "text", "text": training[1]["content"]}]
    gsm8k = branch.gsm8k_training_messages({"benchmark": "gsm8k", "example_id": "g", "question": "1+1?"})
    assert gsm8k[1]["content"].endswith("Problem: 1+1?")
    humaneval = branch.humaneval_policy_messages(
        {"benchmark": "humaneval", "example_id": "h", "prompt": "def f():\n"}
    )
    assert "```python\ndef f():\n```" in humaneval[1]["content"][0]["text"]
    with pytest.raises(ValueError, match="frozen folio"):
        branch.folio_training_messages({"benchmark": "gsm8k"})


# ---------------------------------------------------------------------------
# Parsing rules
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "prediction", "malformed"),
    [
        ("True", "True", False),
        ("the conclusion is FALSE.", "False", False),
        ("Uncertain", "Uncertain", False),
        ("Based on the premises: true", "True", False),
        ("I cannot determine this", None, True),
        ("", None, True),
    ],
)
def test_folio_parsing(raw, prediction, malformed):
    assert branch.parse_folio_prediction(raw) == (prediction, malformed)
    audit = branch._audit_parse_folio(raw)
    assert (audit if prediction else None) == prediction


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("reasoning\n#### 42", "42"),
        ("total is $1,200.50\n#### $1,200.50", "1200.50"),
        ("#### 42.", "42"),
        ("no marker, answer 17 then 18", "18"),
        ("#### -5", "-5"),
    ],
)
def test_gsm8k_prediction_parsing(raw, expected):
    prediction, malformed = branch.parse_gsm8k_prediction(raw)
    assert not malformed
    assert prediction == expected
    assert branch._audit_parse_gsm8k(raw) == expected


def test_gsm8k_malformed_and_gold():
    assert branch.parse_gsm8k_prediction("no numbers at all") == (None, True)
    assert branch._audit_parse_gsm8k("no numbers at all") is None
    assert branch.parse_gsm8k_gold("work\n#### 1,000") == "1000"
    with pytest.raises(ValueError, match="####"):
        branch.parse_gsm8k_gold("missing marker")


def test_gsm8k_correct_string_then_float_tolerance():
    assert branch.gsm8k_correct("42", "42")
    assert branch.gsm8k_correct("42.0", "42")
    assert branch.gsm8k_correct("42.0000001", "42")
    assert not branch.gsm8k_correct("43", "42")
    assert branch._audit_gsm8k_equal("42.0", "42")
    assert not branch._audit_gsm8k_equal("43", "42")


# ---------------------------------------------------------------------------
# HumanEval extraction and sandbox
# ---------------------------------------------------------------------------


def test_humaneval_extraction_fenced_unfenced_empty():
    fenced = "Here is the code:\n```python\ndef add(a, b):\n    return a + b\n```\nDone."
    assert branch.extract_humaneval_code(fenced) == "def add(a, b):\n    return a + b"
    assert branch._audit_extract_humaneval(fenced) == "def add(a, b):\n    return a + b"
    raw = "def add(a, b):\n    return a + b\n"
    assert branch.extract_humaneval_code(raw) == "def add(a, b):\n    return a + b"
    assert branch.extract_humaneval_code("```python\n\n```") == ""
    assert not branch.humaneval_defines_entry_point("def other():\n    pass", "add")
    assert branch.humaneval_defines_entry_point("def add(a, b):\n    return a + b", "add")
    assert not branch.humaneval_defines_entry_point("def broken(:", "add")


def test_humaneval_extraction_unterminated_fence_matches_frozen_rule():
    # Regression: an unterminated fence is not a complete block; both paths fall back to the
    # raw output, whose ```python line breaks ast.parse, so the prediction is malformed.
    raw = "```python\ndef min_path(grid):\n    return 0\n"
    expected = raw.strip("\n").strip()
    assert branch.extract_humaneval_code(raw) == expected
    assert branch._audit_extract_humaneval(raw) == expected
    assert not branch.humaneval_defines_entry_point(branch.extract_humaneval_code(raw), "min_path")
    assert not branch._audit_defines(branch._audit_extract_humaneval(raw), "min_path")
    terminated = "Here:\n```python\ndef min_path(grid):\n    return 0\n```\nThanks."
    assert branch.extract_humaneval_code(terminated) == "def min_path(grid):\n    return 0"
    assert branch._audit_extract_humaneval(terminated) == branch.extract_humaneval_code(terminated)
    assert branch._audit_defines(branch._audit_extract_humaneval(terminated), "min_path")


@pytest.mark.parametrize(
    "raw",
    [
        "```python```",  # no newline after the marker: not a block
        "```python",  # marker only
        "```python def f():\n    pass\n```",  # no newline directly after the marker
        "```python\n\n\ndef f():\n    pass\n```",  # extra blank lines after the marker
        "```pythonX\n```python\ndef f():\n    pass\n```",  # false marker skipped, real block taken
        "```python\nbody without close\n\n```python\ndef g():\n    pass\n```",  # closes at the next fence
        "no fence at all",
        "",
    ],
)
def test_audit_extract_matches_frozen_extraction_exactly(raw):
    assert branch._audit_extract_humaneval(raw) == branch.extract_humaneval_code(raw)


@pytest.mark.parametrize(
    ("code", "entry_point", "expected"),
    [
        ("def f():\n    pass", "f", True),
        ("async def f():\n    pass", "f", True),
        ("def outer():\n    def f():\n        pass", "f", False),  # nested is not top-level
        ("class A:\n    def f(self):\n        pass", "f", False),  # method is not top-level
        ("def f(:", "f", False),  # syntax error
        ("def g():\n    pass", "f", False),
    ],
)
def test_audit_defines_agrees_with_scoring_defines(code, entry_point, expected):
    assert branch.humaneval_defines_entry_point(code, entry_point) is expected
    assert branch._audit_defines(code, entry_point) is expected


def test_humaneval_sandbox_passes_and_blocks_sockets():
    program = branch.build_humaneval_program(
        "def add(a, b):\n    return a + b",
        "def check(candidate):\n    assert candidate(1, 2) == 3",
        "add",
    )
    assert "socket.socket = _transfer_blocked_socket" in program
    outcome = branch.execute_humaneval_program(program)
    assert outcome["category"] == "passed", outcome
    blocked = branch.build_humaneval_program(
        "import socket\n\n\ndef probe():\n    return socket.socket()",
        "def check(candidate):\n    candidate()",
        "probe",
    )
    outcome = branch.execute_humaneval_program(blocked)
    assert outcome["category"] == "runtime_error"
    assert "network access is disabled" in outcome["stderr_tail"]


def test_humaneval_sandbox_wrong_answer_and_timeout():
    wrong = branch.build_humaneval_program(
        "def add(a, b):\n    return a - b",
        "def check(candidate):\n    assert candidate(1, 2) == 3",
        "add",
    )
    assert branch.execute_humaneval_program(wrong)["category"] == "wrong_answer"
    slow = branch.build_humaneval_program(
        "def spin():\n    while True:\n        pass",
        "def check(candidate):\n    candidate()",
        "spin",
    )
    outcome = branch.execute_humaneval_program(slow, wall_timeout_seconds=2, rlimit_cpu_seconds=30)
    assert outcome["category"] == "timeout"


# ---------------------------------------------------------------------------
# Admission arithmetic
# ---------------------------------------------------------------------------


def _probe(p95=1.0, load=100.0):
    return {
        "load": {"wall_seconds": load},
        "latency": {
            name: {"p95_seconds_per_example": p95} for name in branch.BENCHMARK_ORDER
        },
        "probe_gpu_hours": 0.5,
    }


def _admission(probe, spent=0.0, now=None):
    protocol = repository_protocol()
    now = time.time() if now is None else now
    cutoff = time.time() + 48 * 3600
    return branch.decide_admission(
        protocol, probe, branch_spent_gpu_hours=spent, now_epoch=now, cutoff_epoch=cutoff
    )


def test_admission_l0_l1_l2_boundaries():
    l0 = _admission(_probe())
    assert l0["decision"] == "L0" and l0["outcome"] == "PASS"
    assert l0["ledger_mutated"] is False
    expected_worker0 = (1.0 * 200 * 4 + 100.0) * 1.25 / 3600
    assert math.isclose(l0["arithmetic"]["L0"]["per_worker_seconds"]["0"], 1.0 * 200 * 4 + 100.0)
    required = l0["arithmetic"]["L0"]["required_gpu_hours"]
    assert math.isclose(required, (expected_worker0 + (1.0 * 200 * 4 + 1.0 * 164 * 4 + 100.0) * 1.25 / 3600))

    boundary = 24 - l0["arithmetic"]["L0"]["required_gpu_hours"]
    assert _admission(_probe(), spent=boundary - 0.01)["decision"] == "L0"
    l1 = _admission(_probe(), spent=boundary + 0.01)
    assert l1["decision"] == "L1" and l1["authorized_subsets"]["subset_sizes"] == branch.L1_SIZES
    l1_required = l1["arithmetic"]["L1"]["required_gpu_hours"]
    assert math.isclose(l1_required, l0["arithmetic"]["L1"]["required_gpu_hours"])
    assert _admission(_probe(), spent=24 - l1_required + 0.01)["decision"] == "L2"
    assert _admission(_probe(), spent=24 - l1_required + 0.01)["outcome"] == "VALID_STOP"

    past_cutoff = _admission(_probe(), now=time.time() + 49 * 3600)
    assert past_cutoff["decision"] == "L2"
    huge = _admission(_probe(p95=400.0))
    assert huge["arithmetic"]["L0"]["fits_per_worker_24h"] is False
    assert huge["decision"] == "L2"


def test_require_admission_gate(tmp_path):
    protocol = repository_protocol()
    root = tmp_path
    with pytest.raises(RuntimeError, match="VALID_STOP: transfer cost admission has not run"):
        branch.require_admission_gate(root, protocol)
    path = root / branch.OUTPUT_ROOT / "admission.json"
    path.parent.mkdir(parents=True)
    admission = _admission(_probe())
    admission.update(outcome="VALID_STOP", decision="L2", authorized_subsets=None)
    path.write_text(json.dumps(admission))
    with pytest.raises(RuntimeError, match="VALID_STOP: transfer admission did not authorize"):
        branch.require_admission_gate(root, protocol)
    admission = _admission(_probe())
    path.write_text(json.dumps(admission))
    assert branch.require_admission_gate(root, protocol)["decision"] == "L0"


# ---------------------------------------------------------------------------
# Journal resume and run-cell identity (fake policy, no GPU)
# ---------------------------------------------------------------------------


class FakeTokenizer:
    def __call__(self, text, add_special_tokens=False):
        return {"input_ids": list(range(len(text.split())))}


class FakePolicy:
    def __init__(self):
        self.processor = SimpleNamespace(tokenizer=FakeTokenizer())
        self.max_new_tokens = 64
        self.calls = []

    def input_token_length(self, request):
        return 10

    def generate_many(self, requests):
        self.calls.append([request.instance_id for request in requests])
        return [f"output:{request.adapter_id}:{request.instance_id}" for request in requests]


def _fake_protocol():
    return {
        "protocol_id": branch.PROTOCOL_ID,
        "base_model": {"model_id": "m", "revision": "r"},
        "cells": {
            "base": {"adapter_id": None},
            **{
                cell: {"adapter_id": cell, "checkpoint": f"adapters/{cell}"}
                for cell in branch.ADAPTED_CELLS
            },
        },
    }


def _fake_subsets(n=6):
    entries = {}
    order = []
    for index in range(n):
        example_id = f"folio-{index}"
        order.append(example_id)
        model_input = {
            "benchmark": "folio",
            "example_id": example_id,
            "premises": [f"premise {index}"],
            "conclusion": f"conclusion {index}",
        }
        prompt = branch.rendered_prompt("folio", model_input)
        entries[example_id] = {
            "example_id": example_id,
            "source_index": index,
            "stratum": "True",
            "model_input": model_input,
            "system": prompt["system"],
            "user": prompt["user"],
            "input_tokens": 10,
            "gold": {"label": "True"},
        }
    return {
        "schema_version": branch.SUBSETS_SCHEMA,
        "protocol_id": branch.PROTOCOL_ID,
        "benchmarks": {
            "folio": {"l0_order": order, "l1_order": branch.l1_order(order), "max_new_tokens": 64, "examples": entries}
        },
    }


def test_run_cell_journals_and_resumes_completed_keys(tmp_path):
    protocol = _fake_protocol()
    subsets = _fake_subsets(6)
    ids = subsets["benchmarks"]["folio"]["l0_order"]
    policy = FakePolicy()
    report = branch.run_cell(
        tmp_path, protocol, subsets, policy,
        benchmark="folio", cell="base", ids=ids, level="L0", fingerprints={},
    )
    assert report["examples"] == 6
    assert len(report["entries"]) == 6
    assert all(value.startswith("output:None:") for value in (e["raw_output"] for e in report["entries"].values()))

    final, journal = branch._run_paths(tmp_path, "folio", "base")
    assert final.is_file() and not journal.exists()
    second = FakePolicy()
    retained = branch.run_cell(
        tmp_path, protocol, subsets, second,
        benchmark="folio", cell="base", ids=ids, level="L0", fingerprints={},
    )
    assert retained == report
    assert second.calls == []

    final.unlink()
    kept = {key: report["entries"][key] for key in ids[:4]}
    from examples.planning_benchmark_slice.modality_view_preparation import write_json

    write_json(
        journal,
        {
            **branch._run_identity(protocol, "folio", "base", "L0", 64, {}),
            "schema_version": branch.RUN_JOURNAL_SCHEMA,
            "entries": kept,
            "started": 1.0,
            "resumptions": 0,
        },
    )
    resumed = FakePolicy()
    result = branch.run_cell(
        tmp_path, protocol, subsets, resumed,
        benchmark="folio", cell="base", ids=ids, level="L0", fingerprints={},
    )
    regenerated = {key for call in resumed.calls for key in call}
    assert regenerated == set(ids[4:])
    for key in ids[:4]:
        assert result["entries"][key] == kept[key]
    assert result["order"] == ids
    assert not journal.exists()

    final.unlink()
    write_json(
        journal,
        {
            **branch._run_identity(protocol, "folio", "bfs_text", "L0", 64, {}),
            "schema_version": branch.RUN_JOURNAL_SCHEMA,
            "entries": {},
            "started": 1.0,
            "resumptions": 0,
        },
    )
    with pytest.raises(ValueError, match="partial journal identity differs"):
        branch.run_cell(
            tmp_path, protocol, subsets, FakePolicy(),
            benchmark="folio", cell="base", ids=ids, level="L0", fingerprints={},
        )


# ---------------------------------------------------------------------------
# audit-score re-execution time budget (scheduler hooks are capped at 300s)
# ---------------------------------------------------------------------------


def _fake_humaneval_scored_root(tmp_path, monkeypatch, n=30):
    """Fabricate freeze/subsets/run/scores evidence for one humaneval cell."""
    protocol = _fake_protocol()
    entries = {}
    order = []
    run_entries = {}
    for index in range(n):
        example_id = f"HumanEval/{index}"
        order.append(example_id)
        model_input = {"benchmark": "humaneval", "example_id": example_id, "prompt": f"def f_{index}():\n"}
        prompt = branch.rendered_prompt("humaneval", model_input)
        entries[example_id] = {
            "example_id": example_id,
            "source_index": index,
            "stratum": "all",
            "model_input": model_input,
            "system": prompt["system"],
            "user": prompt["user"],
            "input_tokens": 10,
            "gold": {
                "test": "def check(candidate):\n    assert candidate() is not None\n",
                "entry_point": f"f_{index}",
            },
        }
        run_entries[example_id] = {
            "raw_output": f"def f_{index}():\n    return {index}",
            "input_tokens": 10,
            "generated_tokens": 8,
            "batch_size": 1,
            "batch_latency_seconds": 0.5,
        }
    subsets = {
        "schema_version": branch.SUBSETS_SCHEMA,
        "protocol_id": branch.PROTOCOL_ID,
        "benchmarks": {
            "folio": {"l0_order": [], "l1_order": [], "max_new_tokens": 64, "examples": {}},
            "gsm8k": {"l0_order": [], "l1_order": [], "max_new_tokens": 512, "examples": {}},
            "humaneval": {
                "l0_order": order,
                "l1_order": branch.l1_order(order),
                "max_new_tokens": 768,
                "examples": entries,
            },
        },
    }
    write_json(tmp_path / branch.OUTPUT_ROOT / "subsets.json", subsets)
    write_json(tmp_path / branch.OUTPUT_ROOT / "freeze.json", {"sandbox": {"unshare_network_available": False}})
    final, _journal = branch._run_paths(tmp_path, "humaneval", "base")
    write_json(
        final,
        {
            **branch._run_identity(protocol, "humaneval", "base", "L0", 768, {}),
            "examples": n,
            "order": order,
            "entries": run_entries,
            "generated_tokens_total": 8 * n,
            "input_tokens_total": 10 * n,
            "started": 1.0,
            "finished_at": 2.0,
        },
    )
    monkeypatch.setattr(
        branch,
        "execute_humaneval_program",
        lambda program, **kwargs: {"category": "passed", "wall_seconds": 0.01, "returncode": 0, "stderr_tail": ""},
    )
    branch.score_stage(tmp_path, protocol)
    monkeypatch.undo()
    return protocol


def test_audit_score_resample_time_budget_skips_slow_executions(tmp_path, monkeypatch):
    protocol = _fake_humaneval_scored_root(tmp_path, monkeypatch, n=30)
    calls = []

    def slow(program, **kwargs):
        calls.append(program)
        time.sleep(0.4)
        return {"category": "passed", "wall_seconds": 0.4, "returncode": 0, "stderr_tail": ""}

    monkeypatch.setattr(branch, "execute_humaneval_program", slow)
    started = time.monotonic()
    result = branch.audit_score_stage(tmp_path, protocol, resample_budget_seconds=0.7)
    elapsed = time.monotonic() - started
    resample = result["humaneval_resample"]
    assert result["outcome"] == "PASS"
    assert resample["planned"] == 3  # positions 0, 10, 20 of the frozen order
    assert resample["re_executed"] == len(resample["executions"]) == len(calls)
    assert 0 < resample["re_executed"] < resample["planned"]
    assert resample["skipped_for_time"] == resample["planned"] - resample["re_executed"]
    assert resample["complete"] is False
    assert elapsed < 30


def test_audit_score_resample_detects_mismatch_on_executed_samples(tmp_path, monkeypatch):
    protocol = _fake_humaneval_scored_root(tmp_path, monkeypatch, n=20)
    monkeypatch.setattr(
        branch,
        "execute_humaneval_program",
        lambda program, **kwargs: {
            "category": "runtime_error",
            "wall_seconds": 0.01,
            "returncode": 1,
            "stderr_tail": "boom",
        },
    )
    with pytest.raises(RuntimeError, match="sandbox re-execution differs"):
        branch.audit_score_stage(tmp_path, protocol, resample_budget_seconds=60)
    from examples.planning_benchmark_slice.scene_assets import read_json

    result = read_json(tmp_path / branch.OUTPUT_ROOT / "audit-score.json")
    resample = result["humaneval_resample"]
    assert result["outcome"] == "INVALID"
    assert resample["planned"] == 2  # positions 0, 10
    assert resample["re_executed"] == 2
    assert resample["skipped_for_time"] == 0
    assert resample["complete"] is True
    assert all(row["reexecuted"] == "runtime_error" for row in resample["executions"])
    assert len(result["problems"]) == 2


# ---------------------------------------------------------------------------
# Freeze idempotency on synthetic fixtures (no network)
# ---------------------------------------------------------------------------


def _fixture_protocol(tmp_path):
    folio_rows = [
        {"premises": [f"premise {i} share"], "conclusion": f"conclusion {i}", "label": label}
        for i, label in enumerate(["True", "Uncertain", "False"] * 68)
    ]
    gsm8k_rows = [
        {"question": f"question {i}", "answer": f"step {'<<s>>' * (i % 5)}\n#### {i}"} for i in range(1319)
    ]
    humaneval_rows = [
        {
            "task_id": f"HumanEval/{i}",
            "prompt": f"def f_{i}():\n",
            "test": "def check(candidate):\n    pass\n",
            "entry_point": f"f_{i}",
            "canonical_solution": "",
        }
        for i in range(164)
    ]
    files = {}
    folio_path = tmp_path / "folio.jsonl"
    folio_path.write_text("\n".join(json.dumps(row) for row in folio_rows) + "\n")
    files["folio"] = folio_path
    import pandas as pd

    gsm8k_path = tmp_path / "gsm8k.parquet"
    pd.DataFrame(gsm8k_rows).to_parquet(gsm8k_path)
    files["gsm8k"] = gsm8k_path
    humaneval_path = tmp_path / "humaneval.parquet"
    pd.DataFrame(humaneval_rows).to_parquet(humaneval_path)
    files["humaneval"] = humaneval_path
    protocol = {
        "schema": branch.PROTOCOL_SCHEMA,
        "protocol_id": branch.PROTOCOL_ID,
        "frozen_at_utc": "2026-09-19T00:00:00Z",
        "allocation_gpu_hours": 24,
        "base_model": {"model_id": "m", "revision": "r"},
        "cells": {"base": {"adapter_id": None}},
        "benchmarks": {
            name: {
                "official_source": {
                    "sha256": branch._sha256_path(path),
                    "examples": {"folio": 204, "gsm8k": 1319, "humaneval": 164}[name],
                    **({"commit": "c", "path": "p"} if name == "folio" else {"revision": "r", "file": "f"}),
                },
                "subset_size": {"folio": 200, "gsm8k": 200, "humaneval": 164}[name],
                "max_new_tokens": {"folio": 64, "gsm8k": 512, "humaneval": 768}[name],
            }
            for name, path in files.items()
        },
    }
    return protocol, files


def test_freeze_idempotent_on_synthetic_fixtures(tmp_path, monkeypatch):
    protocol, files = _fixture_protocol(tmp_path)
    monkeypatch.setattr(branch, "validate_protocol", lambda root, proto: {"outcome": "PASS"})
    monkeypatch.setattr(
        branch,
        "_download",
        lambda root, proto, name: {
            "url": "fixture",
            "sha256": proto["benchmarks"][name]["official_source"]["sha256"],
            "path": "fixture",
            "downloaded": False,
        },
    )

    class FakeProcessor:
        tokenizer = SimpleNamespace(
            apply_chat_template=lambda messages, tokenize=True, add_generation_prompt=True: list(
                range(sum(len(message["content"].split()) for message in messages))
            )
        )

    monkeypatch.setattr(branch, "frozen_processor", lambda root, proto: FakeProcessor())
    monkeypatch.setattr(branch, "_load_benchmark_rows", lambda root, name: {
        "folio": [json.loads(line) for line in (files["folio"]).read_text().splitlines()],
        "gsm8k": __import__("pandas").read_parquet(files["gsm8k"]).to_dict(orient="records"),
        "humaneval": __import__("pandas").read_parquet(files["humaneval"]).to_dict(orient="records"),
    }[name])
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir(parents=True)
    corpus = corpus_dir / "report.json"
    record_file = corpus_dir / "records.jsonl.gz"
    with gzip.open(record_file, "wt") as stream:
        stream.write(json.dumps({"record_id": "r0", "authoritative_input": {"planning": "bfs"}}) + "\n")
    corpus.write_text(json.dumps({"results": [{"path": str(record_file), "records": 1}]}))
    monkeypatch.setattr(branch, "CORPUS_REPORT", str(corpus))
    monkeypatch.setattr(branch, "probe_unshare_network", lambda: False)

    first = branch.freeze_stage(tmp_path, protocol)
    assert first["outcome"] == "PASS"
    assert first["subsets"]["folio"]["l0_size"] == 200
    assert first["subsets"]["gsm8k"]["l0_size"] == 200
    assert first["subsets"]["humaneval"]["l0_size"] == 164
    assert first["leakage"]["items_with_shared_ngrams"] == 0
    subsets_path = tmp_path / branch.OUTPUT_ROOT / "subsets.json"
    digest = subsets_path.read_bytes()
    second = branch.freeze_stage(tmp_path, protocol)
    assert subsets_path.read_bytes() == digest
    assert second["subsets"]["folio"]["l0_order"] == first["subsets"]["folio"]["l0_order"]

    subsets_path.write_text("{}")
    with pytest.raises(RuntimeError, match="byte-reproducible"):
        branch.freeze_stage(tmp_path, protocol)


def test_leakage_check_reports_shared_ngrams(tmp_path):
    record_file = tmp_path / "records.jsonl"
    record_file.write_text(json.dumps({"text": "alpha beta gamma delta epsilon zeta eta theta iota kappa"}) + "\n")
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"results": [{"path": str(record_file), "records": 1}]}))
    inputs = {
        "hit": "alpha beta gamma delta epsilon zeta eta theta and more words here",
        "miss": "completely unrelated benchmark question text",
    }
    result = branch.leakage_check(tmp_path, str(report), inputs)
    assert result["records_scanned"] == 1
    assert result["items_with_shared_ngrams"] == 1
    assert result["matches"]["hit"] == ["alpha beta gamma delta epsilon zeta eta theta"]


# ---------------------------------------------------------------------------
# v2 extension: protocol-driven layout, byte-identical subset reuse, v1 regression
# ---------------------------------------------------------------------------

PROTOCOL_V2_PATH = ROOT / "configs/experiments/expanded-study/transfer-protocol-v2.json"


def repository_protocol_v2():
    return json.loads(PROTOCOL_V2_PATH.read_text())


def test_protocol_driven_layout_helpers():
    fake = _fake_protocol()
    assert branch.cell_order(fake) == branch.CELL_ORDER
    assert branch.adapted_cells(fake) == branch.ADAPTED_CELLS
    assert branch.output_root(fake) == branch.OUTPUT_ROOT
    assert branch.doc_stem(fake) == "transfer"
    assert branch.worker_benchmarks(fake) == branch.WORKER_BENCHMARKS
    assert branch.worker_gpus(fake) == branch.WORKER_GPUS
    assert branch.l0_sizes(fake) == branch.L0_SIZES
    assert branch.l1_sizes(fake) == branch.L1_SIZES
    assert branch.subsets_reference(fake) is None

    v2 = repository_protocol_v2()
    order = branch.cell_order(v2)
    assert order == tuple(v2["execution_topology"]["cell_order_per_benchmark"])
    assert len(order) == 9 and "base" not in order
    assert branch.adapted_cells(v2) == order
    assert branch.output_root(v2) == "outputs/expanded-study/v1/transfer-v2"
    assert branch.doc_stem(v2) == "transfer-v2"
    assert branch.worker_benchmarks(v2) == {0: ("gsm8k",), 1: ("folio", "humaneval")}
    assert branch.worker_gpus(v2) == {0: 0, 1: 1}
    assert branch.l0_sizes(v2) == branch.L0_SIZES
    assert branch.l1_sizes(v2) == branch.L1_SIZES
    reference = branch.subsets_reference(v2)
    assert reference == {
        "path": f"{branch.OUTPUT_ROOT}/subsets.json",
        "sha256": branch.V1_SUBSETS_SHA256,
    }

    custom = {
        "protocol_id": "custom",
        "cells": {"x": {"adapter_id": "x"}, "y": {"adapter_id": "y"}},
        "execution_topology": {
            "cell_order_per_benchmark": ["x", "y"],
            "workers": {"custom-run-0": {"gpu": 3, "benchmarks": ["folio"]}},
        },
        "evidence": {"output_root": "outputs/tmp/custom"},
    }
    assert branch.cell_order(custom) == ("x", "y")
    assert branch.adapted_cells(custom) == ("x", "y")
    assert branch.output_root(custom) == "outputs/tmp/custom"
    assert branch.doc_stem(custom) == "custom"
    assert branch.worker_benchmarks(custom) == {0: ("folio",)}
    assert branch.worker_gpus(custom) == {0: 3}


def test_repository_protocol_v2_validates_against_live_repo():
    report = branch.validate_protocol(ROOT, repository_protocol_v2())
    assert report["outcome"] == "PASS"
    assert report["extends"] == branch.PROTOCOL_ID
    assert sorted(report["adapter_paths"]) == sorted(branch.cell_order(repository_protocol_v2()))
    assert report["l0_sizes"] == {"folio": 200, "gsm8k": 200, "humaneval": 164}
    assert report["l1_sizes"] == {"folio": 100, "gsm8k": 100, "humaneval": 82}
    assert report["worker_benchmarks"] == {"0": ["gsm8k"], "1": ["folio", "humaneval"]}

    changed = repository_protocol_v2()
    changed["cells"]["iw_text"]["checkpoint"] = "missing/checkpoint"
    with pytest.raises(ValueError, match="extension protocol validation failed"):
        branch.validate_protocol(ROOT, changed)
    changed = repository_protocol_v2()
    changed["evidence"]["output_root"] = branch.OUTPUT_ROOT
    with pytest.raises(ValueError, match="extension protocol validation failed"):
        branch.validate_protocol(ROOT, changed)
    changed = repository_protocol_v2()
    changed["benchmarks"]["subsets_reference"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="extension protocol validation failed"):
        branch.validate_protocol(ROOT, changed)


def test_v1_admission_regression_byte_identical():
    """The parameterized code must reproduce the published v1 admission decision exactly."""
    from examples.planning_benchmark_slice.expanded_scheduler import timestamp

    protocol = repository_protocol()
    out = ROOT / branch.OUTPUT_ROOT
    probe = json.loads((out / "probe.json").read_text())
    admission = json.loads((out / "admission.json").read_text())
    schedule = json.loads((ROOT / branch.SCHEDULE_DOC).read_text())
    decision = branch.decide_admission(
        protocol,
        probe,
        branch_spent_gpu_hours=admission["branch_spent_gpu_hours"],
        now_epoch=admission["decided_at"],
        cutoff_epoch=timestamp(schedule["gpu_cutoff_utc"]),
    )
    assert decision == admission
    assert json.dumps(decision, indent=2) + "\n" == (out / "admission.json").read_text()


def test_extension_admission_remainder_arithmetic():
    protocol = repository_protocol_v2()
    probe = _probe()
    now = time.time()
    decision = branch.decide_admission(
        protocol, probe, branch_spent_gpu_hours=1.5, now_epoch=now, cutoff_epoch=now + 48 * 3600
    )
    assert math.isclose(decision["branch_remainder_gpu_hours"], 22.5)
    assert math.isclose(decision["arithmetic"]["L0"]["per_worker_seconds"]["0"], 1.0 * 200 * 9 + 100.0)
    assert math.isclose(
        decision["arithmetic"]["L1"]["per_worker_seconds"]["1"], 1.0 * 100 * 9 + 1.0 * 82 * 9 + 100.0
    )
    assert decision["arithmetic"]["L0"]["subset_sizes"] == branch.L0_SIZES
    assert decision["arithmetic"]["L1"]["subset_sizes"] == branch.L1_SIZES
    boundary = 24 - decision["arithmetic"]["L0"]["required_gpu_hours"]
    flipped = branch.decide_admission(
        protocol, probe, branch_spent_gpu_hours=boundary + 0.01, now_epoch=now, cutoff_epoch=now + 48 * 3600
    )
    assert flipped["decision"] == "L1"


def _fixture_extension_protocol(tmp_path, subsets_bytes):
    import hashlib

    digest = hashlib.sha256(subsets_bytes).hexdigest()
    v1_root = tmp_path / branch.OUTPUT_ROOT
    v1_root.mkdir(parents=True, exist_ok=True)
    (v1_root / "subsets.json").write_bytes(subsets_bytes)
    write_json(
        v1_root / "freeze.json",
        {
            "outcome": "PASS",
            "leakage": {
                "records_scanned": 3,
                "benchmark_inputs": 2,
                "items_with_shared_ngrams": 0,
                "report": "leakage.json",
            },
        },
    )
    write_json(v1_root / "leakage.json", {"schema_version": branch.LEAKAGE_SCHEMA, "matches": {}})
    protocol = {
        "protocol_id": "transfer-extension-test-v2",
        "extends": branch.PROTOCOL_ID,
        "frozen_at_utc": "2026-09-19T00:00:00Z",
        "base_model": {"model_id": "m", "revision": "r"},
        "cells": {"x": {"adapter_id": "x", "checkpoint": "adapters/x"}},
        "benchmarks": {
            "inherit": branch.PROTOCOL_ID,
            "subsets_reference": {"path": f"{branch.OUTPUT_ROOT}/subsets.json", "sha256": digest},
            "subset_sizes": dict(branch.L0_SIZES),
            "l1_subset_sizes": dict(branch.L1_SIZES),
        },
        "execution_topology": {"cell_order_per_benchmark": ["x"]},
        "evidence": {"output_root": "outputs/expanded-study/v1/transfer-v2-test"},
    }
    return protocol, digest


def _minimal_subsets_bytes():
    benchmarks = {}
    for name, ids in (("folio", ["f0", "f1"]), ("gsm8k", ["g0", "g1"]), ("humaneval", ["h0", "h1"])):
        benchmarks[name] = {
            "l0_order": ids,
            "l1_order": ids[::2],
            "max_new_tokens": 64,
            "examples": {example_id: {"input_tokens": 10} for example_id in ids},
        }
    return (json.dumps({"schema_version": branch.SUBSETS_SCHEMA, "protocol_id": branch.PROTOCOL_ID,
                        "benchmarks": benchmarks}, indent=2) + "\n").encode()


def test_extension_freeze_verifies_and_copies_byte_identically(tmp_path, monkeypatch):
    protocol, digest = _fixture_extension_protocol(tmp_path, _minimal_subsets_bytes())
    monkeypatch.setattr(branch, "validate_protocol", lambda root, proto: {"outcome": "PASS"})
    monkeypatch.setattr(branch, "probe_unshare_network", lambda: False)

    freeze = branch.freeze_stage(tmp_path, protocol)
    out = tmp_path / "outputs/expanded-study/v1/transfer-v2-test"
    assert freeze["outcome"] == "PASS"
    assert freeze["method"].startswith("referenced-v1")
    assert (out / "subsets.json").read_bytes() == (tmp_path / branch.OUTPUT_ROOT / "subsets.json").read_bytes()
    assert freeze["subsets_reference"]["verified_sha256"] == "sha256:" + digest
    assert freeze["subsets_reference"]["byte_identical"] is True
    assert freeze["leakage"]["status"] == "inherited_from_v1"
    assert freeze["leakage"]["records_scanned"] == 3
    assert freeze["subsets"]["folio"]["l0_size"] == 2
    assert (out / "leakage.json").is_file()

    audit = branch.audit_freeze_stage(tmp_path, protocol)
    assert audit["outcome"] == "PASS"
    assert all(audit["comparisons"].values())

    # A tampered pin fails closed before anything is written.
    tampered = json.loads(json.dumps(protocol))
    tampered["benchmarks"]["subsets_reference"]["sha256"] = "0" * 64
    tampered["evidence"]["output_root"] = "outputs/expanded-study/v1/transfer-v2-tampered"
    with pytest.raises(RuntimeError, match="freeze refused"):
        branch.freeze_stage(tmp_path, tampered)
    assert not (tmp_path / "outputs/expanded-study/v1/transfer-v2-tampered").exists()

    # An extension refusing to overwrite a divergent subsets.json.
    (out / "subsets.json").write_text("{}")
    with pytest.raises(RuntimeError, match="byte-reproducible"):
        branch.freeze_stage(tmp_path, protocol)
