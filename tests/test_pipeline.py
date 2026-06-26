from steam_updater.config import Config
from steam_updater.pipeline import TranslationPipeline
from steam_updater.steam_json import StoreListing
from steam_updater.translator.base import TranslationRequest, Translator


class FakeTranslator(Translator):
    """Records requests and returns a predictable marker translation."""

    def __init__(self):
        self.requests: list[TranslationRequest] = []

    def translate(self, request: TranslationRequest) -> str:
        self.requests.append(request)
        return f"[{request.target_language}] {request.text}"


def _listing():
    return StoreListing.from_dict(
        {
            "itemid": "1",
            "languages": {
                "english": {
                    "app[content][about]": "Hello [b]world[/b]",
                    "app[content][short_description]": "Short and punchy.",
                }
            },
        }
    )


def test_translates_all_fields_for_each_language():
    cfg = Config(target_languages=["french", "german"], source_language="english")
    fake = FakeTranslator()
    listing = _listing()

    result = TranslationPipeline(cfg, fake).run(listing)

    assert result.translated == 4  # 2 fields x 2 languages
    assert listing.languages["french"]["app[content][about]"] == "[French] Hello [b]world[/b]"
    assert "Simplified Chinese" not in str(result.results)
    # Short description carries the char limit through to the request.
    short_reqs = [r for r in fake.requests if r.is_short_description]
    assert short_reqs and short_reqs[0].char_limit == 300


def test_existing_translation_is_kept_without_overwrite():
    cfg = Config(target_languages=["french"], source_language="english")
    listing = _listing()
    listing.fields_for("french")["app[content][about]"] = "déjà traduit"

    result = TranslationPipeline(cfg, FakeTranslator()).run(listing)

    assert listing.languages["french"]["app[content][about]"] == "déjà traduit"
    assert result.count("skipped-existing") == 1
    assert result.translated == 1  # only the short description


def test_overwrite_replaces_existing():
    cfg = Config(target_languages=["french"], source_language="english")
    listing = _listing()
    listing.fields_for("french")["app[content][about]"] = "old"

    TranslationPipeline(cfg, FakeTranslator()).run(listing, overwrite=True)

    assert listing.languages["french"]["app[content][about]"].startswith("[French]")


def test_dry_run_does_not_call_translator():
    cfg = Config(target_languages=["french"], source_language="english")
    result = TranslationPipeline(cfg, translator=None).run(_listing(), dry_run=True)
    assert result.translated == 2
    assert all(r.detail == "dry-run" for r in result.results if r.status == "translated")


def test_missing_source_text_is_skipped():
    cfg = Config(
        target_languages=["french"],
        source_language="english",
        fields=["app[content][about]", "app[content][legal]"],
    )
    fake = FakeTranslator()
    result = TranslationPipeline(cfg, fake).run(_listing())
    assert result.count("skipped-no-source") == 1  # legal has no source text


def test_translator_error_is_reported_not_raised():
    class Boom(Translator):
        def translate(self, request):
            raise RuntimeError("api down")

    cfg = Config(target_languages=["french"], source_language="english")
    result = TranslationPipeline(cfg, Boom()).run(_listing())
    assert len(result.errors) == 2
    assert "api down" in result.errors[0].detail


def test_short_description_over_limit_is_flagged():
    class LongTranslator(Translator):
        def translate(self, request):
            return "x" * 400 if request.is_short_description else "ok"

    cfg = Config(target_languages=["french"], source_language="english")
    result = TranslationPipeline(cfg, LongTranslator()).run(_listing())
    flagged = [r for r in result.results if r.detail and "char limit" in r.detail]
    assert flagged


def test_missing_source_language_raises():
    cfg = Config(target_languages=["french"], source_language="klingon")
    try:
        TranslationPipeline(cfg, FakeTranslator()).run(_listing())
    except ValueError as exc:
        assert "klingon" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")
