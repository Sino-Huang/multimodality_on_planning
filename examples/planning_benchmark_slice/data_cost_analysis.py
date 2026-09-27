"""#147 pre-registered data-cost analysis: cell metrics, N50/N90, task-cluster bootstrap, Holm-adjusted contrasts."""

from __future__ import annotations

import itertools
import math
import random
import statistics
import warnings
from typing import Any, Iterable

import numpy as np

ALGORITHMS = ("bfs", "best_first_width")
MODALITIES = ("text-state", "visual-state", "multimodal-state")
SIZES = (512, 1024, 2048, 4096, 8192, 16384)
SEEDS = (17, 29, 71)
RANDOM_VALID_SEEDS = (17, 5077, 6131, 7409, 8527)
QUANTILES = {"N50": 0.5, "N90": 0.9}
DRAWS = 10_000
BOOTSTRAP_SEED = 147
ALPHA = 0.05
SUCCESS_CONTRASTS = [("algorithm", modality, "bfs", "best_first_width") for modality in MODALITIES] + [
    ("modality", algorithm, a, b)
    for algorithm in ALGORITHMS
    for a, b in (
        ("text-state", "visual-state"),
        ("text-state", "multimodal-state"),
        ("visual-state", "multimodal-state"),
    )
]
BOOTSTRAP_NOTE = {
    "draws": DRAWS,
    "seed": BOOTSTRAP_SEED,
    "rng": "random.Random(147); each draw resamples the panel tasks with replacement",
    "unit": "task cluster",
    "within_draw": "per training seed mean over the resampled tasks, then averaged over seeds",
    "interval": "95% percentile (sorted[int(p*(n-1))])",
}


# --------------------------------------------------------------------------------------------- primitives


def percentile(sorted_values: list[float], probability: float):
    if not sorted_values:
        return None
    return sorted_values[min(len(sorted_values) - 1, int(probability * (len(sorted_values) - 1)))]


def holm(pvalues: list[float]) -> list[float]:
    """Holm step-down adjusted p-values (monotone, capped at 1), in input order."""

    m = len(pvalues)
    order = sorted(range(m), key=lambda i: pvalues[i])
    adjusted = [0.0] * m
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvalues[index]))
        adjusted[index] = running
    return adjusted


def two_sided_p(differences: np.ndarray) -> float:
    values = differences[~np.isnan(differences)]
    if values.size == 0:
        return float("nan")
    return float(min(1.0, 2 * min(np.mean(values <= 0), np.mean(values >= 0))))


def n_quantile(sizes: Iterable[int], curve: Iterable[float | None], q: float) -> dict[str, Any]:
    """Operations needed to reach success q: linear interpolation in log2(N) at the first upward crossing.

    Already reached at the smallest evaluated size -> left-censored ``<=N``; never reached -> right-censored ``>N``
    at the largest evaluated size. ``ordinal`` orders censored values (-inf / +inf) for bootstrap percentiles.
    """

    pairs = zip(sizes, curve, strict=True)
    points = [(math.log2(s), float(y)) for s, y in pairs if y is not None and not math.isnan(float(y))]
    if not points:
        return {"label": "missing", "value": None, "log2": None, "censoring": "missing", "ordinal": float("nan")}
    x0, y0 = points[0]
    if y0 >= q:
        bound = round(2**x0)
        return {
            "label": f"<={bound}",
            "value": None,
            "log2": None,
            "censoring": "left",
            "bound": bound,
            "ordinal": -math.inf,
        }
    for (xa, ya), (xb, yb) in itertools.pairwise(points):
        if ya < q <= yb:
            x = xa + (q - ya) / (yb - ya) * (xb - xa)
            return {"label": f"{2**x:.0f}", "value": 2**x, "log2": x, "censoring": "none", "ordinal": x}
    bound = round(2 ** points[-1][0])
    return {"label": f">{bound}", "value": None, "log2": None, "censoring": "right", "bound": bound, "ordinal": math.inf}


def ordinal_label(value: float, low: int, high: int) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if value == -math.inf:
        return f"<={low}"
    if value == math.inf:
        return f">{high}"
    return f"{2**value:.0f}"


def draw_indices(n_tasks: int, draws: int = DRAWS, seed: int = BOOTSTRAP_SEED) -> np.ndarray:
    rng = random.Random(seed)
    return np.array([[rng.randrange(n_tasks) for _ in range(n_tasks)] for _ in range(draws)], dtype=np.int64)


