"""Predeclared paired 3x3 curriculum-by-modality analysis."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .best_first_curriculum import paired_bootstrap_interval

ORDERINGS = ("staged", "shuffled", "mixed_order")
MODALITIES = ("text-state", "visual-state", "multimodal-state")


def _values(rows: Sequence[Mapping[str, Any]], arm: str) -> dict[str, float]:
    result = {}
    for row in rows:
        key = f"{row['panel']}::{row['task_id']}"
        result[key] = float(row["arms"][arm]["invariant_valid_success"])
    return result


def _interval(protocol, left, right):
    analysis = protocol["analysis"]
    return paired_bootstrap_interval(
        left,
        right,
        resamples=analysis["bootstrap_resamples"],
        seed=analysis["bootstrap_seed"],
        confidence=analysis["confidence"],
    )


def analyze(protocol: Mapping[str, Any], evidence: Mapping[str, Any]) -> dict[str, Any]:
    rows = evidence["paired_rows"]
    curriculum_arms = [f"{modality}__{ordering}" for modality in MODALITIES for ordering in ORDERINGS]
    if not rows or any(not set(curriculum_arms).issubset(row["arms"]) for row in rows):
        raise ValueError("curriculum analysis requires complete paired 3x3 rows")
    values = {arm: _values(rows, arm) for arm in curriculum_arms}
    ordering_effects = []
    for modality in MODALITIES:
        for left, right in (("staged", "shuffled"), ("mixed_order", "shuffled"), ("staged", "mixed_order")):
            ordering_effects.append(
                {
                    "modality": modality,
                    "contrast": f"{left}_minus_{right}",
                    "interval": _interval(protocol, values[f"{modality}__{left}"], values[f"{modality}__{right}"]),
                }
            )
    modality_effects = []
    for ordering in ORDERINGS:
        for left, right in (
            ("visual-state", "text-state"),
            ("multimodal-state", "text-state"),
            ("multimodal-state", "visual-state"),
        ):
            modality_effects.append(
                {
                    "ordering": ordering,
                    "contrast": f"{left}_minus_{right}",
                    "interval": _interval(protocol, values[f"{left}__{ordering}"], values[f"{right}__{ordering}"]),
                }
            )
    interaction = []
    for left_order, right_order in (("staged", "shuffled"), ("mixed_order", "shuffled")):
        for left_modality, right_modality in (("visual-state", "text-state"), ("multimodal-state", "text-state")):
            left = {
                key: values[f"{left_modality}__{left_order}"][key] - values[f"{left_modality}__{right_order}"][key]
                for key in values[curriculum_arms[0]]
            }
            right = {
                key: values[f"{right_modality}__{left_order}"][key] - values[f"{right_modality}__{right_order}"][key]
                for key in values[curriculum_arms[0]]
            }
            interaction.append(
                {
                    "contrast": (
                        f"({left_modality}:{left_order}-{right_order})-({right_modality}:{left_order}-{right_order})"
                    ),
                    "interval": _interval(protocol, left, right),
                }
            )
    successes = {arm: sum(values[arm].values()) for arm in curriculum_arms}
    saturated = all(value == len(rows) for value in successes.values())
    controls = ("base", "sft_sequential_order_control", "random_valid", "exact_reference")
    curriculum_saturation_by_modality = {}
    control_saturation_by_modality = {}
    for modality in MODALITIES:
        modality_curriculum = [f"{modality}__{ordering}" for ordering in ORDERINGS]
        curriculum_saturation_by_modality[modality] = {
            "success_rate": sum(successes[arm] for arm in modality_curriculum) / (len(rows) * len(modality_curriculum)),
            "all_orderings_saturated": all(successes[arm] == len(rows) for arm in modality_curriculum),
        }
        control_saturation_by_modality[modality] = {}
        for control in controls:
            arm = f"{modality}__{control}"
            success = sum(float(row["arms"][arm]["invariant_valid_success"]) for row in rows)
            control_saturation_by_modality[modality][control] = {
                "successes": success,
                "success_rate": success / len(rows),
                "saturated": success == len(rows),
            }
    all_controls_saturated = all(
        value["saturated"] for modality in control_saturation_by_modality.values() for value in modality.values()
    )
    if saturated and all_controls_saturated:
        conclusion = "curriculum arms and all four modality-matched controls saturated; no effects claimed"
    elif saturated:
        conclusion = (
            "all curriculum arms saturated but comparator controls did not all saturate; no curriculum effects claimed"
        )
    elif all_controls_saturated:
        conclusion = "comparator controls saturated but curriculum arms did not; interpret paired curriculum intervals"
    else:
        conclusion = "neither curriculum arms nor all comparator controls saturated; interpret paired intervals"
    return {
        "schema_version": "expanded_curriculum_analysis_v1",
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "paired_units": len(rows),
        "successes": successes,
        "ordering_main_effect_by_modality": ordering_effects,
        "modality_effect_by_ordering": modality_effects,
        "modality_x_ordering_interaction": interaction,
        "materiality_margin": protocol["analysis"]["materiality_margin"],
        "control_saturation": {
            "all_curriculum_arms_saturated": saturated,
            "all_comparator_controls_saturated": all_controls_saturated,
            "curriculum_by_modality": curriculum_saturation_by_modality,
            "controls_by_modality": control_saturation_by_modality,
            "conclusion": conclusion,
        },
        "historical_issue67": {
            **protocol["analysis"]["historical_issue67"],
            "pooled": False,
            "interpretation": "reported separately under its unmatched historical schedule",
        },
    }
