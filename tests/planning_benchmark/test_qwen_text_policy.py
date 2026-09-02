from __future__ import annotations

import json
from contextlib import nullcontext

import pytest
import torch

from examples.planning_benchmark_slice.qwen_text_policy import (
    BatchedPolicyAdapter,
    QwenTextPolicy,
    qwen_text_policy_messages,
    qwen_text_policy_training_messages,
)


def test_batched_policy_rejects_batch_shape_sensitive_bfloat16_inference() -> None:
    with pytest.raises(ValueError, match="float32"):
        BatchedPolicyAdapter(
            model_id="fixture",
            revision="fixture",
            adapter_paths={},
            inference_dtype="bfloat16",
        )


def test_qwen_policy_prompt_preserves_canonical_model_input_and_runtime_boundary() -> None:
    model_input = {
        "search_memory": {"visited": ["b", "a"], "frontier": ["a"]},
        "goal_atoms": ["on(a,b)"],
        "observation": {"state_id": "a", "state_atoms": ["clear(a)"]},
    }

    messages = qwen_text_policy_messages(model_input)

    assert [message["role"] for message in messages] == ["system", "user"]
    system = messages[0]["content"][0]["text"]
    assert "trusted runtime" in system
    assert "runtime_result: null" in system
    assert "Invalid operations consume" in system
    assert '"source_state_id":"<id>"' in system
    assert '"operation_type":"retire_frontier"' in system
    user = messages[1]["content"][0]["text"]
    assert json.loads(user) == model_input
    assert user == json.dumps(model_input, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    training_messages = qwen_text_policy_training_messages(model_input, {"typed_operation": {}})
    assert [message["content"] for message in messages] == [
        [{"type": "text", "text": training_messages[0]["content"]}],
        [{"type": "text", "text": training_messages[1]["content"]}],
    ]
    assert json.loads(training_messages[2]["content"]) == {"typed_operation": {}}


def test_greedy_policy_memoizes_identical_unchanged_inputs() -> None:
    class Inputs(dict[str, torch.Tensor]):
        def to(self, _device: str) -> "Inputs":
            return self

    class Processor:
        def apply_chat_template(self, *_args: object, **_kwargs: object) -> Inputs:
            return Inputs(input_ids=torch.tensor([[1, 2]]))

        def batch_decode(self, *_args: object, **_kwargs: object) -> list[str]:
            return ["decision"]

    class Model:
        calls = 0

        def generate(self, **_kwargs: object) -> torch.Tensor:
            self.calls += 1
            return torch.tensor([[1, 2, 3]])

    policy = object.__new__(QwenTextPolicy)
    policy._torch = type("Torch", (), {"inference_mode": staticmethod(nullcontext)})()
    policy.device = "cpu"
    policy.max_new_tokens = 4
    policy._output_cache = {}
    policy.processor = Processor()
    policy.model = Model()
    model_input = {"goal_atoms": [], "observation": {}, "search_memory": {}}

    assert policy(model_input) == "decision"
    assert policy(model_input) == "decision"
    assert policy.model.calls == 1
