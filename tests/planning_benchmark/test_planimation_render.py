from __future__ import annotations

import json
import types
from pathlib import Path

import pytest

from examples.planning_benchmark_slice.planimation_render import (
    PlanimationRenderError,
    PlanimationRenderRequest,
    produce_planimation_render,
)


def _request(
    tmp_path: Path,
    *,
    base_url: str = "http://127.0.0.1:18082",
    supplied_plan: tuple[str, ...] | None = ("(pickup b1)", "(stack b1 b2)"),
    solver_url: str | None = None,
) -> PlanimationRenderRequest:
    domain_path = tmp_path / "domain.pddl"
    problem_path = tmp_path / "problem.pddl"
    profile_path = tmp_path / "profile.pddl"
    domain_path.write_text("(define (domain blocks))", encoding="utf-8")
    problem_path.write_text("(define (problem p1) (:domain blocks))", encoding="utf-8")
    profile_path.write_text("(define (domain blocks-animation))", encoding="utf-8")
    return PlanimationRenderRequest(
        base_url=base_url,
        domain_path=domain_path,
        problem_path=problem_path,
        animation_profile_path=profile_path,
        supplied_plan=supplied_plan,
        output_dir=tmp_path / "render",
        timeout_seconds=30,
        solver_url=solver_url,
    )


def test_production_uses_one_local_supplied_plan_request_and_writes_render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path)
    posted: list[dict[str, object]] = []
    vfg_payload = {
        "imageTable": {"m_keys": [], "m_values": []},
        "visualStages": [{"visualSprites": []} for _ in range(3)],
    }

    def post(url: str, **arguments: object) -> object:
        posted.append({"url": url, **arguments})
        return types.SimpleNamespace(
            status_code=200,
            text=json.dumps(vfg_payload),
            content=json.dumps(vfg_payload).encode("utf-8"),
            json=lambda: vfg_payload,
        )

    monkeypatch.setattr("scripts.planimation_phase1_client.requests.post", post)
    result = produce_planimation_render(request)

    assert len(posted) == 1
    assert posted[0]["url"] == "http://127.0.0.1:18082/upload/pddl"
    assert posted[0]["allow_redirects"] is False
    files = posted[0]["files"]
    assert isinstance(files, dict)
    assert list(files) == ["domain", "problem", "animation", "plan"]
    assert files["plan"] == (None, "(pickup b1)\n(stack b1 b2)")
    assert result.used_endpoint == "http://127.0.0.1:18082/upload/pddl"
    assert result.trace_path.is_file()
    assert len(result.frame_paths) == 3
    assert all(path.is_file() for path in result.frame_paths)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"base_url": "https://planimation.planning.domains"}, "Planimation endpoint must be localhost"),
        ({"supplied_plan": None}, "supplied plan is required"),
        ({"supplied_plan": ()}, "supplied plan is required"),
        ({"supplied_plan": ("pickup b1",)}, "supplied plan actions must be parenthesized"),
        ({"solver_url": "http://127.0.0.1:18082/forbidden-solver"}, "planning fallback is prohibited"),
    ],
)
def test_production_hard_fails_unsafe_requests_before_http(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    overrides: dict[str, object],
    message: str,
) -> None:
    posts: list[object] = []
    request = _request(tmp_path, **overrides)  # type: ignore[arg-type]
    monkeypatch.setattr(
        "scripts.planimation_phase1_client.requests.post",
        lambda *args, **kwargs: posts.append((args, kwargs)),
    )

    with pytest.raises(PlanimationRenderError, match=message):
        produce_planimation_render(request)

    assert posts == []
    assert not request.output_dir.exists()
