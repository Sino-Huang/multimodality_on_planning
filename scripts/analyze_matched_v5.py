#!/usr/bin/env python3
"""Replay and analyze all retained matched v5 outcomes without model calls."""

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from examples.planning_benchmark_slice.matched_analysis import analyze  # noqa: E402
from examples.planning_benchmark_slice.matched_tasks import Progress  # noqa: E402
from examples.planning_benchmark_slice.scene_assets import read_json  # noqa: E402


def csv_table(path, rows):
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def tables(result):
    episodes = result["episodes"]
    flat = [{k: v for k, v in r.items() if k not in ("failures", "common_prefix")} for r in episodes]
    prefixes = [
        {
            "task_id": r["task_id"],
            "algorithm": r["algorithm"],
            "modality": r["modality"],
            "arm": r["arm"],
            "common_cap": r["common_cap"],
            **r["common_prefix"],
        }
        for r in episodes
    ]
    failures = [
        {"episode": r["episode"], "modality": r["modality"], "algorithm": r["algorithm"], "arm": r["arm"], **failure}
        for r in episodes
        for failure in r["failures"]
    ]
    index = {(r["task_id"], r["algorithm"], r["modality"], r["arm"]): r for r in episodes}
    gaps = []
    for row in episodes:
        if row["arm"] != "process_sft":
            continue
        for arm in ("pretrained_base", "random_valid", "exact_reference"):
            ref = index.get((row["task_id"], row["algorithm"], row["modality"], arm))
            if ref is None:
                continue
            both = row["success"] and ref["success"]
            gaps.append(
                {
                    "task_id": row["task_id"],
                    "algorithm": row["algorithm"],
                    "modality": row["modality"],
                    "control": arm,
                    "success_difference": int(row["success"]) - int(ref["success"]),
                    "invalid_operation_difference": row["invalid_operations"] - ref["invalid_operations"],
                    "decision_difference": row["decisions"] - ref["decisions"],
                    "expansion_difference": row["expansions"] - ref["expansions"],
                    "both_successful": both,
                    "solution_cost_difference_on_joint_success": row["solution_unit_action_cost"]
                    - ref["solution_unit_action_cost"]
                    if both
                    else None,
                }
            )
    return {
        "episodes.csv": flat,
        "common-prefixes.csv": prefixes,
        "rejections.csv": failures,
        "control-gaps.csv": gaps,
        "coverage.csv": result["coverage"],
        "summary.csv": [{k: v for k, v in r.items() if k != "terminations"} for r in result["summaries"]],
        "paired-contrasts.csv": [
            {
                "algorithm": r["algorithm"],
                "arm": r["arm"],
                "metric": r["metric"],
                "left": r["left_minus_right"][0],
                "right": r["left_minus_right"][1],
                "complete_paired_coverage": r["complete_paired_coverage"],
                **(r["estimate"] or {"difference": None, "lower": None, "upper": None, "whole_problems": None}),
            }
            for r in result["paired_contrasts"]
        ],
    }