def _nanmean(array: np.ndarray, axis: int) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        return np.nanmean(array, axis=axis)


def seed_mean(matrix: np.ndarray, indices: np.ndarray | None = None) -> np.ndarray | float:
    """``matrix`` is (seeds, tasks) with NaN for missing episodes. Observed (indices None) or per draw."""

    if indices is None:
        return float(_nanmean(_nanmean(matrix, 1), 0)) if matrix.size else float("nan")
    return _nanmean(_nanmean(matrix[:, indices], 2), 0)


def ci(values: np.ndarray) -> list[float] | None:
    ordered = sorted(float(v) for v in values if not math.isnan(v))
    if not ordered:
        return None
    return [percentile(ordered, 0.025), percentile(ordered, 0.975)]


# --------------------------------------------------------------------------------------------- data shaping


class Table:
    """Episode rows indexed by (kind, algorithm, modality, size, epochs, seed) -> task -> row."""

    def __init__(self, rows: list[dict[str, Any]], tasks: list[str]):
        self.tasks = list(tasks)
        self.position = {task: i for i, task in enumerate(self.tasks)}
        self.cells: dict[tuple, dict[str, dict[str, Any]]] = {}
        for row in rows:
            key = (row["kind"], row["algorithm"], row["modality"], row.get("size"), row.get("epochs"), row.get("seed"))
            if row["task_id"] in self.position:
                self.cells.setdefault(key, {})[row["task_id"]] = row

    def matrix(self, keys: list[tuple], field: str = "success") -> np.ndarray:
        result = np.full((len(keys), len(self.tasks)), np.nan)
        for s, key in enumerate(keys):
            for task, row in self.cells.get(key, {}).items():
                value = row.get(field)
                result[s, self.position[task]] = np.nan if value is None else float(value)
        return result

    def rows(self, keys: list[tuple]) -> list[dict[str, Any]]:
        return [row for key in keys for row in self.cells.get(key, {}).values()]


def learned_keys(algorithm: str, modality: str, size: int, seeds=SEEDS) -> list[tuple]:
    return [("learned", algorithm, modality, size, 1, seed) for seed in seeds]


def episode_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    calls = sum(r.get("calls") or 0 for r in rows)
    accepted = sum(r.get("accepted") or 0 for r in rows)
    invalid_steps = sorted(r["first_invalid_step"] for r in rows if r.get("first_invalid_step") is not None)
    rates = [r["valid_op_rate"] for r in rows if r.get("valid_op_rate") is not None]
    return {
        "episodes": len(rows),
        "valid_op_rate_pooled": accepted / calls if calls else None,
        "valid_op_rate_episode_mean": statistics.fmean(rates) if rates else None,
        "model_calls": calls,
        "first_invalid_step": {
            "median_over_episodes_with_invalid": statistics.median(invalid_steps) if invalid_steps else None,
            "episodes_with_invalid": len(invalid_steps),
            "censored_no_invalid": len(rows) - len(invalid_steps),
        },
    }


# --------------------------------------------------------------------------------------------- analysis blocks


def cell_block(table: Table, indices: np.ndarray) -> tuple[list[dict], dict]:
    cells, boot = [], {}
    expected_per_cell = len(SEEDS) * len(table.tasks)
    for algorithm in ALGORITHMS:
        for modality in MODALITIES:
            for size in SIZES:
                keys = learned_keys(algorithm, modality, size)
                matrix = table.matrix(keys)
                present = int(np.sum(~np.isnan(matrix)))
                draws = seed_mean(matrix, indices) if present else np.full(len(indices), np.nan)
                boot[(algorithm, modality, size)] = draws
                per_seed = {
                    str(seed): (float(_nanmean(matrix[i], 0)) if np.any(~np.isnan(matrix[i])) else None)
                    for i, seed in enumerate(SEEDS)
                }
                cells.append(
                    {
                        "algorithm": algorithm,
                        "modality": modality,
                        "size": size,
                        "success_3seed_mean": seed_mean(matrix) if present else None,
                        "success_per_seed": per_seed,
                        "ci95": ci(draws) if present else None,
                        "episodes_present": present,
                        "episodes_expected": expected_per_cell,
                        "complete": present == expected_per_cell,
                        **episode_summary(table.rows(keys)),
                    }
                )
    return cells, boot


