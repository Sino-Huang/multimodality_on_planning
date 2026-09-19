#!/usr/bin/env python
"""Compute the v2 second-backbone admission artifact (ticket #123, CPU-only).

Protocol expanded-second-backbone-v2 reduces the branch to the frozen L1
key-cell panel (72 model episodes) under the amended 52.11 GPU-h cap after the
prospective recovery-reserve transfer. This script reuses the frozen
``decide_admission`` formula from ``expanded_second_backbone`` together with:

- the v1 qualification and probe artifacts (pinned by sha256 in the v2
  protocol's ``prior_evidence_reuse`` block; they contain no model outcomes),
- the live ledger branch spend (ledger is read-only here),

and writes ``outputs/expanded-study/v1/second-backbone-v2/admission.json``.
No v1 artifact and no ledger entry is modified; the v1 VALID_STOP evidence
under ``outputs/expanded-study/v1/second-backbone`` is retained untouched.

The CLI ``admit`` stage cannot be used for v2: ``validate_protocol`` is frozen
to the v1 protocol identity (protocol_id, output_root, 40 GPU-h cap, L0
episode counts) and to the pre-transfer ledger allocations, so the v2
protocol is admitted through this explicit recompute instead.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from examples.planning_benchmark_slice import expanded_second_backbone as branch
from examples.planning_benchmark_slice.expanded_scheduler import ROOT, read


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def compute_admission(protocol_path: Path) -> dict:
    protocol = read(protocol_path)
    if protocol.get("protocol_id") != "expanded-second-backbone-v2":
        raise ValueError("second-backbone v2 admission requires the v2 protocol")
    reuse = protocol.get("prior_evidence_reuse", {})

    qualification_path = ROOT / reuse["qualification"]["path"]
    probe_path = ROOT / reuse["probe"]["path"]
    if _file_sha256(qualification_path) != reuse["qualification"]["sha256"]:
        raise ValueError("second-backbone v1 qualification artifact differs from the pinned sha256")
    if _file_sha256(probe_path) != reuse["probe"]["sha256"]:
        raise ValueError("second-backbone v1 probe artifact differs from the pinned sha256")
    qualification = read(qualification_path)
    probe = read(probe_path)
    if qualification.get("outcome") != "PASS" or not qualification.get("complete"):
        raise RuntimeError("second-backbone v2 admission requires a complete PASS v1 qualification")
    if probe.get("outcome") != "PASS":
        raise RuntimeError("second-backbone v2 admission requires a PASS v1 probe")

    ledger = read(ROOT / branch.LEDGER_PATH)
    spent = branch._branch_spent(ledger)
    cap = protocol["budget"]["gpu_hours"]
    if cap != ledger["allocations_gpu_hours"]["second_backbone"]:
        raise ValueError("second-backbone v2 protocol cap differs from the ledger allocation")

    _panel, panel_tasks = branch.load_panel(ROOT, protocol)
    costs = [task["row"]["reference_costs"] for task in panel_tasks]
    task_ids = [task["row"]["task_id"] for task in panel_tasks]

    result = branch.decide_admission(
        protocol,
        qualification,
        probe,
        branch_spent_gpu_hours=spent,
        panel_task_costs=costs,
        panel_task_ids=task_ids,
    )

    scope = result.get("authorized_scope") or {}
    frozen_ids = list(protocol["evaluation"]["key_cell_selection"]["task_ids"])
    if scope.get("task_ids") != frozen_ids:
        raise ValueError("second-backbone v2 frozen key-cell membership differs from decide_admission L1 scope")
    if protocol["evaluation"]["key_cell_selection"]["task_ids_sha256"] != branch._json_sha256(frozen_ids):
        raise ValueError("second-backbone v2 key-cell membership sha256 differs from the canonical task_ids")
    if scope.get("model_episodes") != protocol["evaluation"]["model_episodes"]:
        raise ValueError("second-backbone v2 admission scope episode count differs from the protocol")

    admission_path = ROOT / protocol["output_root"] / "admission.json"
    branch.write_json(admission_path, result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument(
        "--protocol",
        type=Path,
        default=ROOT / "configs/experiments/expanded-study/second-backbone-protocol-v2.json",
    )
    args = parser.parse_args(argv)
    result = compute_admission(args.protocol)
    print(
        json.dumps(
            {
                "outcome": result["outcome"],
                "decision": result["decision"],
                "branch_cap_gpu_hours": result["branch_cap_gpu_hours"],
                "branch_spent_gpu_hours": result["branch_spent_gpu_hours"],
                "branch_remainder_gpu_hours": result["branch_remainder_gpu_hours"],
                "required_gpu_hours_including_spent": result["arithmetic"][result["decision"]][
                    "required_gpu_hours_including_spent"
                ],
                "authorized_tasks": len(result["authorized_scope"]["task_ids"]),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
