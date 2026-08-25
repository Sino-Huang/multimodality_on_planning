"""Qwen3-VL text-state policy adapter for governed search episodes."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

QWEN_TEXT_POLICY_SYSTEM_PROMPT = """You are a Search Process Policy executing BFS through a trusted runtime.
Return exactly one JSON object with these fields:
- canonical_rationale: a short non-authoritative string
- typed_operation: one typed search operation matching the supplied search-memory contract
- runtime_result: null, because the trusted runtime—not you—computes the result
typed_operation must be exactly one of:
- transition: {"source_state_id":"<id>","action":{"name":"<name>","args":["<arg>"]},
  "frontier_intent":{"retire_source":true,"target_position":0},
  "visit_target":true,"evaluate_target":false}
- {"operation_type":"retire_frontier","state_id":"<id>"}
Copy state IDs from the input. Append successors at the BFS frontier tail. Retire the frontier head exactly once.
Do not use Markdown fences or add text outside the JSON object. Invalid operations consume the episode budget."""


def qwen_text_policy_training_messages(
    model_input: Mapping[str, Any],
    target: Mapping[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Build the canonical text messages consumed by process-SFT conversion."""
    canonical_input = json.dumps(
        dict(model_input),
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    messages = [
        {"role": "system", "content": QWEN_TEXT_POLICY_SYSTEM_PROMPT},
        {"role": "user", "content": canonical_input},
    ]
    if target is not None:
        messages.append(
            {
                "role": "assistant",
                "content": json.dumps(
                    dict(target),
                    allow_nan=False,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            }
        )
    return messages


def qwen_text_policy_messages(model_input: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Build the text-only chat presented to both base and adapted policies."""

    return [
        {
            "role": message["role"],
            "content": [{"type": "text", "text": message["content"]}],
        }
        for message in qwen_text_policy_training_messages(model_input)
    ]


class QwenTextTokenCounter:
    """Pinned chat-template token counter shared by corpus qualification and release."""

    def __init__(self, processor: Any) -> None:
        self.tokenizer = processor.tokenizer

    def __call__(self, model_input: Mapping[str, Any]) -> int:
        return len(
            self.tokenizer.apply_chat_template(
                qwen_text_policy_training_messages(model_input),
                tokenize=True,
                add_generation_prompt=True,
            )
        )


def load_qwen_text_token_counter(*, model_id: str, revision: str) -> QwenTextTokenCounter:
    from transformers import AutoProcessor

    return QwenTextTokenCounter(AutoProcessor.from_pretrained(model_id, revision=revision))


class QwenTextPolicy:
    """Load one frozen Qwen3-VL checkpoint and emit one model decision per call."""

    def __init__(
        self,
        *,
        model_id: str,
        revision: str,
        max_new_tokens: int,
        max_context_tokens: int | None = None,
        device: str = "cuda:0",
        adapter_path: str | Path | None = None,
    ) -> None:
        if not model_id or not revision:
            raise ValueError("model_id and revision must be non-empty")
        if isinstance(max_new_tokens, bool) or not isinstance(max_new_tokens, int) or max_new_tokens <= 0:
            raise ValueError("max_new_tokens must be a positive integer")
        if max_context_tokens is not None and (
            isinstance(max_context_tokens, bool)
            or not isinstance(max_context_tokens, int)
            or max_context_tokens <= max_new_tokens
        ):
            raise ValueError("max_context_tokens must be an integer larger than max_new_tokens")

        import torch
        from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

        self._torch = torch
        self.device = device
        self.max_new_tokens = max_new_tokens
        self.max_context_tokens = max_context_tokens
        self._output_cache: dict[str, str] = {}
        self.processor = AutoProcessor.from_pretrained(model_id, revision=revision)
        self.model = Qwen3VLForConditionalGeneration.from_pretrained(
            model_id,
            revision=revision,
            torch_dtype=torch.bfloat16,
            low_cpu_mem_usage=True,
        ).to(device)
        self.model.eval()
        self.adapter_path: str | None = None
        if adapter_path is not None:
            from peft import PeftModel

            resolved_adapter = str(Path(adapter_path).resolve())
            self.model = PeftModel.from_pretrained(self.model, resolved_adapter).to(device)
            self.model.eval()
            self.adapter_path = resolved_adapter

        self.identity = {
            "adapter_path": self.adapter_path,
            "attention_implementation": getattr(self.model.config, "_attn_implementation", None),
            "decoding": "greedy",
            "dtype": "bfloat16",
            "memoize_identical_inputs": True,
            "max_context_tokens": self.max_context_tokens,
            "model_id": model_id,
            "revision": revision,
        }

    def set_seed(self, seed: int) -> None:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError("seed must be an integer")
        self._torch.manual_seed(seed)
        self._torch.cuda.manual_seed_all(seed)

    def __call__(self, model_input: Mapping[str, Any]) -> str:
        cache_key = json.dumps(
            dict(model_input),
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        cached = self._output_cache.get(cache_key)
        if cached is not None:
            return cached
        messages = qwen_text_policy_messages(model_input)
        inputs = self.processor.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
            return_tensors="pt",
        ).to(self.device)
        input_length = inputs["input_ids"].shape[1]
        max_context_tokens = getattr(self, "max_context_tokens", None)
        if max_context_tokens is not None and input_length + self.max_new_tokens > max_context_tokens:
            raise ValueError(
                f"model input ({input_length}) plus output allowance ({self.max_new_tokens}) "
                f"exceeds the {max_context_tokens}-token context"
            )
        with self._torch.inference_mode():
            output_ids = self.model.generate(
                **inputs,
                do_sample=False,
                max_new_tokens=self.max_new_tokens,
            )
        generated = output_ids[:, input_length:]
        output = self.processor.batch_decode(
            generated,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )[0].strip()
        self._output_cache[cache_key] = output
        return output


__all__ = [
    "QWEN_TEXT_POLICY_SYSTEM_PROMPT",
    "QwenTextPolicy",
    "QwenTextTokenCounter",
    "load_qwen_text_token_counter",
    "qwen_text_policy_messages",
    "qwen_text_policy_training_messages",
]