def quantile_block(cells: list[dict], boot: dict) -> tuple[dict, dict]:
    result, ordinals = {}, {}
    for algorithm in ALGORITHMS:
        for modality in MODALITIES:
            curve = [
                next(
                    c["success_3seed_mean"]
                    for c in cells
                    if (c["algorithm"], c["modality"], c["size"]) == (algorithm, modality, s)
                )
                for s in SIZES
            ]
            complete = all(c["complete"] for c in cells if (c["algorithm"], c["modality"]) == (algorithm, modality))
            matrix = np.stack([boot[(algorithm, modality, s)] for s in SIZES], axis=1)
            entry = {"curve_3seed_mean": dict(zip(map(str, SIZES), curve, strict=True)), "complete_curve": complete}
            for name, q in QUANTILES.items():
                observed = n_quantile(SIZES, curve, q)
                draws = np.array([n_quantile(SIZES, row, q)["ordinal"] for row in matrix])
                ordinals[(algorithm, modality, name)] = draws
                ordered = sorted(v for v in draws if not math.isnan(v))
                low, high = percentile(ordered, 0.025), percentile(ordered, 0.975)
                entry[name] = {
                    **{k: v for k, v in observed.items() if k != "ordinal"},
                    "ci95": [ordinal_label(low, SIZES[0], SIZES[-1]), ordinal_label(high, SIZES[0], SIZES[-1])]
                    if ordered
                    else None,
                    "bootstrap_censoring": {
                        "left": int(np.sum(draws == -math.inf)),
                        "right": int(np.sum(draws == math.inf)),
                        "missing": int(np.sum(np.isnan(draws))),
                    },
                }
            result[f"{algorithm}/{modality}"] = entry
    return result, ordinals


def contrast_pairs():
    for axis, fixed, a, b in SUCCESS_CONTRASTS:
        if axis == "algorithm":
            yield f"{a}-{b} | {fixed}", (a, fixed), (b, fixed)
        else:
            yield f"{a}-{b} | {fixed}", (fixed, a), (fixed, b)


def success_contrasts(table: Table, indices: np.ndarray) -> list[dict]:
    tests = []
    for size in SIZES:
        for name, (alg_a, mod_a), (alg_b, mod_b) in contrast_pairs():
            a = table.matrix(learned_keys(alg_a, mod_a, size))
            b = table.matrix(learned_keys(alg_b, mod_b, size))
            # Paired by task: keep only (seed, task) pairs observed in both arms.
            both = ~np.isnan(a) & ~np.isnan(b)
            a, b = np.where(both, a, np.nan), np.where(both, b, np.nan)
            if not both.any():
                tests.append({"contrast": name, "size": size, "estimate": None, "ci95": None, "p": None, "pairs": 0})
                continue
            draws = seed_mean(a, indices) - seed_mean(b, indices)
            tests.append(
                {
                    "contrast": name,
                    "size": size,
                    "estimate": seed_mean(a) - seed_mean(b),
                    "ci95": ci(draws),
                    "p": two_sided_p(draws),
                    "pairs": int(both.sum()),
                    "complete": bool(both.sum() == len(SEEDS) * len(table.tasks)),
                }
            )
    ps = [t["p"] if t["p"] is not None and not math.isnan(t["p"]) else 1.0 for t in tests]
    for test, adjusted in zip(tests, holm(ps), strict=True):
        if test["p"] is None or math.isnan(test["p"]):
            test["holm_p"], test["verdict"] = None, "MISSING"
        else:
            test["holm_p"] = adjusted
            test["verdict"] = "SEPARATED" if adjusted < ALPHA else "NOT_SEPARATED"
    return tests


def quantile_contrasts(ordinals: dict, quantiles: dict) -> list[dict]:
    results = []
    for name in QUANTILES:
        for label, (alg_a, mod_a), (alg_b, mod_b) in contrast_pairs():
            a = ordinals[(alg_a, mod_a, name)]
            b = ordinals[(alg_b, mod_b, name)]
            valid = ~np.isnan(a) & ~np.isnan(b)
            # Ordinal comparison keeps censored draws (-inf/+inf) without subtracting infinities.
            sign = (np.greater(a, b).astype(float) - np.less(a, b).astype(float))[valid]
            observed_a = quantiles[f"{alg_a}/{mod_a}"][name]
            observed_b = quantiles[f"{alg_b}/{mod_b}"][name]
            difference = (
                observed_a["log2"] - observed_b["log2"]
                if observed_a["censoring"] == observed_b["censoring"] == "none"
                else None
            )
            both_finite = valid & np.isfinite(a) & np.isfinite(b)
            finite = a[both_finite] - b[both_finite]
            results.append(
                {
                    "quantile": name,
                    "contrast": label,
                    "a": observed_a["label"],
                    "b": observed_b["label"],
                    "log2_ratio": difference,
                    "log2_ratio_ci95_uncensored_draws": ci(finite) if finite.size else None,
                    "uncensored_draws": int(finite.size),
                    "p_a_lower": float(np.mean(sign < 0)) if sign.size else None,
                    "p_a_higher": float(np.mean(sign > 0)) if sign.size else None,
                    "p_tie": float(np.mean(sign == 0)) if sign.size else None,
                    "p_two_sided": two_sided_p(sign) if sign.size else None,
                    "family": "descriptive (outside the 54-test Holm family)",
                }
            )
    return results


