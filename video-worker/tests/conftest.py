"""Shared test guards — keep the suite hermetic.

Ambient .env leaks DIRECTOR_ENABLED/DOCUMENTARY_ENGINE_V2 into tests. The pipeline
reads those at call time, so a test that mocks the legacy stock path silently runs
the real Director path instead: live Pexels + LLM calls, 429 retries (~30 s each),
and the mocked functions never get called. Many test files delenv'd these by hand;
this does it once. Tests that need a mode set it themselves via monkeypatch.

pipeline.refine_script hits Wikipedia + the LLM quality editor for the same reason.
Tests that assert on real refinement behaviour call app.script_quality.refine_script
directly and are unaffected.
"""
from __future__ import annotations

import pytest

from app.script_quality import ScriptQualityResult

_PIPELINE_MODE_ENV = ("DIRECTOR_ENABLED", "DOCUMENTARY_ENGINE_V2")


@pytest.fixture(autouse=True)
def _default_legacy_pipeline_mode(request, monkeypatch):
    if request.node.get_closest_marker("live"):
        return
    for name in _PIPELINE_MODE_ENV:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _stub_pipeline_refine_script(request, monkeypatch):
    if request.node.get_closest_marker("live"):
        return
    import app.pipeline as pipeline

    monkeypatch.setattr(
        pipeline,
        "refine_script",
        lambda script, **kw: ScriptQualityResult(
            raw_script=script or "", final_script=script or ""
        ),
    )
