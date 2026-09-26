"""F5: expanded-baseline enumeration success, descriptive and development-stage.

Evidence: docs/experiments/expanded-study/synthesis-v1/baseline-summary.csv
  modality, algorithm, arm, episodes, successes (every cell); totals of successes
  by arm are asserted against 0, 125, 240, 288. The separate additive-pair
  identity audit is outputs/native-arms/v1/identity-audit.json
  pairs_identical / pairs_checked (48/48), not 48 modality-specific pairs.
Run: python fig_identity_heatmap.py [EVIDENCE_ROOT].
"""

import csv
from collections import defaultdict
from pathlib import Path

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np

from _style import ARM_STYLE, EVIDENCE_ROOT, load_json

HERE = Path(__file__).resolve().parent
CSV = "docs/experiments/expanded-study/synthesis-v1/baseline-summary.csv"
MODALITIES = [("text-state", "Text"), ("visual-state", "Visual"),
              ("multimodal-state", "Multimodal")]
ALGORITHMS = [("bfs", "BFS"), ("best_first_width", "BFWS"),
              ("best_first_add_greedy", "Greedy"), ("best_first_add_w3", "w3")]
ARMS = [("pretrained_base", "Base"), ("process_sft", "SFT"),
        ("random_valid", "Random-valid"), ("exact_reference", "Exact")]
EXPECTED_TOTALS = {"pretrained_base": 0, "process_sft": 125,
                   "random_valid": 240, "exact_reference": 288}


def evidence():
    with (EVIDENCE_ROOT / CSV).open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    cells = {}
    totals = defaultdict(int)
    episodes = defaultdict(int)
    for row in rows:
        key = (row["algorithm"], row["modality"], row["arm"])
        assert key not in cells, f"duplicated baseline cell: {key}"
        success, count = int(row["successes"]), int(row["episodes"])
        assert count == 24 and 0 <= success <= count, (key, success, count)
        cells[key] = success
        totals[row["arm"]] += success
        episodes[row["arm"]] += count
    expected = {(alg, mod, arm) for alg, _ in ALGORITHMS
                for mod, _ in MODALITIES for arm, _ in ARMS}
    assert cells.keys() == expected, f"baseline cells missing/extra: {expected ^ cells.keys()}"
    for arm, total in EXPECTED_TOTALS.items():
        assert episodes[arm] == 288 and totals[arm] == total, (arm, totals[arm], episodes[arm])
    # The additive rows share control success with the exact reference;
    # decision identity is separately asserted against the audit below.
    for alg, _ in ALGORITHMS[2:]:
        for mod, _ in MODALITIES:
            assert cells[alg, mod, "random_valid"] == cells[alg, mod, "exact_reference"] == 24
    audit = load_json("outputs/native-arms/v1/identity-audit.json")
    assert audit["pairs_identical"] == audit["pairs_checked"] == 48
    assert "deterministic sorted candidate order" in audit["structural_basis"]
    return cells, totals, audit


def main():
    cells, totals, audit = evidence()
    matrix = np.asarray([[cells[alg, mod, arm] for arm, _ in ARMS]
                         for alg, _ in ALGORITHMS for mod, _ in MODALITIES])
    cmap = mcolors.LinearSegmentedColormap.from_list(
        "enumeration", ["#f2f4f6", "#c4dce9", ARM_STYLE["exact_reference"]["color"]])
    fig, ax = plt.subplots(figsize=(7.0, 5.5))
    fig.subplots_adjust(left=.225, right=.72, top=.82, bottom=.085)
    image = ax.imshow(matrix, cmap=cmap, norm=mcolors.Normalize(0, 24), aspect="auto")
    ax.set_xticks(range(4), [label for _, label in ARMS], fontsize=7.4)
    ax.tick_params(top=True, labeltop=True, bottom=False, labelbottom=False, length=0, pad=7)
    ax.set_yticks(range(12), [name for _, name in MODALITIES] * 4, fontsize=7.4)
    ax.tick_params(axis="y", length=0, pad=8)
    for group, (_, name) in enumerate(ALGORITHMS):
        ax.text(-1.27, group * 3 + 1, name, ha="right", va="center",
                fontsize=8, fontweight="bold", color="#243746", clip_on=False)
    for boundary in (2.5, 5.5, 8.5):
        ax.axhline(boundary, color="white", linewidth=3)
    ax.set_xticks(np.arange(-.5, 4, 1), minor=True)
    ax.set_yticks(np.arange(-.5, 12, 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=1)
    ax.tick_params(which="minor", length=0)
    for row in range(12):
        for column in range(4):
            value = matrix[row, column]
            ax.text(column, row, str(value), ha="center", va="center", fontsize=8,
                    fontweight="bold" if column in (1, 2) else "normal",
                    color="white" if value >= 18 else "#263646")
    # Bracket only additive-algorithm oracle/reference columns (three modalities
    # each). The audit count refers to 24 tasks x two algorithms, not six cells.
    ax.add_patch(Rectangle((1.52, 5.54), 1.96, 5.92, fill=False,
                           edgecolor="white", linewidth=2))
    # % Evidence: identity-audit.json pairs_identical/pairs_checked;
    # 48 task-algorithm pairs are not 48 modality-specific cells.
    fig.text(.755, .36, "Random-valid ≡ exact\n48/48 additive pairs\n(decision audit)",
             va="center", ha="left", fontsize=7.6,
             color=ARM_STYLE["exact_reference"]["color"])
    fig.add_artist(plt.Line2D([.715, .742], [.36, .36], transform=fig.transFigure,
                              color=ARM_STYLE["exact_reference"]["color"], linewidth=1))
    cax = fig.add_axes([.76, .72, .16, .022])
    bar = fig.colorbar(image, cax=cax, orientation="horizontal", ticks=[0, 12, 24])
    bar.set_label("Successes per cell /24", fontsize=7, labelpad=3)
    bar.ax.tick_params(labelsize=7, length=2)
    # % Evidence: baseline-summary.csv successes grouped by arm; 12 cells per arm,
    # episodes=24 each, asserted at exact-integer totals above.
    fig.text(.225, .89, "Enumeration contract  ·  development-stage, descriptive",
             fontsize=9, color="#243746", weight="bold")
    fig.text(.225, .045, "Overall: " + "   ·   ".join(
        f"{name} {totals[arm]}/288" for arm, name in ARMS), fontsize=7.2,
        color="#354554")
    for extension in ("pdf", "svg", "png"):
        fig.savefig(HERE / f"fig_identity_heatmap.{extension}",
                    dpi=300 if extension == "png" else None)
    plt.close(fig)
    print("F5 totals:", dict(totals), "additive identity:",
          audit["pairs_identical"], "/", audit["pairs_checked"])


if __name__ == "__main__":
    main()
