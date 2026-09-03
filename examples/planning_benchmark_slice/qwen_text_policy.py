"""Qwen3-VL text-state policy adapter for governed search episodes."""

from __future__ import annotations

import json
from collections.abc import Mapping
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence

from .model_search_episode import SearchPolicyRequest

FROZEN_MAX_BATCH_SIZE = 8
FROZEN_MAX_BATCH_INPUT_TOKENS = 48_000
FROZEN_MAX_NEW_TOKENS = 384
FROZEN_BATCHED_INFERENCE_DTYPE = "float32"

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


class BatchedPolicyAdapter:
    """Batched greedy Qwen inference with one backbone and switchable PEFT adapters."""

    def __init__(
        self,
        *,
        model_id: str,
        revision: str,
        adapter_paths: Mapping[str, str | Path],
        device: str = "cuda:0",
        max_new_tokens: int = FROZEN_MAX_NEW_TOKENS,
        max_context_tokens: int = 8_192,
        max_batch_size: int = FROZEN_MAX_BATCH_SIZE,
        max_batch_input_tokens: int = FROZEN_MAX_BATCH_INPUT_TOKENS,
        inference_dtype: str = FROZEN_BATCHED_INFERENCE_DTYPE,
        training_message_builder: Callable[[Mapping[str, Any]], list[dict[str, str]]] = (
            qwen_text_policy_training_messages
        ),
        policy_message_builder: Callable[[Mapping[str, Any]], list[dict[str, Any]]] = qwen_text_policy_messages,
    ) -> None:
        for name, value in (
            ("max_new_tokens", max_new_tokens),
            ("max_context_tokens", max_context_tokens),
            ("max_batch_size", max_batch_size),
            ("max_batch_input_tokens", max_batch_input_tokens),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if max_context_tokens <= max_new_tokens:
            raise ValueError("max_context_tokens must exceed max_new_tokens")
        if not model_id or not revision:
            raise ValueError("model_id and revision must be non-empty")
        if inference_dtype != FROZEN_BATCHED_INFERENCE_DTYPE:
            raise ValueError("batched inference dtype is frozen to float32 for scalar parity")

        import torch
        from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

        self._torch = torch
        self.device = device
        self.max_new_tokens = max_new_tokens
        self.max_context_tokens = max_context_tokens
        self.max_batch_size = max_batch_size
        self.max_batch_input_tokens = max_batch_input_tokens
        self.training_message_builder = training_message_builder
        self.policy_message_builder = policy_message_builder
        self.processor = AutoProcessor.from_pretrained(model_id, revision=revision)
        tokenizer = getattr(self.processor, "tokenizer", None)
        if tokenizer is not None:
            tokenizer.padding_side = "left"
            if tokenizer.pad_token_id is None:
                tokenizer.pad_token_id = tokenizer.eos_token_id
        self.model = Qwen3VLForConditionalGeneration.from_pretrained(
            model_id,
            revision=revision,
            dtype=torch.float32,
            low_cpu_mem_usage=True,
        ).to(device)
        self.model.eval()
        self.adapter_paths = {name: str(Path(path).expanduser().resolve()) for name, path in adapter_paths.items()}
        if any(not name or not Path(path).is_dir() for name, path in self.adapter_paths.items()):
            raise ValueError("adapter names must be non-empty and adapter paths must exist")
        self._loaded_adapters: set[str] = set()
        self._peft_wrapped = False
        self._output_cache: dict[tuple[str | None, bytes], str] = {}
        self._token_length_cache: dict[bytes, int] = {}
        self.identity = {
            "attention_implementation": getattr(self.model.config, "_attn_implementation", None),
            "decoding": "greedy",
            "dtype": inference_dtype,
            "max_batch_input_tokens": max_batch_input_tokens,
            "max_batch_size": max_batch_size,
            "max_context_tokens": max_context_tokens,
            "max_new_tokens": max_new_tokens,
            "memoize_identical_inputs": True,
            "model_id": model_id,
            "revision": revision,
        }

    def input_token_length(self, request: SearchPolicyRequest) -> int:
        key = request.canonical_input
        cached = self._token_length_cache.get(key)
        if cached is not None:
            return cached
        tokens = self.processor.tokenizer.apply_chat_template(
            self.training_message_builder(request.model_input),
            tokenize=True,
            add_generation_prompt=True,
        )
        length = len(tokens)
        self._token_length_cache[key] = length
        return length

    def generate_many(self, requests: Sequence[SearchPolicyRequest]) -> list[str]:
        """Return one output per request while preserving caller order."""

        request_list = list(requests)
        if not request_list:
            return []
        outputs: list[str | None] = [None] * len(request_list)
        by_adapter: dict[str | None, list[tuple[int, SearchPolicyRequest]]] = {}
        for index, request in enumerate(request_list):
            if not isinstance(request, SearchPolicyRequest):
                raise TypeError("requests must contain SearchPolicyRequest values")
            by_adapter.setdefault(request.adapter_id, []).append((index, request))

        for adapter_id in sorted(by_adapter, key=lambda value: value or ""):
            indexed = by_adapter[adapter_id]
            missing_by_key: dict[tuple[str | None, bytes], SearchPolicyRequest] = {}
            for index, request in indexed:
                key = (adapter_id, request.canonical_input)
                cached = self._output_cache.get(key)
                if cached is None:
                    missing_by_key.setdefault(key, request)
                else:
                    outputs[index] = cached
            if missing_by_key:
                unique_requests = list(missing_by_key.values())
                generated = self._generate_uncached(adapter_id, unique_requests)
                for key, output in zip(missing_by_key, generated, strict=True):
                    self._output_cache[key] = output
            for index, request in indexed:
                if outputs[index] is None:
                    outputs[index] = self._output_cache[(adapter_id, request.canonical_input)]
        return [output for output in outputs if output is not None]

    def verify_scalar_parity(self, requests: Sequence[SearchPolicyRequest]) -> bool:
        """Run fixed probes both scalar and batched, bypassing the inference cache."""

        request_list = list(requests)
        if not request_list or len({request.adapter_id for request in request_list}) != 1:
            raise ValueError("parity probes must be a non-empty single-adapter sequence")
        adapter_id = request_list[0].adapter_id
        scalar = [self._generate_uncached(adapter_id, [request])[0] for request in request_list]
        batched = self._generate_uncached(adapter_id, request_list)
        return scalar == batched

    def verify_determinism(self, requests: Sequence[SearchPolicyRequest]) -> bool:
        """Require two uncached batched probe runs to be byte-identical."""

        request_list = list(requests)
        if not request_list or len({request.adapter_id for request in request_list}) != 1:
            raise ValueError("determinism probes must be a non-empty single-adapter sequence")
        adapter_id = request_list[0].adapter_id
        return self._generate_uncached(adapter_id, request_list) == self._generate_uncached(
            adapter_id,
            request_list,
        )

    def _generate_uncached(
        self,
        adapter_id: str | None,
        requests: Sequence[SearchPolicyRequest],
    ) -> list[str]:
        if len(requests) > self.max_batch_size:
            raise ValueError("batch exceeds max_batch_size")
        lengths = [self.input_token_length(request) for request in requests]
        if any(length + self.max_new_tokens > self.max_context_tokens for length in lengths):
            raise ValueError("batch contains a request exceeding the model context")
        padded_input_tokens = max(lengths) * len(lengths)
        if padded_input_tokens > self.max_batch_input_tokens:
            raise ValueError("batch exceeds max_batch_input_tokens")

        conversations = [self.policy_message_builder(request.model_input) for request in requests]
        inputs = self.processor.apply_chat_template(
            conversations,
            tokenize=True,
            add_generation_prompt=True,
            padding=True,
            return_dict=True,
            return_tensors="pt",
        ).to(self.device)
        input_width = inputs["input_ids"].shape[1]
        with self._adapter_context(adapter_id), self._torch.inference_mode():
            output_ids = self.model.generate(
                **inputs,
                do_sample=False,
                max_new_tokens=self.max_new_tokens,
            )
        generated = output_ids[:, input_width:]
        return [
            output.strip()
            for output in self.processor.batch_decode(
                generated,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            )
        ]

    @contextmanager
    def _adapter_context(self, adapter_id: str | None) -> Iterator[None]:
        if adapter_id is None:
            context = self.model.disable_adapter() if self._peft_wrapped else nullcontext()
            with context:
                yield
            return
        try:
            adapter_path = self.adapter_paths[adapter_id]
        except KeyError as error:
            raise ValueError(f"unknown adapter: {adapter_id}") from error
        if not self._peft_wrapped:
            from peft import PeftModel

            self.model = PeftModel.from_pretrained(
                self.model,
                adapter_path,
                adapter_name=adapter_id,
            ).to(self.device)
            self.model.eval()
            self._peft_wrapped = True
            self._loaded_adapters.add(adapter_id)
        elif adapter_id not in self._loaded_adapters:
            self.model.load_adapter(adapter_path, adapter_name=adapter_id)
            self._loaded_adapters.add(adapter_id)
        self.model.set_adapter(adapter_id)
        yield


__all__ = [
    "FROZEN_BATCHED_INFERENCE_DTYPE",
    "FROZEN_MAX_BATCH_INPUT_TOKENS",
    "FROZEN_MAX_BATCH_SIZE",
    "FROZEN_MAX_NEW_TOKENS",
    "QWEN_TEXT_POLICY_SYSTEM_PROMPT",
    "BatchedPolicyAdapter",
    "QwenTextPolicy",
    "QwenTextTokenCounter",
    "load_qwen_text_token_counter",
    "qwen_text_policy_messages",
    "qwen_text_policy_training_messages",
]
