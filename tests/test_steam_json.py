import json

import pytest

from steam_updater.steam_json import StoreListing, SteamJsonError


def test_round_trip_preserves_structure(tmp_path):
    data = {
        "itemid": "42",
        "languages": {
            "english": {
                "app[content][about]": "Hello [b]world[/b]",
                "app[content][short_description]": "Hi",
            }
        },
        "some_other_top_level": {"keep": "me"},
    }
    path = tmp_path / "export.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    listing = StoreListing.load(path)
    assert listing.itemid == "42"
    assert listing.extra["some_other_top_level"] == {"keep": "me"}

    out = tmp_path / "out.json"
    listing.dump(out)
    reloaded = json.loads(out.read_text(encoding="utf-8"))
    assert reloaded["itemid"] == "42"
    assert reloaded["some_other_top_level"] == {"keep": "me"}
    assert reloaded["languages"]["english"]["app[content][about]"] == "Hello [b]world[/b]"


def test_missing_languages_raises():
    with pytest.raises(SteamJsonError):
        StoreListing.from_dict({"itemid": "1"})


def test_non_object_language_raises():
    with pytest.raises(SteamJsonError):
        StoreListing.from_dict({"languages": {"english": "not-an-object"}})


def test_source_text_treats_blank_as_missing():
    listing = StoreListing.from_dict(
        {"languages": {"english": {"app[content][about]": "   "}}}
    )
    assert listing.source_text("english", "app[content][about]") is None
    assert listing.source_text("english", "missing") is None


def test_fields_for_creates_language():
    listing = StoreListing.from_dict({"languages": {"english": {}}})
    fields = listing.fields_for("french")
    fields["app[content][about]"] = "Bonjour"
    assert listing.languages["french"]["app[content][about]"] == "Bonjour"


def test_non_ascii_is_not_escaped(tmp_path):
    listing = StoreListing.from_dict(
        {"languages": {"japanese": {"app[content][about]": "こんにちは"}}}
    )
    out = tmp_path / "out.json"
    listing.dump(out)
    assert "こんにちは" in out.read_text(encoding="utf-8")
