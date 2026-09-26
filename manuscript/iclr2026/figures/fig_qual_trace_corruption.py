"""Same main-grid greedy adapters under text and visual corruptions.

Evidence: outputs/expanded-study/v1/modality-stress/episodes/{text,multimodal,visual}-state/
expanded-final__blocksworld-expanded-911101/best_first_add_greedy-
{text-shuffled,visual-blank,visual-degraded}-learned_adapter.json.gz;
baseline/episodes/.../best_first_add_greedy-process_sft.json.gz (checkpoints);
configs/experiments/expanded-study/modality-stress-protocol.json seed;
examples/planning_benchmark_slice/expanded_modality_stress.py _corrupt_image;
panel-v2/views/blocksworld-expanded-911101/scenes/catalog.json.gz.
"""
import json

import matplotlib.pyplot as plt
from PIL import Image

from _style import EVIDENCE_ROOT
from fig_qual_trace_solved import CATALOG, TASK, INK, MUTED, ORANGE, episode, gz, scene, save, text

STRESS = "outputs/expanded-study/v1/modality-stress/episodes"


def main():
    protocol = json.loads((EVIDENCE_ROOT / "configs/experiments/expanded-study/modality-stress-protocol.json").read_text())
    assert protocol["corruption_master_seed"] == 42613
    catalog = gz(CATALOG)
    clean = scene(catalog, 0)
    assert clean.size == (128, 128)
    blank = Image.new(clean.mode, (128, 128), (128, 128, 128))
    degraded = clean.resize((16, 16), Image.Resampling.BILINEAR).resize((128, 128), Image.Resampling.NEAREST)
    reports = {}
    for obs, corruption in (("text-state", "text-shuffled"), ("multimodal-state", "text-shuffled"),
                             ("visual-state", "visual-blank"), ("visual-state", "visual-degraded"),
                             ("multimodal-state", "visual-blank"), ("multimodal-state", "visual-degraded")):
        rel = f"{STRESS}/{obs}/{TASK}/best_first_add_greedy-{corruption}-learned_adapter.json.gz"
        report = gz(rel)
        baseline = episode(obs, "best_first_add_greedy", "process_sft")
        assert report["output"] == rel and report["checkpoint"] == baseline["checkpoint"]
        assert report["modality"] == obs and report["algorithm"] == "best_first_add_greedy"
        assert ["current-state", 0, 0] in report["events"][0]["view"]["input_pages"]
        assert set(catalog["states"][0]["atoms"]) == set(catalog["states"][report["events"][0]["view"]["state"]]["atoms"])
        reports[obs, corruption] = report
    text_ep = reports["text-state", "text-shuffled"]
    multi_ep = reports["multimodal-state", "text-shuffled"]
    for obs, report, idx in (("text-state", text_ep, 1), ("multimodal-state", multi_ep, 2)):
        result = report["result"]
        assert (result["termination_reason"], result["decision_count"], result["expansion_count"]) == (
            "deterministic_invalid_operation", idx + 1, 0 if obs == "text-state" else 1)
        assert all(e["accepted"] for e in report["events"][:idx]) and not report["events"][idx]["accepted"]
        assert report["events"][idx]["raw_output"] == report["events"][0]["raw_output"] == (
            '{"action":{"args":["b1","b4"],"name":"unstack"},"source_state_id":"s0"}')
        assert report["events"][idx]["input"]["current"]["state_id"] == ("s0" if obs == "text-state" else "s1")
        assert set(catalog["states"][report["events"][idx]["view"]["state"]]["atoms"]) == (
            set(catalog["states"][0 if obs == "text-state" else 1]["atoms"]))
    assert [row[0] for row in text_ep["events"][1]["input"]["successor_candidates"]["rows"]] == [
        ["unstack", "b3", "b5"]]
    for (obs, corruption), report in reports.items():
        if corruption == "text-shuffled":
            continue
        assert report["result"]["termination_reason"] == "goal_reached"
        assert (report["result"]["decision_count"], report["result"]["expansion_count"]) == (18, 6)
        assert all(e["accepted"] for e in report["events"])
    fig = plt.figure(figsize=(5.5, 1.4), facecolor="white")
    text(fig, .022, .91, "Test-time corruption · same task and greedy checkpoints", size=7.4, weight="bold")
    # Evidence: cached unlabelled state-000000.png. Blank and degraded are
    # generated exactly as expanded_modality_stress.py::_corrupt_image.
    for x, label, image in ((.025, "Clean", clean), (.155, "Blank", blank), (.285, "Degraded", degraded)):
        ax = fig.add_axes([x, .215, .105, .48]); ax.imshow(image, interpolation="nearest"); ax.axis("off")
        text(fig, x+.052, .135, label, size=6.1, ha="center")
    text(fig, .025, .73, "Policy scene variants", size=6.4, color=MUTED, weight="bold")
    text(fig, .435, .728, "Shuffled text", size=6.5, color=ORANGE, weight="bold")
    text(fig, .435, .604, "Text: repeats unstack(b1,b4) at call 2", size=6.1)
    text(fig, .435, .501, "Multimodal: repeats it at call 3", size=6.1)
    text(fig, .435, .398, "Both rejected; previously submitted from s0", size=6.1)
    text(fig, .435, .265, "Blank / degraded images", size=6.5, weight="bold", color="#009E73")
    text(fig, .435, .14, "Visual + multimodal: goal in 18 calls each", size=6.1)
    save(fig, "fig_qual_trace_corruption")
    print("Q3: text rejected at decisions 2/3; blank/degraded visual + multimodal solve in 18")


if __name__ == "__main__":
    main()
