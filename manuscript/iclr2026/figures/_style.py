"""Shared evidence access, 3-dp checks, and final-size figure styling."""

import json
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8,
                            "pdf.fonttype": 42, "svg.fonttype": "none"})

EVIDENCE_ROOT = (Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) > 1
                 else Path(__file__).resolve().parents[4] / "multimodality_on_planning")


def load_json(rel):
    """Read a JSON evidence record relative to the selected evidence repository."""
    return json.loads((EVIDENCE_ROOT / rel).read_text())


def f3(value):
    """Render a number to three decimal places with Decimal half-up rounding."""
    return str(Decimal(str(value)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))


def assert_3dp(actual, expected):
    """Assert scalars or flat sequences agree at the manuscript's 3-dp precision."""
    got = tuple(f3(v) for v in actual) if isinstance(actual, (tuple, list)) else f3(actual)
    want = tuple(f3(v) for v in expected) if isinstance(expected, (tuple, list)) else f3(expected)
    assert got == want, f"got {got}, expected {want}"


# All figures use the same semantic colours and marker shapes.
# Each entry: colour of the arm, marker glyph, marker fill, marker edge.
ARM_STYLE = {
    "exact_reference": {"color": "#003F66", "marker": "o", "facecolor": "#003F66", "edgecolor": "#003F66"},
    "exact-eps-0.25": {"color": "#0072B2", "marker": "o", "facecolor": "#0072B2", "edgecolor": "#0072B2"},
    "exact-eps-0.50": {"color": "#3B97CF", "marker": "o", "facecolor": "#3B97CF", "edgecolor": "#3B97CF"},
    "exact-eps-0.75": {"color": "#7FBDE3", "marker": "o", "facecolor": "#7FBDE3", "edgecolor": "#7FBDE3"},
    "random_valid": {"color": "#777777", "marker": "o", "facecolor": "white", "edgecolor": "#777777"},
    "learned_adapter_seed_mean": {"color": "#D55E00", "marker": "s", "facecolor": "#D55E00", "edgecolor": "#D55E00"},
    "zero_shot_base": {"color": "#333333", "marker": "D", "facecolor": "white", "edgecolor": "#333333"},
    "first_adapter": {"color": "#D55E00", "marker": "s", "facecolor": "white", "edgecolor": "#D55E00"},
}
