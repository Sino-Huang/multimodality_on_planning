from __future__ import annotations

import argparse

from .verifiers import run_cli, verify_manifest_coverage

parser = argparse.ArgumentParser()
parser.add_argument("--accepted-manifest", required=True)
parser.add_argument("--diagnostics", required=True)

if __name__ == "__main__":
    run_cli(verify_manifest_coverage, parser, lambda a: {"accepted_manifest": __import__("pathlib").Path(a.accepted_manifest), "diagnostics": __import__("pathlib").Path(a.diagnostics)})
