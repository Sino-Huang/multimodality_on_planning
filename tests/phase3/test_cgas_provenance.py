from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from examples.planning_benchmark_slice.generate_experts import generate_experts
from scripts.phase3.local_iw import run_iterated_width
from scripts.phase3.local_planner_types import LocalPlannerRequest
from scripts.phase3.pddl import GroundAction, PDDLTask, parse_task
from scripts.phase3.cgas_provenance import canonical_composition


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = REPOSITORY_ROOT / "tests/fixtures/planning/blocksworld_nontrivial.json"


def test_existing_benchmark_fixture_characterizes_bfs_and_iw_before_cgas_gate(tmp_path: Path) -> None:
    # Given: the checked-in deterministic Blocksworld fixture.
    generated = generate_experts(
        fixture_path=FIXTURE_PATH,
        algorithms=("bfs", "iterated_width"),
        output_dir=tmp_path / "benchmark",
    )

    # When: its established expert generators run before CGAS changes shared helpers.
    # Then: the known action sequence and width-one metadata remain stable.
    assert generated["algorithms"]["bfs"]["selected_actions"] == ["pickup(a)", "stack(a,b)"]
    assert generated["algorithms"]["iterated_width"]["selected_actions"] == [
        "pickup(a)",
        "stack(a,b)",
    ]


def test_local_width_one_iw_records_novelty_evidence_for_real_expansion_and_prune() -> None:
    # Given: a real local-IW state graph where the second queued state becomes non-novel.
    task = PDDLTask(
        domain_name="novelty",
        problem_name="prune",
        objects_by_type={},
        init=frozenset({("p",)}),
        goal=frozenset({("missing_goal",)}),
        actions=(),
        unsupported_features=(),
    )
    actions = (
        GroundAction("first", (), frozenset({("p",)}), frozenset({("q",), ("r",)}), frozenset({("p",)})),
        GroundAction("second", (), frozenset({("p",)}), frozenset({("r",)}), frozenset({("p",)})),
    )

    # When: the repository's local IW implementation runs at exactly width one.
    result = run_iterated_width(
        LocalPlannerRequest(
            "iw",
            task,
            actions,
            {"local_iw_width": 1, "local_iw_max_width": 1, "max_trace_steps": 10, "gbfs_max_depth": 10, "gbfs_max_expansions": 10, "max_plan_length": 10},
        )
    )

    # Then: both the accepted expansion and the later prune carry complete novelty evidence.
    events_value = result.trace["events"]
    assert isinstance(events_value, list)
    events = [event for event in events_value if isinstance(event, dict)]
    decisions: set[str] = set()
    for event in events:
        decision = event["decision"]
        assert isinstance(decision, str)
        decisions.add(decision)
    assert decisions == {"expand", "prune"}
    assert all(
        {"novelty_table_before", "novelty_table_after", "novel_item", "width_decision"}
        <= event.keys()
        for event in events
    )


def test_cgas_cli_publishes_canonical_bfs_and_exact_width_one_iw_for_every_split(
    tmp_path: Path,
) -> None:
    # Given: three split-preserving Blocksworld instances and a declared held-out partition.
    source_manifest = _write_fixture_manifest(tmp_path)
    output_root = tmp_path / "planning_cgas_v1"

    # When: the P0 source generator creates a candidate corpus.
    result = _run_cgas("--source-manifest", str(source_manifest), "--output-root", str(output_root))

    # Then: publication has replay-valid canonical BFS and real width-one IW rows in every split.
    assert result.returncode == 0, result.stderr
    manifest: dict[str, Any] = json.loads((output_root / "manifest.json").read_text(encoding="utf-8"))
    assert (output_root / "approved.json").is_file()
    assert (output_root / "source_manifest.jsonl").is_file()
    assert manifest["partitions"]["structural_ood"]["ids"] == ["blocksworld-ood-heldout-0000"]

    for split in ("train", "dev", "test"):
        rows = _read_jsonl(output_root / "source" / f"{split}.jsonl")
        assert {row["planner"]["algorithm"] for row in rows} == {
            "breadth_first_search",
            "iterated_width",
        }
        bfs_rows = [row for row in rows if row["planner"]["algorithm"] == "breadth_first_search"]
        iw_rows = [row for row in rows if row["planner"]["algorithm"] == "iterated_width"]
        assert bfs_rows[0]["planner"]["implementation"] == "scripts.phase3.cgas_bfs.run_fifo_bfs"
        assert bfs_rows[0]["planner"]["action_tie_break"] == "legal_actions_sorted_by_canonical_action_string"
        assert bfs_rows[0]["planner_trace"]["expansions"][0]["actions_considered"] == [
            "(pickup a)",
            "(pickup b)",
            "(pickup c)",
        ]
        assert bfs_rows[0]["planner_trace"]["expansions"][0]["frontier_before"] == [
            bfs_rows[0]["state_before_id"]
        ]
        assert iw_rows[0]["planner"]["width"] == 1
        assert "plan_recovery" not in iw_rows[0]["planner_trace"]
        assert all(
            {"novelty_table_before", "novelty_table_after", "novel_item", "width_decision"}
            <= event.keys()
            for event in iw_rows[0]["planner_trace"]["events"]
        )


