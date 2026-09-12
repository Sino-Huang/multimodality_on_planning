"""Run the four-hour multimodal feasibility study using the shared experiment runner."""

from run_visual_issue75 import ROOT, main

if __name__ == "__main__":
    raise SystemExit(main(default_config=ROOT / "configs/experiments/issue76/experiment.json"))