def compute_matched_block(table: Table, indices: np.ndarray) -> dict:
    control_key = [("control", "bfs", "text-state", 2048, 8, 17)]
    control = table.matrix(control_key)
    result = {
        "cell": "bfs text-state 2,048 records x 8 epochs, seed 17 (512 updates)",
        "success": seed_mean(control) if np.any(~np.isnan(control)) else None,
        "episodes_present": int(np.sum(~np.isnan(control))),
        **episode_summary(table.rows(control_key)),
        "comparisons": {},
    }
    for size in (2048, 16384):
        for label, seeds in (("seed17_paired", (17,)), ("3seed_mean", SEEDS)):
            other = table.matrix(learned_keys("bfs", "text-state", size, seeds))
            # control is a single seed: compare against each reference seed's tasks, pairs kept per task.
            other_mean = _nanmean(other, 0)[None, :]
            both = ~np.isnan(control) & ~np.isnan(other_mean)
            a, b = np.where(both, control, np.nan), np.where(both, other_mean, np.nan)
            key = f"control-minus-{size}x1-{label}"
            if not both.any():
                result["comparisons"][key] = {"estimate": None, "pairs": 0}
                continue
            draws = seed_mean(a, indices) - seed_mean(b, indices)
            result["comparisons"][key] = {
                "estimate": seed_mean(a) - seed_mean(b),
                "ci95": ci(draws),
                "p_two_sided": two_sided_p(draws),
                "pairs": int(both.sum()),
                "family": "descriptive (outside the 54-test Holm family)",
            }
    return result


def reference_block(table: Table, indices: np.ndarray) -> dict:
    result = {}
    for algorithm in ALGORITHMS:
        for condition, seeds in (("exact_reference", (17,)), ("random_valid", RANDOM_VALID_SEEDS)):
            keys = [(condition, algorithm, "text-state", None, None, seed) for seed in seeds]
            matrix = table.matrix(keys)
            present = int(np.sum(~np.isnan(matrix)))
            result[f"{condition}/{algorithm}"] = {
                "modality": "text-state (declared modality-independent)",
                "seeds": list(seeds),
                "success": seed_mean(matrix) if present else None,
                "success_per_seed": {
                    str(seed): (float(_nanmean(matrix[i], 0)) if np.any(~np.isnan(matrix[i])) else None)
                    for i, seed in enumerate(seeds)
                },
                "ci95": ci(seed_mean(matrix, indices)) if present else None,
                "episodes_present": present,
                "episodes_expected": len(seeds) * len(table.tasks),
                **episode_summary(table.rows(keys)),
            }
        for modality in MODALITIES:
            keys = [("base", algorithm, modality, None, None, None)]
            matrix = table.matrix(keys)
            present = int(np.sum(~np.isnan(matrix)))
            result[f"pretrained_base/{algorithm}/{modality}"] = {
                "success": seed_mean(matrix) if present else None,
                "ci95": ci(seed_mean(matrix, indices)) if present else None,
                "episodes_present": present,
                "episodes_expected": len(table.tasks),
                **episode_summary(table.rows(keys)),
            }
    return result


def primary(table: Table, indices: np.ndarray) -> dict:
    cells, boot = cell_block(table, indices)
    quantiles, ordinals = quantile_block(cells, boot)
    tests = success_contrasts(table, indices)
    return {
        "cells": cells,
        "n_quantiles": quantiles,
        "success_contrasts": {
            "family_size": len(tests),
            "adjustment": "Holm over all success contrasts (9 per size x 6 sizes); missing tests enter as p=1",
            "rule": "SEPARATED iff Holm-adjusted two-sided bootstrap p < 0.05",
            "p_definition": "min(1, 2*min(P*(diff<=0), P*(diff>=0))) over bootstrap draws of the paired difference",
            "tests": tests,
            "separated": [f"{t['contrast']} @ {t['size']}" for t in tests if t["verdict"] == "SEPARATED"],
        },
        "n_quantile_contrasts": quantile_contrasts(ordinals, quantiles),
    }


