"""Verify v6 teacher traces against the v7 incremental rolling context."""

from __future__ import annotations

import json
from pathlib import Path

from examples.planning_benchmark_slice.bfs_generation import _normalize_authority_input
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority
from examples.planning_benchmark_slice.search_context import verify_incremental_replay_contexts
from examples.planning_benchmark_slice.search_episode import _trace_limits

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TRACE_ROOT = _REPO_ROOT / "data" / "bfs_pilot_v6" / "exact-traces"
_MANIFEST = _TRACE_ROOT / "manifests" / "bfs-expert-traces.json"


def main() -> int:
    manifest = json.loads(_MANIFEST.read_bytes())
    traces = manifest["traces"]
    verified = 0
    for row in traces:
        domain_text, problem_text, _ = _normalize_authority_input(
            Path(row["source"]["domain_path"]).read_text(encoding="utf-8"),
            Path(row["source"]["problem_path"]).read_text(encoding="utf-8"),
        )
        authority = PDDLStateAuthority.from_pddl(domain_text, problem_text)
        limits = _trace_limits(authority, int(row["max_expansions"]))
        verify_incremental_replay_contexts(
            (_TRACE_ROOT / row["search_trace"]["path"]).read_bytes(),
            authority=authority,
            limits=limits,
            accepted_delta_limit=16,
        )
        verified += 1
        print(
            json.dumps(
                {"instance_id": row["instance_id"], "verified": verified, "total": len(traces)},
                sort_keys=True,
            ),
            flush=True,
        )
    if verified != 90:
        raise ValueError(f"expected 90 BFS teacher traces, verified {verified}")
    print(
        json.dumps(
            {
                "context_pairs_byte_identical": True,
                "model_input_construction_byte_identical": True,
                "trace_count": verified,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
