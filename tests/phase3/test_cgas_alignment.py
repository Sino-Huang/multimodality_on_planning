from __future__ import annotations

import json
import subprocess
import sys
from io import BytesIO
from pathlib import Path
from typing import Callable

from PIL import Image

from scripts.phase3.cgas_provenance import build_corpus, canonical_composition
from scripts.phase3.cgas_serialization import digest
from scripts.phase3.pddl import parse_task
from scripts.phase3.planimation_pairing_rendering import _write_problem_state


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BLOCKSWORLD_FIXTURE = REPOSITORY_ROOT / "tests/fixtures/planning/blocksworld_nontrivial.json"


def test_alignment_cli_emits_one_replay_proven_pre_action_image_for_each_source_transition(
    tmp_path: Path,
) -> None:
    # Given: accepted canonical P0 source transitions and Planimation-derived render inputs.
    source_root = _build_cgas_source(tmp_path)
    render_manifest = _write_render_manifest(source_root, tmp_path / "renders")
    output_root = tmp_path / "alignment"

    # When: the alignment CLI builds a bounded fixture corpus.
    result = _run_alignment("--source-root", str(source_root), "--render-manifest", str(render_manifest), "--output-root", str(output_root))

    # Then: every source transition has exactly one pre-action image with complete proof fields.
    assert result.returncode == 0, result.stderr
    source_rows = _source_rows(source_root)
    alignment_rows = _alignment_rows(output_root)
    assert len(alignment_rows) == len(source_rows)
    assert {row["source_transition_id"] for row in alignment_rows} == {
        str(row["record_id"]) for row in source_rows
    }
    assert all(row["vision_status"] == "vision_available_step_aligned" for row in alignment_rows)
    assert all(
        {
            "source_transition_id",
            "state_before_hash",
            "action",
            "png_path",
            "png_sha256",
            "vfg_action_index",
            "source_trace_sha256",
            "render_trace_sha256",
            "mapping_rationale",
        }
        <= row.keys()
        for row in alignment_rows
    )

    verification = _run_alignment("--verify", "--source-root", str(source_root), "--render-manifest", str(render_manifest), "--output-root", str(output_root))
    assert verification.returncode == 0, verification.stderr
    report = json.loads(verification.stdout)
    assert report["accepted_rows"] == len(source_rows)
    assert report["failures"] == {
        "action_order": 0,
        "duplicate": 0,
        "missing": 0,
        "state_linkage": 0,
        "unreadable": 0,
    }


def test_alignment_verify_rejects_swapped_frame_mutated_action_missing_initial_unreadable_and_stale_state(
    tmp_path: Path,
) -> None:
    # Given: independent valid bounded fixtures with two transition images per P0 planner.
    expected_reasons = {
        "swapped": "state_linkage_mismatch",
        "action": "frame_action_order_mismatch",
        "missing-initial": "missing_initial_frame",
        "unreadable": "unreadable_png",
        "stale-state": "state_linkage_mismatch",
    }
    mutations = {
        "swapped": _swap_frame_paths,
        "action": _mutate_vfg_action,
        "missing-initial": _remove_initial_frame,
        "unreadable": _corrupt_png,
        "stale-state": _mutate_state_before_hash,
    }

    # When: one render manifest at a time violates its required alignment proof.
    for name, mutate in mutations.items():
        scenario_root = tmp_path / name
        scenario_root.mkdir()
        source_root = _build_cgas_source(scenario_root)
        render_manifest = _write_render_manifest(source_root, scenario_root / "renders")
        output_root = scenario_root / "alignment"
        generated = _run_alignment("--source-root", str(source_root), "--render-manifest", str(render_manifest), "--output-root", str(output_root))
        assert generated.returncode == 0, generated.stderr
        candidate = _mutate_manifest(render_manifest, scenario_root, name, mutate)
        result = _run_alignment("--verify", "--source-root", str(source_root), "--render-manifest", str(candidate), "--output-root", str(output_root))

        # Then: each invalid mapping fails closed with its explicit reason and no accepted stale output.
        assert result.returncode == 1
        report = json.loads(result.stdout)
        assert report["accepted_rows"] == 0
        assert expected_reasons[name] in {item["reason"] for item in report["rejections"]}


def _build_cgas_source(tmp_path: Path) -> Path:
    fixture = json.loads(BLOCKSWORLD_FIXTURE.read_text(encoding="utf-8"))
    domain = tmp_path / "domain.pddl"
    problem = tmp_path / "problem.pddl"
    domain.write_text(fixture["domain_pddl"].replace("(domain blocksworld-4ops)", "(domain blocksworld)"), encoding="utf-8")
    problem.write_text(fixture["problem_pddl"].replace("(:domain blocksworld-4ops)", "(:domain blocksworld)"), encoding="utf-8")
    rows = [
        {"domain": "blocksworld", "instance_id": f"blocksworld-{split}-fixture-0000", "problem_path": str(problem), "domain_path": str(domain), "split": split, "structural_ood": False}
        for split in ("train", "dev", "test")
    ]
    rows.append({"domain": "blocksworld", "instance_id": "blocksworld-ood-heldout-0000", "problem_path": str(problem), "domain_path": str(domain), "split": "structural_ood", "structural_ood": True, "object_count": 3, "horizon": 2, "composition": canonical_composition(parse_task(domain, problem))})
    manifest = tmp_path / "instances.jsonl"
    manifest.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    output = tmp_path / "planning_cgas_v1"
    build_corpus(manifest, output)
    return output


