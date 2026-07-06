from __future__ import annotations

import argparse
from pathlib import Path

from .verifiers import run_cli, validate_jsonl_schema

parser = argparse.ArgumentParser()
parser.add_argument("--schema", required=True)
parser.add_argument("--jsonl", action="append", required=True)

if __name__ == "__main__":
    run_cli(validate_jsonl_schema, parser, lambda a: {"schema": Path(a.schema), "jsonl_paths": [Path(path) for path in a.jsonl]})
