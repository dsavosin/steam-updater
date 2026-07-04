import json

import pytest

from steam_updater.optimizer import (
    DescriptionOptimizer,
    OptimizedDescription,
    OptimizerError,
    validate_output,
)
from steam_updater.resources import Asset, OptimizerResources


def _resources(assets=None, examples=None):
    return OptimizerResources(
        game_context="Pitch: brutal space survival.\n\nJTBD: feel like a scrappy captain.",
        examples=examples or ["Example description from another game"],
        assets=assets if assets is not None else [
            Asset(file="combat.mp4", type="video", shows="Ship combat", poster="poster.png"),
            Asset(file="building.gif", type="gif", shows="Base building"),
        ],
    )


# -- prompt ---------------------------------------------------------------

def test_prompt_includes_context_examples_and_asset_snippets():
    prompt = DescriptionOptimizer.build_user_prompt(
        _resources(), current_about="Old text", current_short="Old short",
    )
    assert "scrappy captain" in prompt                      # game context / JTBD
    assert "Example description from another game" in prompt
    assert "[img]{STEAM_APP_IMAGE}/extras/building.gif[/img]" in prompt
    assert "[video mp4={STEAM_APP_IMAGE}/extras/combat.mp4" in prompt
    assert "Old text" in prompt and "Old short" in prompt
    assert "300" in prompt


def test_prompt_without_assets_forbids_embeds():
    prompt = DescriptionOptimizer.build_user_prompt(_resources(assets=[]))
    assert "Do not embed any [img] or" in prompt


# -- response parsing -------------------------------------------------------

class _Block:
    type = "text"

    def __init__(self, text):
        self.text = text


class _Response:
    def __init__(self, text):
        self.content = [_Block(text)]


class _FakeMessages:
    def __init__(self, captured, reply):
        self._captured = captured
        self._reply = reply

    def create(self, **kwargs):
        self._captured.update(kwargs)
        return _Response(self._reply)


class _FakeClient:
    def __init__(self, reply):
        self.captured: dict = {}
        self.messages = _FakeMessages(self.captured, reply)


def test_optimize_parses_structured_json():
    reply = json.dumps({"about": "[h1]Game[/h1] body", "short_description": "Short."})
    client = _FakeClient(reply)
    opt = DescriptionOptimizer(model="test-model", client=client)
    result = opt.optimize(_resources())
    assert result.about.startswith("[h1]")
    assert result.short_description == "Short."
    assert client.captured["model"] == "test-model"
    schema = client.captured["output_config"]["format"]["schema"]
    assert set(schema["required"]) == {"about", "short_description"}


def test_optimize_rejects_bad_json_and_missing_fields():
    with pytest.raises(OptimizerError, match="non-JSON"):
        DescriptionOptimizer(client=_FakeClient("not json")).optimize(_resources())
    empty = json.dumps({"about": "", "short_description": "x"})
    with pytest.raises(OptimizerError, match="missing"):
        DescriptionOptimizer(client=_FakeClient(empty)).optimize(_resources())


# -- validation --------------------------------------------------------------

def test_validation_accepts_known_refs_and_builds_checklist():
    optimized = OptimizedDescription(
        about=(
            "Fight!\n[video mp4={STEAM_APP_IMAGE}/extras/combat.mp4 "
            "poster={STEAM_APP_IMAGE}/extras/poster.png][/video]\n"
            "Build!\n[img]{STEAM_APP_IMAGE}/extras/building.gif[/img]"
        ),
        short_description="Short.",
    )
    report = validate_output(optimized, _resources())
    assert report.ok
    assert report.warnings == []
    assert report.upload_checklist == ["combat.mp4", "poster.png", "building.gif"]


def test_validation_flags_hallucinated_asset():
    optimized = OptimizedDescription(
        about="[img]{STEAM_APP_IMAGE}/extras/does_not_exist.gif[/img]",
        short_description="Short.",
    )
    report = validate_output(optimized, _resources())
    assert not report.ok
    assert "does_not_exist.gif" in report.errors[0]


def test_validation_warns_on_unused_assets_and_long_short_description():
    optimized = OptimizedDescription(about="No embeds here.", short_description="x" * 400)
    report = validate_output(optimized, _resources())
    assert report.ok  # warnings only
    assert any("combat.mp4" in w for w in report.warnings)
    assert any("building.gif" in w for w in report.warnings)
    assert any("400 chars" in w for w in report.warnings)
    assert report.upload_checklist == []


def test_validation_rejects_asset_in_short_description():
    optimized = OptimizedDescription(
        about="ok",
        short_description="See [img]{STEAM_APP_IMAGE}/extras/building.gif[/img]",
    )
    report = validate_output(optimized, _resources())
    assert not report.ok