def test_cgas_verify_rejects_gbfs_identity_and_missing_iw_novelty_without_accepting_candidate(
    tmp_path: Path,
) -> None:
    # Given: a previously valid generated candidate corpus.
    source_manifest = _write_fixture_manifest(tmp_path)
    output_root = tmp_path / "planning_cgas_v1"
    generated = _run_cgas("--source-manifest", str(source_manifest), "--output-root", str(output_root))
    assert generated.returncode == 0, generated.stderr

    # When: a copied candidate falsely claims GBFS as BFS.
    gbfs_candidate = _copy_corpus(output_root, tmp_path / "gbfs_candidate")
    gbfs_rows = _read_jsonl(gbfs_candidate / "source" / "train.jsonl")
    bfs_row = next(row for row in gbfs_rows if row["planner"]["algorithm"] == "breadth_first_search")
    bfs_row["planner"]["implementation"] = "scripts.phase3.gbfs.run_gbfs"
    _write_jsonl(gbfs_candidate / "source" / "train.jsonl", gbfs_rows)
    gbfs_result = _run_cgas("--verify", "--output-root", str(gbfs_candidate))

    # Then: verification names the stable record and accepts no candidate rows.
    assert gbfs_result.returncode != 0
    gbfs_report = json.loads(gbfs_result.stdout)
    assert gbfs_report["accepted_rows"] == 0
    assert any(item["reason"] == "recomputed_row_mismatch" for item in gbfs_report["rejections"])

    # When: a copied candidate omits required IW novelty evidence.
    iw_candidate = _copy_corpus(output_root, tmp_path / "iw_candidate")
    iw_rows = _read_jsonl(iw_candidate / "source" / "train.jsonl")
    iw_row = next(row for row in iw_rows if row["planner"]["algorithm"] == "iterated_width")
    del iw_row["planner_trace"]["events"][0]["novel_item"]
    _write_jsonl(iw_candidate / "source" / "train.jsonl", iw_rows)
    iw_result = _run_cgas("--verify", "--output-root", str(iw_candidate))

    # Then: the missing field is rejected exactly and no candidate is accepted.
    assert iw_result.returncode != 0
    iw_report = json.loads(iw_result.stdout)
    assert iw_report["accepted_rows"] == 0
    assert any(item["reason"] == "recomputed_row_mismatch" for item in iw_report["rejections"])


def _write_fixture_manifest(root: Path) -> Path:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    domain_path = root / "domain.pddl"
    problem_path = root / "problem.pddl"
    domain_path.write_text(fixture["domain_pddl"].replace("(domain blocksworld-4ops)", "(domain blocksworld)"), encoding="utf-8")
    problem_path.write_text(fixture["problem_pddl"].replace("(:domain blocksworld-4ops)", "(:domain blocksworld)"), encoding="utf-8")
    rows = [
        {
            "domain": "blocksworld",
            "instance_id": f"blocksworld-{split}-fixture-0000",
            "problem_path": str(problem_path),
            "domain_path": str(domain_path),
            "split": split,
            "structural_ood": False,
        }
        for split in ("train", "dev", "test")
    ]
    rows.append(
        {
            "domain": "blocksworld",
            "instance_id": "blocksworld-ood-heldout-0000",
            "problem_path": str(problem_path),
            "domain_path": str(domain_path),
            "split": "structural_ood",
            "structural_ood": True,
            "object_count": 3,
            "horizon": 2,
            "composition": canonical_composition(parse_task(domain_path, problem_path)),
        }
    )
    manifest_path = root / "instances.jsonl"
    _write_jsonl(manifest_path, rows)
    return manifest_path


def _copy_corpus(source: Path, destination: Path) -> Path:
    import shutil

    shutil.copytree(source, destination)
    return destination


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _run_cgas(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "scripts.phase3.cgas_provenance", *arguments],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
