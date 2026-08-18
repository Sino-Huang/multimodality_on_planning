from __future__ import annotations

import json
from pathlib import Path

from scripts.phase3.cgas_qwenvl import build_corpus
from scripts.phase3.cgas_qwenvl_preflight import strict_preflight
from scripts.phase3.cgas_release_gate import publish_release_manifest, verify_release_inputs
from test_cgas_qwenvl_conversion import _inputs
from test_cgas_qwenvl_preflight import FakeQwenProcessor


def test_release_gate_publishes_manifest_only_after_all_prerequisites_and_loader_checks_pass(tmp_path: Path) -> None:
    # Given: accepted source, alignment, steps, Qwen conversion, and strict loader preflight reports.
    corpus = _accepted_release_root(tmp_path)
    preflight = strict_preflight(corpus / "qwenvl", corpus / "qwenvl" / "images", FakeQwenProcessor())

    # When: the fail-closed release gate evaluates and publishes.
    report = publish_release_manifest(corpus, preflight)

    # Then: the release manifest binds current prerequisite manifests and loader counters.
    release_path = corpus / "release_manifest.json"
    manifest = json.loads(release_path.read_text(encoding="utf-8"))
    assert report["accepted"] is True
    assert report["rejections"] == []
    assert manifest["schema_version"] == "planning_cgas_release_v1"
    assert manifest["preflight"]["records_checked"] == 12
    assert set(manifest["artifacts"]) == {"source", "alignment", "steps", "qwenvl"}


def test_release_gate_refuses_and_preserves_prior_release_when_prerequisite_report_fails(tmp_path: Path) -> None:
    # Given: a prior approved release and a later stale prerequisite manifest.
    corpus = _accepted_release_root(tmp_path)
    preflight = strict_preflight(corpus / "qwenvl", corpus / "qwenvl" / "images", FakeQwenProcessor())
    assert publish_release_manifest(corpus, preflight)["accepted"] is True
    before = (corpus / "release_manifest.json").read_bytes()
    steps_manifest = json.loads((corpus / "steps_manifest.json").read_text(encoding="utf-8"))
    steps_manifest["steps_digest"] = "0" * 64
    (corpus / "steps_manifest.json").write_text(json.dumps(steps_manifest), encoding="utf-8")

    # When: release publication is attempted against the stale prerequisite.
    report = publish_release_manifest(corpus, preflight)

    # Then: publication is refused, no pending manifest survives, and prior bytes remain intact.
    assert report["accepted"] is False
    assert _rejection_reasons(report) == {"certificates_failed"}
    assert (corpus / "release_manifest.json").read_bytes() == before
    assert not list(corpus.glob(".release_manifest.json-*"))


def test_release_gate_refuses_loader_failure_without_publishing(tmp_path: Path) -> None:
    # Given: accepted prerequisite artifacts but a failed strict loader preflight report.
    corpus = _accepted_release_root(tmp_path)
    preflight = strict_preflight(corpus / "qwenvl", corpus / "qwenvl" / "images", FakeQwenProcessor())
    preflight["tokenization_failures"] = 1

    # When: release inputs are evaluated.
    report = verify_release_inputs(corpus, preflight)

    # Then: the loader failure alone prevents publication.
    assert report["accepted"] is False
    assert _rejection_reasons(report) == {"loader_preflight_failed"}
    assert not (corpus / "release_manifest.json").exists()


def _accepted_release_root(root: Path) -> Path:
    source, alignment, steps = _inputs(root)
    corpus = root / "release" / "planning_cgas_v1"
    corpus.parent.mkdir(parents=True)
    corpus.mkdir()
    for _name, source_root in (("source", source), ("alignment", alignment), ("steps", steps)):
        for path in source_root.iterdir():
            destination = corpus / path.name
            if path.is_dir():
                if destination.exists():
                    continue
                import shutil

                shutil.copytree(path, destination)
            else:
                destination.write_bytes(path.read_bytes())
    assert build_corpus(corpus, corpus, corpus, corpus / "qwenvl")["rejections"] == []
    return corpus


def _rejection_reasons(report: dict[str, object]) -> set[str]:
    rejections = report["rejections"]
    assert isinstance(rejections, list)
    reasons: set[str] = set()
    for rejection in rejections:
        assert isinstance(rejection, dict)
        reason = rejection["reason"]
        assert isinstance(reason, str)
        reasons.add(reason)
    return reasons
