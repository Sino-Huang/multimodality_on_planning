from __future__ import annotations

import argparse
from pathlib import Path

from .verifiers import run_cli, verify_no_smoke_sources

parser = argparse.ArgumentParser()
parser.add_argument("--dataset-root", required=True)
parser.add_argument("--forbidden-path", action="append", default=[])

if __name__ == "__main__":
    run_cli(verify_no_smoke_sources, parser, lambda a: {"dataset_root": Path(a.dataset_root), "forbidden_paths": a.forbidden_path})
