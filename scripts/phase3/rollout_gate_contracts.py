"""Shared immutable contracts for Planimation rollout gates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from .io_utils import JSONRecord

Stage = Literal["fixture", "changed-canary", "stratified-pilot", "complete-domain", "frozen-full"]
STAGES: Final[tuple[Stage, ...]] = (
    "fixture",
    "changed-canary",
    "stratified-pilot",
    "complete-domain",
    "frozen-full",
)
RECEIPT_ARTIFACT_PATHS: Final = (
    "diagnostics/pairing_manifest.jsonl",
    "diagnostics/hybrid_output_manifest.json",
    "diagnostics/state_render_manifest.jsonl",
)


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    stage: Stage
    approved: bool
    reasons: tuple[str, ...]
    counts: dict[str, int]

    def to_record(self) -> JSONRecord:
        return {
            "artifact_kind": "planimation_rollout_promotion_receipt_v1",
            "approved": self.approved,
            "counts": {key: value for key, value in self.counts.items()},
            "reasons": list(self.reasons),
            "stage": self.stage,
        }