def node_choice_block(source: dict | None, path: str, quantiles: dict) -> dict:
    execution = {key: {name: value[name]["label"] for name in QUANTILES} for key, value in quantiles.items()}
    if source is None:
        return {"status": "MISSING_SOURCE", "source": path, "execution_n_quantiles": execution}
    primary_block = source["primary"]
    return {
        "status": "REUSED (0 GPU-h)",
        "source": path,
        "source_status": source.get("status"),
        "level": "node choice (#136/#138: which frontier node to expand), not operation execution",
        "training": {
            "records_per_algorithm": 2048,
            "menu_orders": 2,
            "samples": 4096,
            "updates": 128,
            "gpu_hours_per_cell": 1.89,
            "reference": "docs/experiments/choice-frontier/issue-138-protocol.md L10-13, L64",
        },
        "metric": "M1 = trapezoidal solve-versus-budget AUC; different 12-task panel; not the #147 success metric",
        "m1_learned_3seed_mean": primary_block.get("m1_learned_3seed_mean"),
        "m1_learned_3seed_mean_ci95": primary_block.get("m1_learned_3seed_mean_ci95"),
        "d3_vs_random_valid": primary_block.get("D3"),
        "d3_ci95": primary_block.get("ci95"),
        "verdict_138": primary_block.get("verdict"),
        "execution_n_quantiles": execution,
        "comparison": (
            f"#138 node-choice verdict vs random_valid: {primary_block.get('verdict')} with 2,048 choices x 2 menu "
            "orders (4,096 samples) per algorithm; operation-execution cost on this panel is the N50/N90 above"
        ),
    }


def missingness(table: Table, rows: list[dict], expected: dict | None) -> dict:
    learned = {(k[1], k[2], k[3], k[5]) for k in table.cells if k[0] == "learned"}
    missing_cells = [
        f"{a}/{m}/{s}/seed-{seed}"
        for a in ALGORITHMS
        for m in MODALITIES
        for s in SIZES
        for seed in SEEDS
        if (a, m, s, seed) not in learned
    ]
    partial_cells = [
        f"{k[1]}/{k[2]}/{k[3]}/seed-{k[5]}"
        for k, tasks in table.cells.items()
        if k[0] == "learned" and len(tasks) < len(table.tasks)
    ]
    return {
        "episodes_in_table": len(rows),
        "expected_episodes": (expected or {}).get("expected"),
        "missing_episode_files": len((expected or {}).get("missing", [])),
        "partial_journals": len((expected or {}).get("partial", [])),
        "replay_mismatches": len((expected or {}).get("mismatches", [])),
        "replay_verified": (expected or {}).get("replay_verified"),
        "learned_cells_expected": len(ALGORITHMS) * len(MODALITIES) * len(SIZES) * len(SEEDS),
        "learned_cells_missing": missing_cells,
        "learned_cells_partial": partial_cells,
        "complete": not missing_cells and not partial_cells and not (expected or {}).get("missing"),
    }