def figure(result, output):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    fig, ax = plt.subplots(figsize=(9, 4.5))
    modalities = ["text-state", "visual-state", "multimodal-state"]
    arms = ["pretrained_base", "process_sft", "random_valid", "exact_reference"]
    for i, arm in enumerate(arms):
        counts = [
            next(r["successes"] for r in result["summaries"] if r["modality"] == m and r["arm"] == arm)
            for m in modalities
        ]
        ax.bar(np.arange(3) + (i - 1.5) * 0.19, counts, width=0.19, label=arm.replace("_", " "))
    ax.set_xticks(range(3), ["Text", "Visual", "Multimodal"])
    ax.set_ylim(0, 13)
    ax.set_ylabel("Invariant-valid successes / 12 declared cases")
    ax.set_title("V5: three whole problems x four algorithms; one training seed")
    ax.legend(fontsize=8, loc="upper left", bbox_to_anchor=(1, 1))
    fig.text(
        0.02,
        0.01,
        "Random-valid is oracle-assisted. Counts do not establish modality superiority or equal information.",
        fontsize=8,
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(output / "success-counts.png", dpi=180)
    fig.savefig(output / "success-counts.pdf")
    plt.close(fig)


def narrative(result):
    rows = result["episodes"]
    sft = [r for r in rows if r["arm"] == "process_sft"]
    rejected = sum(r["invalid_operations"] for r in sft)
    missing = sum(r["status"] == "missing" for r in result["coverage"])
    censored = sum(r["common_prefix"]["censored_at_common_cap"] for r in rows)
    claims = [
        {
            "id": "coverage",
            "text": f"All {len(rows)} available episodes were independently replayed; {missing} declared "
            f"bindings are missing and {len(result['infrastructure_stops'])} evaluation "
            f"infrastructure stops are recorded.",
            "evidence": "analysis.json: coverage, infrastructure_stops; source episode paths are in each row",
        },
        {
            "id": "validity",
            "text": f"SFT has {rejected} invalid operations across {len(sft)} episodes. On this panel, "
            f"every unsuccessful SFT episode terminates on an invalid operation; this does not "
            f"identify what a corrected policy would do afterward.",
            "evidence": "episodes.csv: arm=process_sft, invalid_operations and termination; rejections.csv",
        },
        {
            "id": "prefix",
            "text": f"The reference-derived common caps are Storage 12, Blocksworld 6 and Ferry 8 "
            f"decisions. {censored} observed traces extend beyond these caps, so all observed "
            f"terminal outcomes remain unchanged here.",
            "evidence": "common-prefixes.csv: common_cap, observed_decisions, censored_at_common_cap",
        },
        {
            "id": "curriculum",
            "text": "The separate #67 development experiment reports staged, shuffled and mixed-order "
            "success of 60/60 each, with zero invalid operations. Random-valid and exact controls "
            "also reach 100%; the three paired curriculum success intervals are [0,0].",
            "evidence": result["curriculum_source"] + ": condition_results, curriculum_conclusion, training, coverage",
        },
        {
            "id": "cost",
            "text": f"Cumulative recorded evaluation stage wall time is "
            f"{result['cumulative_stage_seconds']['evaluate']:.2f} seconds. Episode/call timings "
            f"and token counts are measured separately; early invalid termination reduces consumed "
            f"work and is not search efficiency.",
            "evidence": "analysis.json: cumulative_stage_seconds; episodes.csv; "
            "outputs/matched_modalities/v2/budget.json",
        },
    ]
    # Assert the specific narrative against source-derived rows rather than silently
    # repeating it if a later study changes its outcomes.
    assert all(r["termination"] == "deterministic_invalid_operation" for r in sft if not r["success"])
    assert {r["domain"]: r["common_cap"] for r in rows} == {"storage": 12, "blocksworld": 6, "ferry": 8}
    curriculum = result["curriculum"]
    assert all(
        curriculum["condition_results"]["process_sft"][cell]["invariant_valid_success"] == 1.0
        and curriculum["condition_results"]["process_sft"][cell]["episodes"] == 60
        and curriculum["condition_results"]["process_sft"][cell]["invalid_operation_rate"] == 0
        for cell in ("staged", "shuffled", "mixed_order")
    )
    assert all(v == [0.0, 0.0, 0.0] for v in curriculum["curriculum_conclusion"]["pairwise_intervals"].values())
    lines = [
        "# Matched v5 analysis — #97 and #109",
        "",
        "Reproduce with `source ~/cd_vlaplan`, then `CUDA_VISIBLE_DEVICES='' python "
        "scripts/analyze_matched_v5.py`. "
        "Add `--check` for independent replay and read-only verification of the JSON, CSVs, "
        "report and claims. No model calls occur.",
        "",
        "| Modality / arm | Successes | Episodes without invalid operations | Invalid / decisions | Expansions |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in result["summaries"]:
        lines.append(
            f"| {row['modality']} / {row['arm']} | {row['successes']}/{row['expected']} | "
            f"{row['valid_operation_episodes']}/{row['observed']} | "
            f"{row['invalid_operations']}/{row['decisions']} | {row['expansions']} |"
        )
    lines += [
        "",
        *[f"**{c['id']}:** {c['text']} Evidence: `{c['evidence']}`.\n" for c in claims],
        "Operation validity and search quality are distinct. Random-valid is an "
        "oracle-assisted programmatic valid-operation control, "
        "while SFT must emit the operation schema and search bookkeeping itself. Both receive "
        "candidate/Search Memory information; "
        "the comparison does not isolate intrinsic planning ability. Conditional success among"
        " validity-surviving episodes is selected, "
        "not the counterfactual success of a repaired model.",
        "",
        "Runtime invariant flags differ by family: BFWS reports maintained runtime invariants "
        "even on rejected operations. "
        "`runtime_reported_invariants_hold` is preserved; `all_operations_valid` is the "
        "uniform zero-invalid-charge measure. "
        "Rejected attempts never imply that an invalid physical transition was executed.",
        "",
        "`rejections.csv` preserves verbatim replay rejection messages. Categories are "
        "descriptive message classifications. "
        "BFS sometimes retains only a generic validity rejection; such rows remain unresolved "
        "rather than being invented as "
        "applicability/effect failures. Absence of an explicit category is not proof that its "
        "underlying error could not occur.",
        "",
        "`episodes.csv` includes observed search costs and successful solution lengths in unit"
        " actions recovered from trusted "
        "controller g-values or transition provenance. Failed episodes have no solution cost. "
        "`control-gaps.csv` reports each "
        "SFT/control paired difference; solution-cost differences use only joint successes, "
        "with that selection explicit.",
        "",
        "`common-prefixes.csv` is descriptive prefix accounting under the original "
        "model-visible budgets, not a rerun with "
        "different prompts or a prediction of unobserved continuations. Primary caps remain "
        "twice matching exact decisions "
        "and matching exact expansions; no new model budget is used.",
        "",
        "The analysis unit is the whole problem: only three held-out problems and one training seed. "
        "`analysis.json` contains all per-algorithm, per-arm pairwise modality contrasts for "
        "success, validity, decisions and "
        "expansions. Intervals use 10,000 paired whole-problem bootstrap samples, seed 1729, "
        "95% percentile bounds. "
        "The same problem-index samples preserve blocks across comparisons. These tiny-panel "
        "intervals do not establish "
        "broad superiority, training-seed variance or independent decision-level replication.",
        "",
        "V5 matches training exposure, not lossless information. Initial/current images are "
        "unlabelled 128px PNGs, "
        "resized to 256px by the processor; identities can disappear, as in numbered puzzle "
        "tiles. Static-context/goal pages "
        "and shared candidate/Search Memory information still contain text. This is not a "
        "purely image-only interface.",
        "",
        "The #67 result is separate: 12 cost-qualified development tasks, five rollout seeds "
        "per trained curriculum adapter, "
        "one training seed per cell, 522 updates and two epochs. Its frozen +/-0.05 "
        "practical-equivalence finding is limited "
        "by complete control saturation. It is not a matched text baseline or a "
        "curriculum-by-modality interaction. "
        "Historical #75/#76 schedules remain separate and are not pooled. The original "
        "h-max/landmark representation "
        "question remains unperformed; #67's replacement compares order within additive best-first.",
        "",
        "![Descriptive success counts](success-counts.png)",
        "",
        "PDF export: [success-counts.pdf](success-counts.pdf). Figure bars are counts over "
        "algorithm/problem cases, "
        "not independent samples. Numerical support is in summary.csv; all coverage and source"
        " links are in coverage.csv.",
        "",
    ]
    return claims, "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="replay and verify existing analysis without rewriting")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/experiments/matched-modalities/analysis-v5")
    args = parser.parse_args()
    study = read_json(ROOT / "configs/experiments/matched-modalities/study-v5.json")
    with Progress() as progress:
        result = analyze(ROOT, study, progress)
        rendered = tables(result)
        claims, report = narrative(result)
        if args.check:
            if read_json(args.output / "analysis.json") != result:
                raise ValueError("analysis differs from replayed evidence")
            if read_json(args.output / "claims.json") != claims or (args.output / "README.md").read_text() != report:
                raise ValueError("claims/report differ from replayed evidence")
            import io

            for name, rows in rendered.items():
                expected = io.StringIO(newline="")
                if rows:
                    writer = csv.DictWriter(expected, fieldnames=list(rows[0]))
                    writer.writeheader()
                    writer.writerows(rows)
                with (args.output / name).open(newline="") as f:
                    if f.read() != expected.getvalue():
                        raise ValueError(f"table differs from replayed evidence: {name}")
        else:
            args.output.mkdir(parents=True, exist_ok=True)
            (args.output / "analysis.json").write_text(json.dumps(result, indent=2) + "\n")
            (args.output / "claims.json").write_text(json.dumps(claims, indent=2) + "\n")
            (args.output / "README.md").write_text(report)
            for name, rows in rendered.items():
                csv_table(args.output / name, rows)
            figure(result, args.output)
        progress(
            "analysis:complete",
            completed=len(result["episodes"]),
            total=144,
            outcome="PASS" if result["complete_coverage"] else "PARTIAL",
            model_calls=0,
        )


if __name__ == "__main__":
    main()
