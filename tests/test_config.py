import pytest

from steam_updater.config import Config, ConfigError


def test_source_language_excluded_from_targets():
    cfg = Config(target_languages=["english", "french", "FRENCH"], source_language="english")
    assert cfg.source_language == "english"
    assert cfg.target_languages == ["french", "french"]  # dedup is not promised, exclusion is


def test_missing_targets_raises():
    with pytest.raises(ConfigError):
        Config.from_dict({"source_language": "english"})


def test_unknown_key_raises():
    with pytest.raises(ConfigError):
        Config.from_dict({"target_languages": ["french"], "bogus": 1})


def test_from_dict_defaults():
    cfg = Config.from_dict({"target_languages": ["French", "German"]})
    assert cfg.target_languages == ["french", "german"]
    assert cfg.model == "claude-opus-4-8"
    assert "app[content][about]" in cfg.fields