def analyze(
    rows: list[dict[str, Any]],
    tasks: list[str],
    *,
    task_domains: dict[str, str] | None = None,
    sufficiency: dict | None = None,
    node_choice: dict | None = None,
    node_choice_path: str = "",
    accounting: dict | None = None,
    draws: int = DRAWS,
) -> dict[str, Any]:
    table = Table(rows, tasks)
    indices = draw_indices(len(tasks), draws)
    main = primary(table, indices)
    result = {
        "study": "data-cost-v1",
        "status": "pre-registered #147 analysis",
        "bootstrap": dict(BOOTSTRAP_NOTE, draws=draws),
        "metrics": {
            "success": "invariant_valid_success within 2x reference decisions",
            "valid_op_rate": "accepted model operations / model calls (pooled over episodes; episode mean also given)",
            "first_invalid_step": (
                "1-based decision index of the first rejected operation; median over episodes with an invalid op "
                "+ censored count"
            ),
            "n_quantiles": (
                "log2-linear interpolation at the first upward crossing of the 3-seed mean curve; <=512 left-, "
                ">16384 right-censored"
            ),
        },
        "tasks": len(tasks),
        "missingness": missingness(table, rows, accounting),
        **main,
        "compute_matched_control": compute_matched_block(table, indices),
        "controls": reference_block(table, indices),
        "node_choice_comparison": node_choice_block(node_choice, node_choice_path, main["n_quantiles"]),
    }
    if sufficiency is None or task_domains is None:
        result["secondary_sufficiency"] = {"status": "MISSING_INPUT (sufficiency.json or task domains absent)"}
    else:
        failed = sorted(d for d, v in sufficiency.get("domains", {}).items() if v.get("verdict") != "PASS")
        kept = [task for task in tasks if task_domains.get(task) not in failed]
        if not kept:
            result["secondary_sufficiency"] = {
                "status": "every panel domain failed sufficiency",
                "failed_domains": failed,
            }
            return result
        secondary = primary(Table(rows, kept), draw_indices(len(kept), draws))
        result["secondary_sufficiency"] = {
            "status": (
                "secondary (descriptive); tasks of sufficiency-FAIL domains removed from every arm so contrasts "
                "stay paired"
            ),
            "failed_domains": failed,
            "tasks_kept": len(kept),
            "cells": [c for c in secondary["cells"] if c["modality"] != "text-state"],
            "n_quantiles": {k: v for k, v in secondary["n_quantiles"].items() if not k.endswith("text-state")},
            "success_contrasts": secondary["success_contrasts"],
        }
    return result


# --------------------------------------------------------------------------------------------- figure


def figure(analysis: dict, path_stem: str) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colours = {"text-state": "#1f77b4", "visual-state": "#d62728", "multimodal-state": "#2ca02c"}
    names = {"bfs": "BFS", "best_first_width": "BFWS"}
    x_all = [math.log2(s) for s in SIZES]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    for ax, algorithm in zip(axes, ALGORITHMS, strict=True):
        for modality in MODALITIES:
            cells = [c for c in analysis["cells"] if c["algorithm"] == algorithm and c["modality"] == modality]
            xs = [math.log2(c["size"]) for c in cells if c["success_3seed_mean"] is not None]
            ys = [c["success_3seed_mean"] for c in cells if c["success_3seed_mean"] is not None]
            lo = [c["ci95"][0] for c in cells if c["success_3seed_mean"] is not None]
            hi = [c["ci95"][1] for c in cells if c["success_3seed_mean"] is not None]
            if xs:
                ax.plot(xs, ys, marker="o", color=colours[modality], label=modality.replace("-state", ""))
                ax.fill_between(xs, lo, hi, color=colours[modality], alpha=0.15, linewidth=0)
            base = analysis["controls"].get(f"pretrained_base/{algorithm}/{modality}", {}).get("success")
            if base is not None:
                ax.axhline(base, color=colours[modality], linestyle=":", linewidth=0.8)
        exact = analysis["controls"].get(f"exact_reference/{algorithm}", {}).get("success")
        rv = analysis["controls"].get(f"random_valid/{algorithm}", {}).get("success")
        if exact is not None:
            ax.axhline(exact, color="black", linestyle="--", linewidth=1, label="exact reference")
        if rv is not None:
            ax.axhline(rv, color="grey", linestyle="-.", linewidth=1, label="random valid (5 seeds)")
        control = analysis["compute_matched_control"]
        if algorithm == "bfs" and control.get("success") is not None:
            ax.plot([math.log2(2048)], [control["success"]], marker="*", markersize=12, color="#9467bd",
                    linestyle="none", label="2,048 x 8 epochs (text)")  # fmt: skip
        ax.set_xticks(x_all, [f"{s:,}" for s in SIZES], rotation=30)
        ax.set_xlabel("training reference operations N (log2 scale)")
        ax.set_title(names[algorithm])
        ax.set_ylim(-0.02, 1.02)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=7, loc="best")
    axes[0].set_ylabel(f"success (3-seed mean, {analysis['tasks']} tasks)")
    fig.text(0.5, -0.02, "bands: 95% task-cluster bootstrap; dotted: untrained base per observation",
             ha="center", fontsize=7)  # fmt: skip
    fig.tight_layout()
    outputs = []
    for suffix in ("pdf", "png"):
        target = f"{path_stem}.{suffix}"
        fig.savefig(target, dpi=200, bbox_inches="tight")
        outputs.append(target)
    plt.close(fig)
    return outputs
