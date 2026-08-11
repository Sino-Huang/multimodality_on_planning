from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from pathlib import Path

import pytest

from scripts.phase3.render_semantics import (
    _decode_png,
    _parse_stage_zero_sprites,
    _sprite_has_coverage,
    validate_render_artifacts,
)

ROOT = Path(__file__).parents[2]
PROOF_HARNESS = ROOT / ".claude/evidence/cgas-phase3-pilot-rendering/local_planimation_backend_proof.py"
FAILED_FERRY_CANARY = ROOT / (
    ".claude/evidence/planimation-pilot-contract-and-render-recovery/"
    "task-5-planimation-pilot-contract-and-render-recovery/ferry-failed-attempt"
)
FAILED_ELEVATORS_CANARY = ROOT / (
    ".claude/evidence/planimation-pilot-contract-and-render-recovery/"
    "task-5-planimation-pilot-contract-and-render-recovery/elevators-failed-attempt"
)
IMAGE_SECTION_SHA256 = {
    "data/pddl_instances/gripper/gripper_AP.pddl": "9acbc33f9b0719cd4bb2e1f4e469a12d834e823719b180eab95165d0ca53216c",
    "data/pddl_instances/ferry/ap.pddl": "871681463f96a3bd8af434bccbf54b2d7f8cbf0bf4cf14e6117fbfddcdaea355",
    "data/pddl_instances/elevators/elevators_ap.pddl": (
        "98eabfd7f6a20104385a146aee971c6331c00514a81254280fc7a1c1f8f39a19"
    ),
    "data/pddl_instances/logistics/logistics_ap.pddl": (
        "4d7044a096d5c3203214644fc3869e41c99cc1f417614cccc22f9e6873c29fb5"
    ),
}


def _normalized_profile(relative_path: str) -> str:
    source = (ROOT / relative_path).read_text(encoding="utf-8")
    before_images, marker, _ = source.partition("(:image")
    assert marker == "(:image"
    without_comments = re.sub(r";[^\n]*", "", before_images)
    return re.sub(r"\s+", " ", without_comments).strip().lower()


