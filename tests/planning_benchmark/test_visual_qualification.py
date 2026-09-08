"""Fast qualification timing regression; no model weights or GPU launches."""

from types import SimpleNamespace

import pytest

from examples.planning_benchmark_slice import visual_jobs as jobs
from examples.planning_benchmark_slice.visual_experiment import VisualExperiment


@pytest.mark.parametrize("seconds_per_call", [5.0, 30.0])
def test_qualification_reaches_training_probe_without_redundant_generation(monkeypatch, tmp_path, seconds_per_call):
    experiment = VisualExperiment()
    experiment.output = tmp_path
    clock = [0.0]
    calls = []
    records = [
        {
            "record_id": str(i),
            "algorithm": "bfs",
            "tokens": {"input": {"text-state": 1000, "visual-state": 1000, "multimodal-state": 1000}},
        }
        for i in range(31)
    ]

    class TrainingReached(Exception):
        pass

    class Policy:
        stop_at = float("inf")

        def generate(self, examples, *args, **kwargs):
            if clock[0] >= self.stop_at:
                raise RuntimeError("VALID_STOP: no new model calls after cutoff")
            calls.append(len(examples))
            clock[0] += seconds_per_call
            return ["operation"] * len(examples)

    def training(config):
        raise TrainingReached

    monkeypatch.setattr(jobs.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(experiment, "deadline", lambda *args: 7200.0 if seconds_per_call == 30 else 3600.0)
    monkeypatch.setattr(jobs, "select_probes", lambda e: records)
    monkeypatch.setattr(jobs, "make_policy", lambda *args: Policy())
    monkeypatch.setattr(jobs, "probe_examples", lambda e, records, *args: records)
    monkeypatch.setattr(jobs, "SemanticProbe", lambda e: SimpleNamespace(evaluate=lambda *args: "same"))
    monkeypatch.setattr(jobs, "load_training_model", training)
    import torch

    monkeypatch.setattr(torch.cuda, "synchronize", lambda: None)
    monkeypatch.setattr(torch.cuda, "empty_cache", lambda: None)
    with pytest.raises(TrainingReached):
        jobs.qualify_device(experiment, 0, lambda *args, **kwargs: None)
    assert len(calls) <= 31 * 5
    assert len(list((tmp_path / "qualification/worker-0-probes").glob("*.json"))) == 31
    if seconds_per_call == 30:
        assert clock[0] > 3600


@pytest.mark.parametrize("mismatch", [None, "batch", "repeat"])
def test_qualification_checks_every_batch_position_with_only_distinct_scalars(mismatch):
    records = [{"record_id": str(i % 2)} for i in range(8)]
    calls = []

    class Policy:
        def generate(self, examples, adapter):
            assert adapter == "trained"
            calls.append(len(examples))
            outputs = [e["record_id"] for e in examples]
            if (mismatch == "batch" and len(calls) == 3) or (mismatch == "repeat" and len(calls) == 4):
                outputs[-1] = "wrong_operation"
            return outputs

    def run():
        jobs.qualify_batch(
            Policy(),
            records,
            records,
            SimpleNamespace(evaluate=lambda r, value: value),
            lambda *args, **kwargs: None,
            "trained",
        )

    if mismatch:
        with pytest.raises(ValueError, match="trusted runtime result differs"):
            run()
    else:
        run()
        assert calls == [1, 1, 8, 8]
