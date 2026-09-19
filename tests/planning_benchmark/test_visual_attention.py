"""Keep causal, padding, decoding and vision semantics in the efficient path."""

from types import SimpleNamespace

import pytest
import torch
from transformers import AttentionMaskInterface
from transformers.masking_utils import sdpa_mask

from examples.planning_benchmark_slice.visual_attention import configure_visual_attention, visual_sdpa


@pytest.mark.parametrize("case", ["causal", "padding", "decode", "vision"])
def test_visual_attention_matches_grouped_query_reference(case):
    torch.manual_seed(17)
    q_length = 1 if case == "decode" else 7
    groups = 1 if case == "vision" else 2
    q = torch.randn(2, 4, q_length, 8)
    k, v = [torch.randn(2, 4 // groups, 7, 8) for _ in range(2)]
    mask = None
    causal = case == "causal"
    if case == "padding":
        mask = torch.ones(2, 1, 7, 7, dtype=torch.bool).tril()
        mask[0, :, :, :2] = False
    module = SimpleNamespace(num_key_value_groups=groups, is_causal=case != "vision")
    expected = torch.nn.functional.scaled_dot_product_attention(
        q, k, v, attn_mask=mask, is_causal=causal, enable_gqa=True, scale=0.2
    )
    actual, weights = visual_sdpa(module, q, k, v, mask, scaling=0.2)
    torch.testing.assert_close(actual, expected.transpose(1, 2), atol=1e-6, rtol=1e-5)
    assert weights is None


def test_custom_attention_keeps_transformers_mask_builder():
    selected = []
    configure_visual_attention(SimpleNamespace(set_attn_implementation=selected.append))
    assert selected == ["visual_sdpa"]
    assert AttentionMaskInterface()["visual_sdpa"] is sdpa_mask
