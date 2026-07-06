from __future__ import annotations

import argparse
from pathlib import Path

from .verifiers import run_cli, verify_fidelity_labels

parser = argparse.ArgumentParser()
parser.add_argument("--dataset-root", required=True)

if __name__ == "__main__":
    run_cli(verify_fidelity_labels, parser, lambda a: {"dataset_root": Path(a.dataset_root)})
