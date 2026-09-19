"""Run the governed issue-66 additive greedy best-first experiment."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from scripts.run_best_first_issue65 import main as _run_development


def main(arguments: Sequence[str] | None = None) -> int:
    supplied = list(sys.argv[1:] if arguments is None else arguments)
    return _run_development(("--source-issue", "66", "--master-port", "29660", *supplied))


if __name__ == "__main__":
    raise SystemExit(main())
