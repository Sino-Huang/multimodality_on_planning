from __future__ import annotations

import argparse
from pathlib import Path

from .verifiers import run_cli, verify_determinism

parser = argparse.ArgumentParser()
parser.add_argument("--dataset-root", required=True)
parser.add_argument("--manifest", required=True)

if __name__ == "__main__":
    run_cli(verify_determinism, parser, lambda a: {"dataset_root": Path(a.dataset_root), "manifest": Path(a.manifest)})
