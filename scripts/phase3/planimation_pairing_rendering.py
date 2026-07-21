from __future__ import annotations
import json
import shutil
import time
from dataclasses import asdict
from pathlib import Path
from typing import Iterable
from PIL import Image, UnidentifiedImageError
from .io_utils import file_sha256, relpath, repo_root, stable_hash, write_json
from .pddl import PDDLError, canonical_atom, parse_task
from .render_semantics import validate_render_artifacts
from .traversal_state_types import JSONValue
from .planimation_pairing_contracts import RenderConfig, StateRenderer
SCHEMA_VERSION = "phase3_planimation_vlm_v1"

__all__ = ("_render_one_state", "_assert_repo_output_root", "_assert_source_output_disjoint")

from .planimation_pairing_source import _repo_path
def render_state_with_planimation(domain_path: Path, problem_path: Path, profile_path: Path, cache_dir: Path, config: RenderConfig) -> dict[str, JSONValue]:
    """Upload a derived problem, then locally render only its initial VFG stage."""
    from scripts.planimation_phase1 import post_pddl_for_vfg, render_vfg_to_local_png_frames

    pddl_urls = [f"{config.base_url.rstrip('/')}/upload/pddl", f"{config.base_url.rstrip('/')}/upload/(?P<filename>[^/]+)$", f"{config.base_url.rstrip('/')}/upload/"]
    errors: list[str] = []
    for attempt in range(1, config.max_attempts + 1):
        try:
            vfg_bytes, used_url = post_pddl_for_vfg(domain_path, problem_path, profile_path, pddl_urls, config.timeout_seconds)
            trace_path = cache_dir / "trace.vfg.json"
            trace_path.write_bytes(vfg_bytes)
            frames_dir = cache_dir / "frames"
            if frames_dir.exists():
                shutil.rmtree(frames_dir)
            frame_count = render_vfg_to_local_png_frames(vfg_bytes, frames_dir, 0, 0)
            frame_path = frames_dir / "frame_000.png"
            if frame_count != 1 or not _valid_png(frame_path):
                raise RuntimeError("Planimation initial-stage render did not produce one readable PNG")
            return {"status": "success", "frame_path": relpath(frame_path), "trace_path": relpath(trace_path), "used_pddl_url": used_url, "attempts": attempt}
        except (OSError, RuntimeError, ValueError, UnidentifiedImageError) as exc:
            errors.append(str(exc))
            if attempt < config.max_attempts and config.request_delay_seconds:
                time.sleep(config.request_delay_seconds)
    return {"status": "failed", "message": " | ".join(errors), "attempts": config.max_attempts}

