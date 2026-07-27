from __future__ import annotations

import json
import math
from collections.abc import Mapping
from functools import singledispatch
from typing import Final, TextIO

from .output_layout_inventory_types import (
    OutputLayoutInventoryError,
    ReceiptInputValue,
    ReceiptRecord,
    ReceiptScalar,
    ReceiptValue,
)

_MAX_JSON_ITEMS: Final[int] = 100_000


class _JsonItemBudget:
    def __init__(self) -> None:
        self.used: int = 0

    def consume(self, count: int) -> None:
        self.used += count
        if self.used > _MAX_JSON_ITEMS:
            raise OutputLayoutInventoryError("too many JSON items")


def parse_receipt_record(value: ReceiptInputValue) -> ReceiptRecord:
    _count_json_items(value, _JsonItemBudget())
    parsed = _parse_receipt_value(value, _JsonItemBudget())
    if not isinstance(parsed, dict):
        raise OutputLayoutInventoryError("receipt JSON must be an object")
    return parsed


def load_receipt_record(handle: TextIO) -> ReceiptRecord:
    decoded: ReceiptInputValue = json.load(handle, object_pairs_hook=_reject_duplicate_keys)
    return parse_receipt_record(decoded)


@singledispatch
def _parse_receipt_value(value: ReceiptInputValue, _budget: _JsonItemBudget) -> ReceiptValue:
    raise OutputLayoutInventoryError(f"unsupported receipt value type: {type(value).__name__}")


def _parse_none(value: None, _budget: _JsonItemBudget) -> ReceiptValue:
    return value


def _parse_string(value: str, _budget: _JsonItemBudget) -> ReceiptValue:
    return value


def _parse_boolean(value: bool, _budget: _JsonItemBudget) -> ReceiptValue:
    return value


def _parse_integer(value: int, _budget: _JsonItemBudget) -> ReceiptValue:
    return value


def _parse_float(value: float, _budget: _JsonItemBudget) -> ReceiptValue:
    if not math.isfinite(value):
        raise OutputLayoutInventoryError("receipt floats must be finite")
    return value


def _parse_list(value: list[ReceiptInputValue], budget: _JsonItemBudget) -> ReceiptValue:
    budget.consume(len(value))
    return [_parse_receipt_value(item, budget) for item in value]


def _parse_mapping(
    value: Mapping[ReceiptScalar, ReceiptInputValue], budget: _JsonItemBudget
) -> ReceiptValue:
    budget.consume(len(value))
    parsed: ReceiptRecord = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise OutputLayoutInventoryError("receipt object keys must be strings")
        parsed[key] = _parse_receipt_value(item, budget)
    return parsed


def _reject_duplicate_keys(pairs: list[tuple[str, ReceiptInputValue]]) -> ReceiptRecord:
    parsed: ReceiptRecord = {}
    for key, value in pairs:
        if key in parsed:
            raise OutputLayoutInventoryError("duplicate receipt JSON key")
        parsed[key] = value
    return parsed


@singledispatch
def _count_json_items(value: ReceiptInputValue, _budget: _JsonItemBudget) -> None:
    del value


def _count_json_list(value: list[ReceiptInputValue], budget: _JsonItemBudget) -> None:
    budget.consume(len(value))
    for item in value:
        _count_json_items(item, budget)


def _count_json_mapping(value: Mapping[ReceiptScalar, ReceiptInputValue], budget: _JsonItemBudget) -> None:
    budget.consume(len(value))
    for item in value.values():
        _count_json_items(item, budget)


_ = _parse_receipt_value.register(type(None), _parse_none)
_ = _parse_receipt_value.register(str, _parse_string)
_ = _parse_receipt_value.register(bool, _parse_boolean)
_ = _parse_receipt_value.register(int, _parse_integer)
_ = _parse_receipt_value.register(float, _parse_float)
_ = _parse_receipt_value.register(list, _parse_list)
_ = _parse_receipt_value.register(Mapping, _parse_mapping)
_ = _count_json_items.register(list, _count_json_list)
_ = _count_json_items.register(Mapping, _count_json_mapping)
