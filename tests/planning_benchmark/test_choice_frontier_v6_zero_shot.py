"""#141 zero-shot arm contracts: output extraction, arm-vs-adapter verdict order, exact sign-flip p-value."""

from __future__ import annotations

import itertools
from statistics import mean

import pytest

from examples.planning_benchmark_slice.choice_frontier import canonical_choice
from scripts.analyze_choice_frontier_v6_zero_shot import adapter_verdict, sign_flip_p
from scripts.run_choice_frontier_v6_zero_shot import extract_choice


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"expand_choice": "c3"}', (canonical_choice("c3"), "json_object")),
        ('```json\n{"expand_choice": "c12"}\n```', (canonical_choice("c12"), "json_object")),
        ('{"reason": "x"} then {"expand_choice": "c1"}', (canonical_choice("c1"), "json_object")),
        ("  c7\n", (canonical_choice("c7"), "bare_label")),
        ("I choose c7", ("I choose c7", "raw")),
        ('{"expand_choice": 3}', ('{"expand_choice": 3}', "raw")),
    ],
)
def test_extractor_rules(text, expected):
    assert extract_choice(text) == expected


def test_extracted_non_offered_label_is_still_submitted_for_rejection():
    # The extractor never validates against the menu; the frozen session rejects c99.
    assert extract_choice('{"expand_choice": "c99"}')[0] == canonical_choice("c99")


def test_adapter_verdict_order():
    assert adapter_verdict(0.01, 0.2) == "SEPARATED_ABOVE"
    assert adapter_verdict(-0.3, -0.01) == "SEPARATED_BELOW"
    assert adapter_verdict(-0.04, 0.04) == "EQUIVALENT"
    assert adapter_verdict(-0.05, 0.04) == "NOT_SEPARATED"
    assert adapter_verdict(-0.2, 0.1) == "NOT_SEPARATED"


@pytest.mark.parametrize("diffs", [[0.5, -0.1, 0.2, 0.0, 0.3], [0.1] * 7, [0.25, -0.25, 0.5, -0.5, 0.125, 0.0]])
def test_sign_flip_matches_brute_force(diffs):
    observed = abs(mean(diffs))
    count = sum(
        abs(mean(s * d for s, d in zip(signs, diffs, strict=True))) >= observed - 1e-12
        for signs in itertools.product((1, -1), repeat=len(diffs))
    )
    assert sign_flip_p(diffs)["p_two_sided"] == pytest.approx(count / 2 ** len(diffs))


def test_sign_flip_split_path_for_more_than_sixteen_tasks():
    result = sign_flip_p([0.1] * 18)
    assert result["sign_vectors"] == 2**18
    assert result["p_two_sided"] == pytest.approx(2 / 2**18)