def _render_one_state(pair: dict[str, JSONValue], transition: dict[str, JSONValue], output_root: Path, renderer: StateRenderer, config: RenderConfig) -> dict[str, JSONValue]:
    state_atoms = sorted(str(atom) for atom in transition["state_before"])
    profile_path = _profile_path(pair)
    identity = _cache_identity(pair, state_atoms, profile_path, renderer, config)
    state_hash = stable_hash(state_atoms)[:32]
    cache_dir = output_root / "state_cache" / str(pair["domain"]) / str(pair["instance_id"]) / identity["cache_key"]
    problem_path = cache_dir / "problem.pddl"
    frame_path = cache_dir / "frames" / "frame_000.png"
    row = {"schema_version": SCHEMA_VERSION, "pair_id": pair["pair_id"], "domain": pair["domain"], "instance_id": pair["instance_id"], "split": pair["split"], "planner": pair["planner"], "step_index": transition["step_index"], "state_hash": state_hash, "transition": transition, "cache_dir": relpath(cache_dir), **identity}
    cached = _validated_cache(cache_dir, problem_path, frame_path, state_atoms, identity)
    if cached is not None:
        row.update({"status": "success", "cache_hit": True, "frame_path": relpath(frame_path), "derived_problem_path": relpath(problem_path), "input_hash": cached["derived_problem_sha256"], "trace_path": cached["trace_path"], "vfg_sha256": cached["vfg_sha256"], "png_sha256": cached["png_sha256"], "png_dimensions": cached["png_dimensions"], "semantic_image_qa": cached["semantic_image_qa"], "semantic_image_metrics": cached["semantic_image_metrics"]})
        return row
    cache_dir.mkdir(parents=True, exist_ok=True)
    try:
        source_problem = _repo_path(pair["problem_path"])
        _write_problem_state(source_problem, problem_path, state_atoms, f"{pair['instance_id']}-{state_hash}")
        task = parse_task(_repo_path(pair["domain_path"]), problem_path)
        if sorted(canonical_atom(atom) for atom in task.init) != state_atoms:
            raise ValueError("derived PDDL init does not equal replay state")
        result = renderer(_repo_path(pair["domain_path"]), problem_path, profile_path, cache_dir, config)
        row.update(result)
        if result.get("status") == "success":
            rendered = _repo_path(str(result["frame_path"]))
            trace_path = _repo_path(str(result["trace_path"]))
            receipt = validate_render_artifacts(trace_path, rendered)
            if receipt.status != "success":
                raise ValueError(f"semantic_image_invalid: {receipt.reason}")
            vfg_sha256 = _valid_vfg(trace_path)
            row.update({"cache_hit": False, "derived_problem_path": relpath(problem_path), "input_hash": file_sha256(problem_path), "vfg_sha256": vfg_sha256, "png_sha256": file_sha256(rendered), "png_dimensions": list(receipt.png_dimensions), "semantic_image_qa": receipt.reason, "semantic_image_metrics": receipt.to_record()})
        write_json(
            cache_dir / "result.json",
            {
                "schema_version": SCHEMA_VERSION,
                "status": row["status"],
                "state_hash": state_hash,
                **identity,
                "derived_problem_sha256": row.get("input_hash", ""),
                "derived_problem_path": row.get("derived_problem_path", relpath(problem_path)),
                "frame_path": row.get("frame_path", ""),
                "trace_path": row.get("trace_path", ""),
                "vfg_sha256": row.get("vfg_sha256", ""),
                "png_sha256": row.get("png_sha256", ""),
                "png_dimensions": row.get("png_dimensions", []),
                "semantic_image_qa": row.get("semantic_image_qa", ""),
                "semantic_image_metrics": row.get("semantic_image_metrics", {}),
                "renderer": {key: value for key, value in result.items() if key not in {"frame_path", "trace_path"}},
            },
        )
        return row
    except (OSError, PDDLError, RuntimeError, ValueError, KeyError, UnidentifiedImageError) as exc:
        row.update({"status": "failed", "cache_hit": False, "message": str(exc), "derived_problem_path": relpath(problem_path)})
        write_json(cache_dir / "result.json", {"schema_version": SCHEMA_VERSION, "status": "failed", "state_hash": state_hash, "message": str(exc), "derived_problem_path": row["derived_problem_path"]})
        return row

def _write_problem_state(source_path: Path, destination: Path, state_atoms: list[str], problem_name: str) -> None:
    source = source_path.read_text(encoding="utf-8")
    start = source.lower().find("(:init")
    if start < 0:
        raise ValueError(f"PDDL problem has no :init block: {source_path}")
    end = _balanced_end(source, start)
    init = "(:init\n" + "\n".join(f"  {atom}" for atom in state_atoms) + "\n)"
    rewritten = source[:start] + init + source[end:]
    marker = "(define (problem "
    lower = rewritten.lower()
    name_start = lower.find(marker)
    if name_start >= 0:
        token_start = name_start + len(marker)
        token_end = token_start
        while token_end < len(rewritten) and not rewritten[token_end].isspace() and rewritten[token_end] != ")":
            token_end += 1
        rewritten = rewritten[:token_start] + problem_name.lower() + rewritten[token_end:]
    destination.write_text(rewritten, encoding="utf-8")

def _balanced_end(text: str, start: int) -> int:
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            depth -= 1
            if depth == 0:
                return index + 1
    raise ValueError("unbalanced PDDL block")