def _write_render_manifest(source_root: Path, renders: Path) -> Path:
    renders.mkdir()
    source_problem = next(
        path
        for path in (source_root / "pddl").glob("*.pddl")
        if "(define (problem" in path.read_text(encoding="utf-8").lower()
    )
    rows: list[dict[str, object]] = []
    for source in _source_rows(source_root):
        transition_id = str(source["record_id"])
        planner = source["planner"]
        assert isinstance(planner, dict)
        planner_name = str(planner["algorithm"])
        instance_id = str(source["instance_id"])
        state = source["state_before"]
        assert isinstance(state, list) and all(isinstance(atom, str) for atom in state)
        step_index_value = source["step_index"]
        assert type(step_index_value) is int
        step_index = step_index_value
        source_trace = renders / f"{instance_id}-{planner_name}-source.vfg.json"
        actions = [str(row["selected_action"]) for row in _source_rows(source_root) if row["instance_id"] == instance_id and isinstance(row["planner"], dict) and row["planner"].get("algorithm") == planner_name]
        source_trace.write_text(json.dumps({"visualStages": [{"stageName": "Initial Stage"}, *({"stageName": item} for item in actions)]}), encoding="utf-8")
        derived_problem = renders / f"{transition_id}.pddl"
        _write_problem_state(source_problem, derived_problem, state, transition_id)
        frame = renders / f"{transition_id}.png"
        frame.write_bytes(_png((20 + step_index * 20, 96, 160, 255)))
        render_trace = renders / f"{transition_id}.vfg.json"
        render_trace.write_text(json.dumps({"visualStages": [{"stageName": "Initial Stage", "visualSprites": [{"name": "token", "minX": 0.2, "maxX": 0.6, "minY": 0.2, "maxY": 0.6}]}]}), encoding="utf-8")
        rows.append({"source_transition_id": transition_id, "state_before_hash": source["state_before_id"], "frame_path": str(frame), "png_sha256": digest(frame), "trace_path": str(render_trace), "vfg_sha256": digest(render_trace), "derived_problem_path": str(derived_problem), "source_trace_path": str(source_trace), "initial_frame_path": str(frame) if step_index == 0 else ""})
    manifest = renders / "state_render_manifest.jsonl"
    manifest.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return manifest


def _source_rows(source_root: Path) -> list[dict[str, object]]:
    return [json.loads(line) for split in ("train", "dev", "test") for line in (source_root / "source" / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()]


def _alignment_rows(output_root: Path) -> list[dict[str, object]]:
    return [json.loads(line) for split in ("train", "dev", "test") for line in (output_root / "alignment" / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()]


def _run_alignment(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "scripts.phase3.cgas_alignment", *arguments], cwd=REPOSITORY_ROOT, check=False, capture_output=True, text=True)


def _mutate_manifest(path: Path, tmp_path: Path, name: str, mutate: Callable[[list[dict[str, object]]], None]) -> Path:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    mutate(rows)
    candidate = tmp_path / f"{name}.jsonl"
    candidate.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return candidate


def _swap_frame_paths(rows: list[dict[str, object]]) -> None:
    rows[0]["frame_path"], rows[1]["frame_path"] = rows[1]["frame_path"], rows[0]["frame_path"]


def _mutate_vfg_action(rows: list[dict[str, object]]) -> None:
    path = Path(str(rows[0]["source_trace_path"]))
    path.write_text(json.dumps({"visualStages": [{"stageName": "Initial Stage"}, {"stageName": "(putdown a)"}]}), encoding="utf-8")


def _remove_initial_frame(rows: list[dict[str, object]]) -> None:
    rows[0]["initial_frame_path"] = ""


def _corrupt_png(rows: list[dict[str, object]]) -> None:
    Path(str(rows[0]["frame_path"])).write_bytes(b"not-a-png")


def _mutate_state_before_hash(rows: list[dict[str, object]]) -> None:
    rows[0]["state_before_hash"] = "0" * 64


def _png(color: tuple[int, int, int, int]) -> bytes:
    stream = BytesIO()
    image = Image.new("RGBA", (100, 100), (255, 255, 255, 255))
    for x in range(20, 60):
        for y in range(40, 80):
            image.putpixel((x, y), color)
    image.save(stream, format="PNG")
    return stream.getvalue()
