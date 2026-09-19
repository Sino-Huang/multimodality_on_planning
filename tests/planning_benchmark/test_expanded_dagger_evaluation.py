from types import SimpleNamespace

from examples.planning_benchmark_slice import expanded_dagger_evaluation as evaluation


def protocol():
    return {
        "protocol_id": "test-dagger",
        "output_root": "dagger",
        "checkpoint_lineage": {"dagger_iteration_2": "checkpoints/{modality}"},
        "evaluation": {"seed": 17},
        "model": {
            "id": "model",
            "revision": "revision",
            "maximum_input_tokens": 100,
            "output_tokens": 10,
        },
    }


class Views:
    read_only = False

    def __init__(self, task_id):
        self.task_id = task_id

    def observe(self, raw, algorithm, *, modality, pixels=True):
        return {
            "messages": [],
            "images": [],
            "binding": {"state": raw["step"], "input_pages": [], "input_tokens": 1},
            "task_id": self.task_id,
        }

    def save(self):
        pass


class Session:
    def __init__(self, root, row, algorithm, arm, seed, output, contract, *, views):
        self.row = row
        self.algorithm = algorithm
        self.arm = arm
        self.step = 0
        self.pending = None
        self.events = []

    def next_request(self):
        if self.step == 2:
            return None
        if self.pending is None:
            self.pending = SimpleNamespace(model_input={"task_id": self.row["task_id"], "step": self.step})
        return self.pending

    def submit(self, output, binding):
        raw = dict(self.pending.model_input)
        self.events.append(
            {
                "index": len(self.events),
                "input": raw,
                "raw_output": output,
                "accepted": True,
                "view": binding,
                "successor_state": self.step + 1,
            }
        )
        self.step += 1
        self.pending = None

    def result(self):
        return {
            "invariant_valid_success": True,
            "goal_reached": True,
            "algorithm_invariants_hold": True,
            "decision_count": self.step,
            "expansion_count": self.step,
            "invalid_operation_count": 0,
            "invalid_operation_rate": 0,
            "model_call_limit": 4,
            "termination_reason": "goal_reached",
        }


def test_evaluation_uses_one_request_per_task_per_round_and_resumes_completed(tmp_path, monkeypatch):
    tasks = [{"row": {"task_id": name}} for name in ("task/a", "task/b", "task/c")]
    monkeypatch.setattr(evaluation, "VisualSession", Session)
    monkeypatch.setattr(
        evaluation,
        "_views",
        lambda root, protocol, panel, task, output, endpoint, read_only=False: Views(task["row"]["task_id"]),
    )
    monkeypatch.setattr(evaluation, "replay_visual_episode", lambda root, row, report, views: report["result"])
    batches = []

    def generate(examples):
        batches.append([example["task_id"] for example in examples])
        return ["output"] * len(examples), [1] * len(examples)

    reports = evaluation.run_cell(
        tmp_path,
        protocol(),
        panel="development",
        modality="text-state",
        arm="dagger_iteration_2",
        tasks=tasks,
        endpoint="unused",
        generate=generate,
        progress=lambda **kwargs: None,
    )
    assert batches == [["task/a", "task/b"], ["task/c"], ["task/a", "task/b"], ["task/c"]]
    assert [report["task_id"] for report in reports] == ["task/a", "task/b", "task/c"]
    assert all(report["result"]["decision_count"] == 2 for report in reports)
    assert all(len(report["call_measurements"]) == 2 for report in reports)

    retained = evaluation.run_cell(
        tmp_path,
        protocol(),
        panel="development",
        modality="text-state",
        arm="dagger_iteration_2",
        tasks=tasks,
        endpoint="unused",
        generate=lambda examples: (_ for _ in ()).throw(AssertionError("retained episode generated")),
        progress=lambda **kwargs: None,
    )
    assert retained == reports
