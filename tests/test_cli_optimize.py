import json

from steam_updater.cli import main
from steam_updater.resources import scaffold


def _write_export(tmp_path):
    export = {
        "itemid": "1",
        "languages": {
            "english": {
                "app[content][about]": "Old about text",
                "app[content][short_description]": "Old short",
            }
        },
    }
    path = tmp_path / "export.json"
    path.write_text(json.dumps(export), encoding="utf-8")
    return path


def test_init_resources_then_optimize_dry_run(tmp_path, capsys):
    res_dir = tmp_path / "res"
    assert main(["init-resources", "-r", str(res_dir)]) == 0
    (res_dir / "game.md").write_text("Pitch: a space game. JTBD: captain fantasy.")
    (res_dir / "examples" / "other-game.md").write_text("Example structure")
    (res_dir / "assets.yaml").write_text(
        "assets:\n  - {file: fight.gif, type: gif, shows: Combat}\n"
    )

    export = _write_export(tmp_path)
    code = main([
        "optimize", "-i", str(export), "-r", str(res_dir), "--dry-run",
        "-o", str(tmp_path / "out.json"),
    ])
    assert code == 0
    out = capsys.readouterr().out
    # The dry run prints the assembled prompt, built from all three resources.
    assert "captain fantasy" in out
    assert "Example structure" in out
    assert "[img]{STEAM_APP_IMAGE}/extras/fight.gif[/img]" in out
    assert "Old about text" in out
    assert not (tmp_path / "out.json").exists()


def test_optimize_requires_resources_folder(tmp_path):
    export = _write_export(tmp_path)
    code = main([
        "optimize", "-i", str(export), "-r", str(tmp_path / "missing"), "--dry-run",
    ])
    assert code == 2  # ResourceError -> CLI error exit


def test_pipeline_dry_run_skips_optimizer(tmp_path, caplog):
    import logging

    res_dir = tmp_path / "res"
    scaffold(res_dir)
    (res_dir / "game.md").write_text("context")
    export = _write_export(tmp_path)

    with caplog.at_level(logging.INFO, logger="steam_updater"):
        code = main([
            "pipeline", "-i", str(export), "-r", str(res_dir),
            "-l", "french", "--dry-run",
        ])
    assert code == 0
    assert "Skipping optimize stage" in caplog.text