def _profile_path(pair: dict[str, JSONValue]) -> Path:
    from src.data_collect.config import load_curriculum_config

    domain = str(pair["domain"])
    for configured_domain in load_curriculum_config().domains:
        if configured_domain.domain_id == domain:
            profile = configured_domain.render_profile_path.resolve()
            if profile.is_relative_to(repo_root()) and profile.exists():
                return profile
            raise FileNotFoundError(f"configured Planimation profile is unavailable for {domain}")
    raise FileNotFoundError(f"missing configured Planimation profile for {domain}")

def _valid_png(path: Path) -> bool:
    return _png_metadata(path) is not None

def _png_metadata(path: Path) -> tuple[tuple[int, int], str] | None:
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            alpha = image.convert("RGBA").getchannel("A")
            if image.width <= 0 or image.height <= 0 or alpha.getbbox() is None:
                return None
            return (image.width, image.height), "nontransparent_pixels"
    except (OSError, UnidentifiedImageError):
        return None

def _cache_identity(pair: dict[str, JSONValue], state_atoms: list[str], profile_path: Path, renderer: StateRenderer, config: RenderConfig) -> dict[str, JSONValue]:
    profile_relative = relpath(profile_path)
    identity = {
        "schema_version": SCHEMA_VERSION,
        "domain_path": str(pair["domain_path"]),
        "domain_sha256": file_sha256(_repo_path(str(pair["domain_path"]))),
        "problem_sha256": file_sha256(_repo_path(str(pair["problem_path"]))),
        "profile_path": profile_relative,
        "profile_sha256": file_sha256(profile_path),
        "state_sha256": stable_hash(state_atoms),
        "renderer_id": f"{getattr(renderer, '__module__', '')}.{getattr(renderer, '__qualname__', repr(renderer))}",
        "renderer_config_sha256": stable_hash(asdict(config)),
    }
    return {**identity, "cache_key": stable_hash(identity)[:32]}

def _valid_vfg(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("visualStages"), list):
        raise ValueError("renderer VFG does not contain visualStages")
    return file_sha256(path)

def _validated_cache(cache_dir: Path, problem_path: Path, frame_path: Path, state_atoms: list[str], identity: dict[str, JSONValue]) -> dict[str, JSONValue] | None:
    result_path = cache_dir / "result.json"
    try:
        metadata = json.loads(result_path.read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            return None
        trace_path = _repo_path(str(metadata["trace_path"]))
        receipt = validate_render_artifacts(trace_path, frame_path)
        if (
            metadata.get("status") != "success"
            or any(metadata.get(key) != value for key, value in identity.items())
            or metadata.get("derived_problem_sha256") != file_sha256(problem_path)
            or receipt.status != "success"
            or metadata.get("png_sha256") != file_sha256(frame_path)
            or metadata.get("png_dimensions") != list(receipt.png_dimensions)
            or metadata.get("semantic_image_qa") != receipt.reason
            or metadata.get("semantic_image_metrics") != receipt.to_record()
        ):
            return None
        if metadata.get("vfg_sha256") != _valid_vfg(trace_path):
            return None
        if sorted(canonical_atom(atom) for atom in parse_task(_repo_path(str(metadata["domain_path"])), problem_path).init) != state_atoms:
            return None
        return metadata
    except (FileNotFoundError, KeyError, OSError, TypeError, json.JSONDecodeError, ValueError):
        return None

def _assert_repo_output_root(output_root: Path) -> None:
    root = repo_root().resolve()
    output = output_root.resolve()
    if not output.is_relative_to(root / "outputs") and not output.is_relative_to(root / "tmp"):
        raise ValueError(f"output_root must be under repo outputs/ or tmp/: {output_root}")

def _assert_source_output_disjoint(dataset_roots: Iterable[Path], output_root: Path) -> None:
    output = output_root.resolve()
    if any(output.is_relative_to(Path(dataset_root).resolve()) for dataset_root in dataset_roots):
        raise ValueError("output_root must not equal or be nested under a source root")
