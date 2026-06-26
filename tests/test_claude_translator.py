from steam_updater.translator.base import TranslationRequest
from steam_updater.translator.claude import ClaudeTranslator


class _Block:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _Response:
    def __init__(self, text):
        self.content = [_Block(text)]


class _FakeMessages:
    def __init__(self, captured):
        self._captured = captured

    def create(self, **kwargs):
        self._captured.update(kwargs)
        return _Response("  translated text  ")


class _FakeClient:
    def __init__(self):
        self.captured: dict = {}
        self.messages = _FakeMessages(self.captured)


def test_translate_strips_and_returns_text():
    client = _FakeClient()
    tr = ClaudeTranslator(model="test-model", client=client)
    out = tr.translate(TranslationRequest(text="Hello", target_language="French"))
    assert out == "translated text"
    assert client.captured["model"] == "test-model"


def test_prompt_includes_do_not_translate_and_glossary():
    client = _FakeClient()
    tr = ClaudeTranslator(client=client)
    tr.translate(
        TranslationRequest(
            text="Play Halcyon Drift",
            target_language="German",
            do_not_translate=["Halcyon Drift"],
            glossary={"wishlist": "Wunschliste"},
            style="punchy",
        )
    )
    prompt = client.captured["messages"][0]["content"]
    assert "German" in prompt
    assert "Halcyon Drift" in prompt
    assert "wishlist -> Wunschliste" in prompt
    assert "punchy" in prompt


def test_short_description_prompt_mentions_char_limit():
    client = _FakeClient()
    tr = ClaudeTranslator(client=client)
    tr.translate(
        TranslationRequest(
            text="Short",
            target_language="Japanese",
            is_short_description=True,
            char_limit=300,
        )
    )
    prompt = client.captured["messages"][0]["content"]
    assert "300 characters" in prompt
