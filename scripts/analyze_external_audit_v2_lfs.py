#!/usr/bin/env python
"""Analyzer for the #142 external identity audit on LLM-First Search.

Frozen protocol: ``docs/experiments/external-audit/issue-142-protocol.md``. Reads the episode logs
written by ``scripts/run_external_audit_v2_lfs.py`` and its ``replay.json`` (which must report 0
missing and 0 mismatched episodes in both arms), and writes ``identity-audit.json``.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "external-audit" / "v2"
SEEDS = (17, 5077, 6131, 7409, 8527)
BOOT_SEED, BOOT_DRAWS = 133, 10_000
SATURATION = 0.9
EQUIV_MARGIN = 0.05
MULTIPLIERS = (1.0, 1.25, 1.5, 1.75, 2.0)  # decision-budget curve: random wins within m x reference expansions
# Paper Table 2, LFS with GPT-4o, WinRate (%) per audited configuration.
PUBLISHED_LFS_GPT4O = {"cd3": 100.00, "cd5": 63.16, "cd7": 47.37, "su4": 96.84}
UPSTREAM = {"repo": "https://github.com/NathanHerr/LLM-First-Search",
            "commit": "3025bdaa3add6f41388c1d5a6d354522489d312e", "license": "Apache-2.0"}


def first_divergence(a: list, b: list) -> int | None:
    for i, (x, y) in enumerate(zip(a, b, strict=False)):
        if x != y:
            return i
    return None if len(a) == len(b) else min(len(a), len(b))


def sign_flip_p(diffs: list[float], unit: float = 0.2) -> float:
    """Exact two-sided sign-flip permutation p-value of the mean per-task difference.

    Differences lie on the grid ``unit`` (reference in {0,1} minus a mean of five binaries), so the
    null distribution of the signed sum is computed exactly by convolution over all 2^n sign vectors.
    """
    k = [abs(round(d / unit)) for d in diffs]
    assert all(abs(abs(d) - ki * unit) < 1e-9 for d, ki in zip(diffs, k)), "difference off the 0.2 grid"
    total = sum(k)
    dist = np.zeros(2 * total + 1)
    dist[total] = 1.0
    for ki in k:
        if ki:
            dist = 0.5 * (np.roll(dist, ki) + np.roll(dist, -ki))
    obs = abs(round(sum(diffs) / unit))
    sums = np.arange(-total, total + 1)
    return float(dist[np.abs(sums) >= obs].sum())


def bootstrap_ci(values: np.ndarray, rng: np.random.Generator) -> list[float]:
    idx = rng.integers(0, len(values), size=(BOOT_DRAWS, len(values)))
    means = values[idx].mean(axis=1)
    return [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))]


def contrast(ref: np.ndarray, rnd: np.ndarray) -> dict:
    """Per-task reference success minus mean random_valid success (task-cluster bootstrap + sign flip)."""
    d = ref - rnd
    rng = np.random.default_rng(BOOT_SEED)
    ratio_idx = rng.integers(0, len(d), size=(BOOT_DRAWS, len(d)))
    ref_b, rnd_b = ref[ratio_idx].mean(axis=1), rnd[ratio_idx].mean(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio_b = np.where(ref_b > 0, rnd_b / ref_b, np.nan)
    rng = np.random.default_rng(BOOT_SEED)
    ci = bootstrap_ci(d, rng)
    return {
        "mean_difference_reference_minus_random": float(d.mean()),
        "bootstrap_95ci": ci,
        "equivalent_within_margin": bool(-EQUIV_MARGIN <= ci[0] and ci[1] <= EQUIV_MARGIN),
        "equivalence_margin": EQUIV_MARGIN,
        "sign_flip_p_two_sided_exact": sign_flip_p(d.tolist()),
        "tasks_reference_better": int((d > 0).sum()),
        "tasks_random_better": int((d < 0).sum()),
        "tasks_tied": int((d == 0).sum()),
        "random_over_reference_ratio": float(rnd.mean() / ref.mean()) if ref.mean() > 0 else None,
        "random_over_reference_ratio_bootstrap_95ci": [float(np.nanpercentile(ratio_b, 2.5)),
                                                       float(np.nanpercentile(ratio_b, 97.5))],
        "bootstrap": {"unit": "task", "seed": BOOT_SEED, "draws": BOOT_DRAWS, "interval": "percentile"},
        "descriptive_only": "sign-flip p-value and intervals are descriptive; the verdict uses the fixed rule",
    }


def verdict(identical: int, checked: int, ref: float, rnd: float) -> tuple[bool, str]:
    saturation = bool(rnd >= SATURATION * ref)
    if identical == checked:
        return saturation, "IDENTICAL"
    return saturation, "SATURATED" if saturation else "CHOICE_REGISTERED"


def summarize(tasks: list[dict], eps: dict) -> dict:
    pairs_checked = pairs_identical = 0
    divergences: list[int] = []
    ref_s, rnd_paper, rnd_matched = [], [], []
    per_seed = {s: [] for s in SEEDS}
    per_seed_matched = {s: [] for s in SEEDS}
    for t in tasks:
        ref = eps[(t["task"], None)]
        ref_s.append(float(ref["won"]))
        row, row_m = [], []
        for s in SEEDS:
            ep = eps[(t["task"], s)]
            pairs_checked += 1
            idx = first_divergence(ref["decisions"], ep["decisions"])
            if idx is None and ref["won"] == ep["won"]:
                pairs_identical += 1
            else:
                divergences.append(0 if idx is None else idx)
            matched = ep["won"] and ep["steps"] <= ref["steps"]
            row.append(float(ep["won"]))
            row_m.append(float(matched))
            per_seed[s].append(float(ep["won"]))
            per_seed_matched[s].append(float(matched))
        rnd_paper.append(statistics.fmean(row))
        rnd_matched.append(statistics.fmean(row_m))
    ref_a, rp, rm = np.array(ref_s), np.array(rnd_paper), np.array(rnd_matched)
    n = len(tasks)
    sat_p, v_p = verdict(pairs_identical, pairs_checked, ref_a.mean(), rp.mean())
    sat_m, v_m = verdict(pairs_identical, pairs_checked, ref_a.mean(), rm.mean())
    return {
        "tasks": n,
        "pairs_checked": pairs_checked,
        "pairs_identical": pairs_identical,
        "pairs_divergent": pairs_checked - pairs_identical,
        "first_divergence_index": (
            {"median": int(statistics.median_low(divergences)), "min": min(divergences), "max": max(divergences),
             "pairs_diverging_at_0": sum(d == 0 for d in divergences)}
            if divergences else None
        ),
        "paper_budget": {
            "success": {"reference": float(ref_a.mean()),
                        "random_valid_per_seed": {str(s): float(np.mean(v)) for s, v in per_seed.items()},
                        "random_valid_mean": float(rp.mean())},
            "saturation": sat_p,
            "verdict": v_p,
            "contrast": contrast(ref_a, rp),
        },
        "matched_decision_budget": {
            "rule": "random_valid wins only if it wins within the reference's own number of expansions on the task",
            "success": {"reference": float(ref_a.mean()),
                        "random_valid_per_seed": {str(s): float(np.mean(v)) for s, v in per_seed_matched.items()},
                        "random_valid_mean": float(rm.mean())},
            "saturation": sat_m,
            "verdict": v_m,
            "contrast": contrast(ref_a, rm),
            "random_valid_decision_budget_curve": curve(tasks, eps),
        },
    }


def curve(tasks: list[dict], eps: dict) -> dict:
    """Descriptive: random_valid success within floor(m x reference expansions), trapezoidal AUC over m."""
    pts = []
    for m in MULTIPLIERS:
        pts.append(statistics.fmean(
            float(eps[(t["task"], s)]["won"] and eps[(t["task"], s)]["steps"] <= int(m * eps[(t["task"], None)]["steps"]))
            for t in tasks for s in SEEDS))
    auc = sum((b - a) * (pa + pb) / 2 for a, b, pa, pb in zip(MULTIPLIERS, MULTIPLIERS[1:], pts, pts[1:]))
    return {"multipliers": list(MULTIPLIERS), "random_valid_success": pts,
            "auc_normalized": auc / (MULTIPLIERS[-1] - MULTIPLIERS[0]),
            "reference_success_at_own_budget": statistics.fmean(float(eps[(t["task"], None)]["won"]) for t in tasks)}


def describe(tasks: list[dict], eps: dict) -> dict:
    ref = [eps[(t["task"], None)] for t in tasks]
    rnd = [eps[(t["task"], s)] for t in tasks for s in SEEDS]
    med = lambda xs: float(statistics.median(xs)) if xs else None  # noqa: E731
    term = lambda es: {k: sum(e["terminated"] == k for e in es) for k in sorted({e["terminated"] for e in es})}  # noqa: E731
    return {
        "expansions_median": {"reference": med([e["steps"] for e in ref]),
                              "random_valid": med([e["steps"] for e in rnd]),
                              "reference_wins": med([e["steps"] for e in ref if e["won"]]),
                              "random_valid_wins": med([e["steps"] for e in rnd if e["won"]])},
        "expansions_max": {"reference": max(e["steps"] for e in ref), "random_valid": max(e["steps"] for e in rnd)},
        "tokens_median": {"reference": med([e["total_tokens"] for e in ref]),
                          "random_valid": med([e["total_tokens"] for e in rnd])},
        "terminated": {"reference": term(ref), "random_valid": term(rnd)},
        "first_decision_options_median": med([e["n_options"][0] for e in ref + rnd if e["n_options"]]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-dir", default=str(OUT / "lfs"))
    args = parser.parse_args()
    run_dir = Path(args.run_dir)
    tasks = json.loads((run_dir / "tasks.json").read_text())
    replay = json.loads((run_dir / "replay.json").read_text())
    for arm in ("reference", "random_valid"):
        r = replay[arm]
        assert r["missing"] == 0 and r["mismatch"] == 0, f"replay {arm}: {r['missing']} missing, {r['mismatch']} mismatch"
    assert replay["reference"]["episodes"] == len(tasks), "replay did not cover every reference episode"
    eps = {}
    for t in tasks:
        eps[(t["task"], None)] = json.loads((run_dir / "episodes" / t["task"] / "reference-ref.json").read_text())
        for s in SEEDS:
            eps[(t["task"], s)] = json.loads((run_dir / "episodes" / t["task"] / f"random_valid-{s}.json").read_text())
    configs = list(dict.fromkeys(t["config"] for t in tasks))
    overall = summarize(tasks, eps)
    published = statistics.fmean(PUBLISHED_LFS_GPT4O[c] for c in configs) / 100
    audit = {
        "schema_version": "external_identity_audit_v2",
        "benchmark": "llm-first-search",
        "upstream": UPSTREAM,
        "interface_type": "C",
        "prediction": {"paper_budget": "SATURATED", "matched_decision_budget": "CHOICE_REGISTERED"},
        **overall,
        "verdict": overall["paper_budget"]["verdict"],
        "published_model_success": {
            "value": published,
            "source": ("Herr et al. arXiv 2506.05213 Table 2, LFS with GPT-4o, WinRate averaged over the audited "
                       f"configurations {configs} (equal game counts); per configuration {PUBLISHED_LFS_GPT4O}"),
        },
        "random_fraction_of_published": overall["paper_budget"]["success"]["random_valid_mean"] / published,
        "per_config": {c: summarize([t for t in tasks if t["config"] == c], eps) for c in configs},
        "supplementary": describe(tasks, eps),
        "replay": {arm: {k: replay[arm][k] for k in ("episodes", "match", "mismatch", "missing")}
                   for arm in ("reference", "random_valid")},
    }
    (run_dir / "identity-audit.json").write_text(json.dumps(audit, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: audit[k] for k in ("tasks", "pairs_checked", "pairs_identical", "verdict")}, indent=1))
    for key in ("paper_budget", "matched_decision_budget"):
        print(key, json.dumps({k: audit[key][k] for k in ("success", "verdict")}))


if __name__ == "__main__":
    main()
