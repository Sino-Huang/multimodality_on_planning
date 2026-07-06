from __future__ import annotations

import argparse
from pathlib import Path

from .verifiers import run_cli, verify_planner_attempts

parser = argparse.ArgumentParser()
parser.add_argument("--accepted-manifest", required=True)
parser.add_argument("--planner-attempts", required=True)
parser.add_argument("--planners", nargs="+", required=True)

if __name__ == "__main__":
    run_cli(verify_planner_attempts, parser, lambda a: {"accepted_manifest": Path(a.accepted_manifest), "planner_attempts": Path(a.planner_attempts), "planners": a.planners})