def _proof_harness():
    """Load the local-only proof harness module (established importlib pattern)."""
    spec = importlib.util.spec_from_file_location(
        "_local_planimation_backend_proof_test", PROOF_HARNESS
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _image_section_sha256(relative_path: str) -> str:
    source = (ROOT / relative_path).read_bytes()
    _, marker, image_section = source.partition(b"(:image")
    assert marker == b"(:image"
    return hashlib.sha256(image_section).hexdigest()


def _form(profile: str, marker: str) -> str:
    start = profile.index(marker)
    depth = 0
    for index, character in enumerate(profile[start:], start=start):
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return profile[start : index + 1]
    raise AssertionError(f"unbalanced PDDL form for {marker}")


def test_gripper_visual_uses_nonzero_geometry() -> None:
    # Given: the Gripper animation profile visual declaration.
    profile = _normalized_profile("data/pddl_instances/gripper/gripper_AP.pddl")

    # When: the gripper visual contract is inspected without comments or image data.
    gripper = _form(profile, "(:visual gripper")

    # Then: the sprite has the approved nonzero dimensions.
    assert "(width 30)" in gripper
    assert "(height 60)" in gripper
    assert "(width 0)" not in gripper
    assert "(height 0)" not in gripper


def test_ferry_car_geometry_differs_from_location() -> None:
    # Given: the Ferry location and car visual declarations.
    profile = _normalized_profile("data/pddl_instances/ferry/ap.pddl")

    # When: their dimensions are inspected without comments or image data.
    location = _form(profile, "(:visual location")
    car = _form(profile, "(:visual car")

    # Then: a car cannot share a location's 150x150 bounds.
    assert "(width 150)" in location
    assert "(height 150)" in location
    assert "(width 100)" in car
    assert "(height 70)" in car
    assert "(width 150)" not in car
    assert "(height 150)" not in car


def test_ferry_shared_location_cars_use_distinct_vertical_lanes(tmp_path: Path) -> None:
    # Given: the stage-zero c0/c1 bounds recorded for full-pilot state 33b9c9648b4b132c94467949b8427b34.
    trace_path = tmp_path / "ferry-shared-location.vfg.json"
    trace_path.write_text(
        json.dumps(
            {
                "visualStages": [
                    {
                        "visualSprites": [
                            {"name": "c0", "minX": 0.679, "maxX": 0.868, "minY": 0.038, "maxY": 0.17},
                            {"name": "c1", "minX": 0.679, "maxX": 0.868, "minY": 0.038, "maxY": 0.17},
                        ]
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    # When: the unchanged validator parses the recorded coincident layout.
    receipt = validate_render_artifacts(trace_path, tmp_path / "unused.png")
    profile = _normalized_profile("data/pddl_instances/ferry/ap.pddl")
    location = _form(profile, "(:predicate location")
    at = _form(profile, "(:predicate at :parameters")

    # Then: shared-location cars must be distributed within their location rather than share its x coordinate.
    assert receipt.reason == "coincident_sprite_bounds"
    assert "(equal (?l y) 0)" in location
    assert "(assign (?c x y) (function distribute_within_objects_vertical (objects ?c ?l)" in at
    assert "(equal (?c x) (?l x))" not in at


def test_elevators_served_passengers_use_distinct_global_origin_lanes() -> None:
    # Given: the real failed VFG where two served-state passengers coincide.
    trace_path = FAILED_ELEVATORS_CANARY / "trace.vfg.json"
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    sprites = payload["visualStages"][0]["visualSprites"]
    by_name = {sprite["name"]: sprite for sprite in sprites}
    p0_bounds = tuple(by_name["p0"][field] for field in ("minX", "maxX", "minY", "maxY"))
    p1_bounds = tuple(by_name["p1"][field] for field in ("minX", "maxX", "minY", "maxY"))
    receipt = validate_render_artifacts(trace_path, FAILED_ELEVATORS_CANARY / "frame_000.png")

    # When: the stable origin and served positioning contracts are inspected.
    profile = _normalized_profile("data/pddl_instances/elevators/elevators_ap.pddl")
    origin = _form(profile, "(:predicate origin")
    served = _form(profile, "(:predicate served")

    # Then: global origin lanes prevent the recorded same-floor passenger collision.
    assert p0_bounds == p1_bounds
    assert receipt.reason == "coincident_sprite_bounds"
    assert "(assign (?p x) (function distributex (objects ?p)))" in origin
    assert "distribute_within_objects_horizontal" not in origin
    assert "(objects ?p ?f)" not in origin
    assert "(assign (?person x)" not in served


def test_elevators_served_preserves_horizontal_position() -> None:
    # Given: the Elevators passenger positioning predicates.
    profile = _normalized_profile("data/pddl_instances/elevators/elevators_ap.pddl")

    # When: served, origin, and boarded contracts are inspected.
    served = _form(profile, "(:predicate served")
    origin = _form(profile, "(:predicate origin")
    boarded = _form(profile, "(:predicate boarded")

    # Then: served retains appearance and destination changes without redistributing x.
    assert "(equal (?person prefabimage) img-happy)" in served
    assert "(equal (?person color) yellow)" in served
    assert "(equal (?person y) (?person destiny))" in served
    assert "(assign (?person x)" not in served
    assert "distributex" not in served
    assert "(assign (?p x) (function distributex (objects ?p)))" in origin
    assert "(assign (?person x) (function distribute_within_objects_horizontal" in boarded


def test_logistics_visuals_use_current_object_selectors() -> None:
    # Given: the Logistics visual declarations.
    profile = _normalized_profile("data/pddl_instances/logistics/logistics_ap.pddl")

    # When: current domain type selectors are inspected without comments or image data.
    package = _form(profile, "(:visual package")
    truck = _form(profile, "(:visual truck")
    plane = _form(profile, "(:visual plane")
    hub = _form(profile, "(:visual hub")
    city = _form(profile, "(:visual city")

    # Then: every visual selects its current typed object set.
    assert ":type predefine" in package
    assert ":objects %p" in package
    assert ":type default" not in package
    assert ":objects %t" in truck
    assert ":objects %truck" not in truck
    assert ":objects %a" in plane
    assert ":objects %plane" not in plane
    assert ":objects %l" in hub
    assert "city6-1" not in hub
    assert ":objects %c" in city
    assert "city6 city5" not in city


def test_ferry_on_car_stays_in_location_coverage_lane() -> None:
    # Given: the real failed Ferry canary with a six-sprite expected-object set.
    sprites = _parse_stage_zero_sprites(FAILED_FERRY_CANARY / "trace.vfg.json")
    decoded = _decode_png(FAILED_FERRY_CANARY / "frame_000.png")
    assert isinstance(sprites, tuple)
    assert isinstance(decoded, tuple)
    image, _ = decoded
    by_name = {sprite.name: sprite for sprite in sprites}

    # When: the unchanged validator evaluates every expected Ferry object.
    coverage = {sprite.name: _sprite_has_coverage(image, sprite, sprites) for sprite in sprites}

    # Then: the missing c1 car is above l2, so the on rule must not add vertical offset.
    assert coverage["c1"] is False
    assert by_name["c1"].min_y > by_name["l2"].max_y
    profile = _normalized_profile("data/pddl_instances/ferry/ap.pddl")
    on = _form(profile, "(:predicate on")
    assert "(equal (?c y) (ferry y))" in on
    assert "(add (ferry y) 60)" not in on


@pytest.mark.parametrize("profile_path", IMAGE_SECTION_SHA256)
def test_embedded_image_section_matches_source_bytes(profile_path: str) -> None:
    assert _image_section_sha256(profile_path) == IMAGE_SECTION_SHA256[profile_path]


def test_profile_materialization_replaces_exact_randomcolor_sentinel() -> None:
    # Given: the exact Planimation sentinel that the pinned backend turns into a
    # process-global random.choice draw (see its Random_color extension).
    source = (
        "(:visual block\n"
        "    :properties((prefabImage img-block)\n"
        "        (color RANDOMCOLOR)\n"
        "        (width 80))\n"
        ")\n"
    )

    # When: the harness materializes the in-memory profile text before submission.
    materialized = _proof_harness()._materialize_profile_text(source)

    # Then: the exact sentinel is replaced with one valid concrete color.
    assert "(color RANDOMCOLOR)" not in materialized
    assert "(color GREY)" in materialized


def test_profile_materialization_is_idempotent_and_leaves_unrelated_text_alone() -> None:
    # Given: a profile carrying the sentinel plus unrelated colors.
    source = (
        "(:visual block :properties((color RANDOMCOLOR) (width 80)))\n"
        "(:visual claw :properties((color BLACK) (width 80)))\n"
    )

    # When: the materializer is applied repeatedly.
    harness = _proof_harness()
    once = harness._materialize_profile_text(source)
    twice = harness._materialize_profile_text(once)

    # Then: it is idempotent and unrelated text stays byte-for-byte unchanged.
    assert twice == once
    assert "(color BLACK)" in once
    assert harness._materialize_profile_text("(:predicate on :parameters (?x ?y))") == (
        "(:predicate on :parameters (?x ?y))"
    )


def test_twelve_object_problem_identifier_avoids_reserved_init_goal_substrings() -> None:
    # Given: the canonical 12-object problem source with an empty goal.
    source = (
        "(define (problem cgas-phase3-regression-replay-04-12obj-empty-goal)\n"
        "(:domain blocksworld-4ops)\n"
        "(:objects b00 b01 b02 b03 b04 b05 b06 b07 b08 b09 b10 b11 )\n"
        "(:init\n"
        "  (clear b05)\n"
        "  (clear b08)\n"
        "  (holding b09)\n"
        "  (on b01 b00)\n"
        "  (on b02 b01)\n"
        "  (on-table b00)\n"
        ")\n"
        "(:goal (and))\n"
        ")\n"
    )

    # When: the proof harness builds the 12-object non-empty-goal problem.
    built = _proof_harness()._build_twelve_object_problem(source)

    # Then: the generated problem identifier is exact and contains neither
    # reserved substring "init" nor "goal".
    identifier = _form(built, "(problem ")
    assert identifier == "(problem cgas-phase3-local-proof-04-12obj)"
    assert "init" not in identifier
    assert "goal" not in identifier

    # And: the actual :init and :goal sections remain present and unchanged.
    init = _form(built, "(:init")
    assert "(clear b09)" in init
    assert "(holding b10)" in init
    assert "(on b02 b01)" in init
    assert _form(built, "(:goal") == "(:goal (and\n(on b10 b9)\n))"
