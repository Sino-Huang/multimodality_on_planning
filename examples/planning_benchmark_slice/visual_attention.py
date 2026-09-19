"""Float32 Qwen attention without the quadratic GQA math-kernel fallback."""

from contextlib import nullcontext

import torch
from torch.nn.attention import SDPBackend, sdpa_kernel
from transformers import AttentionInterface, AttentionMaskInterface
from transformers.integrations.sdpa_attention import repeat_kv
from transformers.masking_utils import sdpa_mask


def visual_sdpa(module, query, key, value, attention_mask, dropout=0.0, scaling=None, is_causal=None, **kwargs):
    # PyTorch's efficient float32 kernel needs equal Q/K/V head counts. The
    # native GQA path otherwise falls back to a full [batch, heads, Q, K] matrix.
    groups = getattr(module, "num_key_value_groups", 1)
    key, value = repeat_kv(key, groups), repeat_kv(value, groups)
    if attention_mask is not None:
        attention_mask = attention_mask[:, :, :, : key.shape[-2]]
    if is_causal is None:
        is_causal = query.shape[2] > 1 and attention_mask is None and getattr(module, "is_causal", True)
    context = sdpa_kernel(SDPBackend.EFFICIENT_ATTENTION) if query.is_cuda else nullcontext()
    with context:
        output = torch.nn.functional.scaled_dot_product_attention(
            query, key, value, attn_mask=attention_mask, dropout_p=dropout, scale=scaling, is_causal=is_causal
        )
    return output.transpose(1, 2).contiguous(), None


def configure_visual_attention(model, implementation="visual_sdpa"):
    AttentionInterface.register("visual_sdpa", visual_sdpa)
    # Reuse Transformers' causal/padding/cache mask construction unchanged.
    AttentionMaskInterface.register("visual_sdpa", sdpa_mask)
    model.set_attn_implementation(implementation)
