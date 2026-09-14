"""The frozen expanded baseline covers every cell exactly once."""

from examples.planning_benchmark_slice.expanded_baseline import assigned_bindings, bindings, validate_protocol
from examples.planning_benchmark_slice.expanded_scheduler import ROOT, read


def test_frozen_baseline_binding_partition_and_checkpoint_contract():
    protocol = read(ROOT / "configs/experiments/expanded-study/baseline-protocol.json")
    protocol["root"] = str(ROOT)
    panel, _, readiness = validate_protocol(ROOT, protocol)
    declared = bindings(panel, protocol)
    assert len(declared) == 1152
    assert len({(b["modality"], b["algorithm"], b["condition"], b["task_id"]) for b in declared}) == 1152
    parts = [
        assigned_bindings(panel, protocol, worker, kind)
        for kind in ("controls", "models")
        for worker in range(2)
    ]
    assert all(len(part) == 288 for part in parts)
    assert sorted(b["index"] for part in parts for b in part) == list(range(1152))
    assert len(readiness["checkpoints"]) == 12
