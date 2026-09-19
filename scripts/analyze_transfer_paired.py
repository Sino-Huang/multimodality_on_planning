#!/usr/bin/env python
"""Paired per-example analysis of the transfer branches (v1 BFS + v2 extension) versus base.

CPU-only post-hoc analysis over retained raw predictions; reads no model, runs no GPU work.
McNemar exact two-sided binomial test on discordant pairs per (benchmark, cell) vs base,
with Holm correction across the 36 comparisons. Output: JSON evidence + markdown summary.
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V1 = ROOT / "outputs/expanded-study/v1/transfer"
V2 = ROOT / "outputs/expanded-study/v1/transfer-v2"
OUT_JSON = ROOT / "outputs/expanded-study/v1/transfer-paired-analysis.json"
OUT_MD = ROOT / "docs/experiments/expanded-study/transfer-paired-analysis.md"
DOCS_JSON = ROOT / "docs/experiments/expanded-study/transfer-paired-analysis.json"

BENCHMARKS = ("folio", "gsm8k", "humaneval")
V1_CELLS = ("bfs_text", "bfs_visual", "bfs_multimodal")
V2_CELLS = (
    "iw_text", "iw_visual", "iw_multimodal",
    "astar_w3_text", "astar_w3_visual", "astar_w3_multimodal",
    "astar_greedy_text", "astar_greedy_visual", "astar_greedy_multimodal",
)


def load_correct(scores_path: Path) -> dict[tuple[str, str], dict[str, bool]]:
    scores = json.loads(scores_path.read_text())
    table: dict[tuple[str, str], dict[str, bool]] = {}
    for cell_report in scores["cells"]:
        key = (cell_report["benchmark"], cell_report["cell"])
        preds_path = Path(cell_report["predictions"])
        predictions = json.loads(gzip.open(preds_path, "rt").read())["predictions"]
        table[key] = {p["example_id"]: bool(p["correct"]) for p in predictions}
    return table


def mcnemar(base: dict[str, bool], cell: dict[str, bool]) -> dict:
    from scipy.stats import binomtest

    ids = sorted(base)
    if ids != sorted(cell):
        raise ValueError("paired example ids differ")
    b = sum(1 for i in ids if base[i] and not cell[i])  # base right, cell wrong
    c = sum(1 for i in ids if not base[i] and cell[i])  # cell right, base wrong
    p = binomtest(c, b + c, 0.5).pvalue if (b + c) else 1.0
    return {
        "n": len(ids),
        "base_correct": sum(base.values()),
        "cell_correct": sum(cell.values()),
        "delta": sum(cell.values()) - sum(base.values()),
        "base_only_correct": b,
        "cell_only_correct": c,
        "mcnemar_exact_p": p,
    }


def holm_adjust(rows: list[dict]) -> None:
    ordered = sorted(range(len(rows)), key=lambda i: rows[i]["mcnemar_exact_p"])
    m = len(rows)
    adjusted = [0.0] * m
    running = 0.0
    for rank, i in enumerate(ordered):
        value = min(1.0, (m - rank) * rows[i]["mcnemar_exact_p"])
        running = max(running, value)
        adjusted[i] = running
    for i, row in enumerate(rows):
        row["holm_p"] = adjusted[i]


def main() -> int:
    v1 = load_correct(V1 / "scores.json")
    v2 = load_correct(V2 / "scores.json")
    rows: list[dict] = []
    for benchmark in BENCHMARKS:
        base = v1[(benchmark, "base")]
        for cell in V1_CELLS:
            stats = mcnemar(base, v1[(benchmark, cell)])
            rows.append({"benchmark": benchmark, "cell": cell, "cell_source": "v1", **stats})
        for cell in V2_CELLS:
            stats = mcnemar(base, v2[(benchmark, cell)])
            rows.append({"benchmark": benchmark, "cell": cell, "cell_source": "v2", **stats})
    holm_adjust(rows)
    result = {
        "schema_version": "transfer_paired_analysis_v1",
        "method": "McNemar exact two-sided binomial on discordant pairs vs v1 base cell; Holm correction across all 36 comparisons; v2 cells pair against the v1 base predictions over byte-identical frozen subsets",
        "comparisons": rows,
        "min_raw_p": min(r["mcnemar_exact_p"] for r in rows),
        "min_holm_p": min(r["holm_p"] for r in rows),
        "note": "single training seed (17); zero-shot; subsets 200/200/164; exploratory analysis of already-observed outcomes",
    }
    OUT_JSON.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    DOCS_JSON.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")

    lines = [
        "# Transfer paired analysis (post-hoc, CPU-only)",
        "",
        "Per-example McNemar exact tests of each adapted cell against the v1 base cell over the frozen",
        "subsets (folio 200, gsm8k 200, humaneval 164). v2 extension cells pair against the same v1 base",
        "predictions (byte-identical subsets). Holm correction across all 36 comparisons.",
        "Exploratory: computed after observing outcomes; single training seed (17).",
        "",
        "| Benchmark | Cell | base n correct | cell n correct | delta | base-only | cell-only | McNemar p | Holm p |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in rows:
        lines.append(
            f"| {r['benchmark']} | {r['cell']} | {r['base_correct']} | {r['cell_correct']} | "
            f"{r['delta']:+d} | {r['base_only_correct']} | {r['cell_only_correct']} | "
            f"{r['mcnemar_exact_p']:.4f} | {r['holm_p']:.4f} |"
        )
    lines += [
        "",
        f"Smallest raw p {result['min_raw_p']:.4f}; smallest Holm-adjusted p {result['min_holm_p']:.4f}.",
        "No comparison reaches significance after Holm correction." if result["min_holm_p"] >= 0.05 else
        "At least one comparison survives Holm correction at 0.05.",
        "",
        "Machine-readable evidence: [transfer-paired-analysis.json](transfer-paired-analysis.json).",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT_JSON} and {OUT_MD}")
    for r in sorted(rows, key=lambda r: r["mcnemar_exact_p"])[:6]:
        print(f"{r['benchmark']:9s} {r['cell']:22s} delta={r['delta']:+3d} p={r['mcnemar_exact_p']:.4f} holm={r['holm_p']:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
