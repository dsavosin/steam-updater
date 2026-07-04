import pytest

from steam_updater.resources import (
    Asset,
    OptimizerResources,
    ResourceError,
    scaffold,
)


def _make_resources(tmp_path, *, game="Pitch: a space game.", assets_yaml=None, examples=None):
    root = tmp_path / "resources"
    root.mkdir(parents=True)
    (root / "game.md").write_text(game, encoding="utf-8")
    if assets_yaml is not None:
        (root / "assets.yaml").write_text(assets_yaml, encoding="utf-8")
    if examples:
        ex = root / "examples"
        ex.mkdir()
        for name, text in examples.items():
            (ex / name).write_text(text, encoding="utf-8")
    return root


def test_load_happy_path(tmp_path):
    root = _make_resources(
        tmp_path,
        assets_yaml=(
            "assets:\n"
            "  - file: combat.mp4\n"
            "    type: video\n"
            "    poster: combat_poster.png\n"
            "    shows: Ship combat\n"
            "  - file: building.gif\n"
            "    type: gif\n"
            "    shows: Base building\n"
        ),
        examples={"game-a.md": "Example A", "README.md": "ignore me", "notes.pdf": "skip"},
    )
    res = OptimizerResources.load(root)
    assert res.game_context.startswith("Pitch:")
    assert res.examples == ["Example A"]
    assert [a.file for a in res.assets] == ["combat.mp4", "building.gif"]
    assert res.upload_checklist() == ["combat.mp4", "combat_poster.png", "building.gif"]


def test_missing_folder_and_missing_game_md(tmp_path):
    with pytest.raises(ResourceError, match="Resources folder not found"):
        OptimizerResources.load(tmp_path / "nope")
    empty = tmp_path / "resources"
    empty.mkdir()
    with pytest.raises(ResourceError, match="game.md"):
        OptimizerResources.load(empty)


def test_empty_game_md_rejected(tmp_path):
    root = _make_resources(tmp_path, game="   \n")
    with pytest.raises(ResourceError, match="empty"):
        OptimizerResources.load(root)


def test_asset_validation_errors(tmp_path):
    cases = {
        "unknown type": "assets:\n  - {file: a.gif, type: webm, shows: x}\n",
        "poster on gif": "assets:\n  - {file: a.gif, type: gif, poster: p.png, shows: x}\n",
        "duplicate": (
            "assets:\n"
            "  - {file: a.gif, type: gif, shows: x}\n"
            "  - {file: a.gif, type: gif, shows: y}\n"
        ),
        "missing keys": "assets:\n  - {file: a.gif}\n",
        "not a list": "assets: {file: a.gif}\n",
    }
    for label, yaml_text in cases.items():
        root = _make_resources(tmp_path / label.replace(" ", "_"), assets_yaml=yaml_text)
        with pytest.raises(ResourceError):
            OptimizerResources.load(root)


def test_missing_assets_and_examples_are_optional(tmp_path):
    root = _make_resources(tmp_path)
    res = OptimizerResources.load(root)
    assert res.assets == []
    assert res.examples == []


def test_asset_bbcode():
    gif = Asset(file="a.gif", type="gif", shows="x")
    assert gif.bbcode() == "[img]{STEAM_APP_IMAGE}/extras/a.gif[/img]"
    vid = Asset(file="v.mp4", type="video", shows="x", poster="p.png")
    assert vid.bbcode() == (
        "[video mp4={STEAM_APP_IMAGE}/extras/v.mp4 "
        "poster={STEAM_APP_IMAGE}/extras/p.png][/video]"
    )
    bare = Asset(file="v.mp4", type="video", shows="x")
    assert bare.bbcode() == "[video mp4={STEAM_APP_IMAGE}/extras/v.mp4][/video]"


def test_scaffold_creates_and_respects_existing(tmp_path):
    root = tmp_path / "res"
    written = scaffold(root)
    assert {p.name for p in written} == {"game.md", "assets.yaml", "README.md"}

    (root / "game.md").write_text("my edits", encoding="utf-8")
    written_again = scaffold(root)
    assert written_again == []
    assert (root / "game.md").read_text(encoding="utf-8") == "my edits"

    forced = scaffold(root, force=True)
    assert len(forced) == 3
    assert "my edits" not in (root / "game.md").read_text(encoding="utf-8")


def test_scaffolded_assets_yaml_loads(tmp_path):
    root = tmp_path / "res"
    scaffold(root)
    # The template must parse as a valid (empty) manifest.
    res_dir = root
    (res_dir / "game.md").write_text("context", encoding="utf-8")
    res = OptimizerResources.load(res_dir)
    assert res.assets == []
