from __future__ import annotations

import argparse
from pathlib import Path

from .verifiers import run_cli, verify_domain_coverage

parser = argparse.ArgumentParser()
parser.add_argument("--accepted-manifest", required=True)
parser.add_argument("--dataset-root", required=True)
parser.add_argument("--domains", nargs="+", required=True)

if __name__ == "__main__":
    run_cli(verify_domain_coverage, parser, lambda a: {"accepted_manifest": Path(a.accepted_manifest), "dataset_root": Path(a.dataset_root), "domains": a.domains})
