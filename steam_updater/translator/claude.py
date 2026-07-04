"""Claude-backed translator.

Uses the Anthropic Messages API. Claude is a good fit for Steam store copy
because it can be instructed to preserve BBCode markup, keep proper nouns (game
name, characters) untranslated, honour a glossary, and respect the short
description's tight character budget — things raw MT engines handle poorly.
"""

from __future__ import annotations

import textwrap

from steam_updater.translator.base import TranslationRequest, Translator

# Per the project default, use the most capable widely available model. Override
# via config (`model:`) or the --model CLI flag for a cheaper/faster option.
DEFAULT_MODEL = "claude-opus-4-8"

_SYSTEM_PROMPT = textwrap.dedent(
    """\
    You are a professional video-game localization translator specializing in
    Steam store pages. You translate marketing copy so it reads naturally to
    native speakers and drives wishlists and sales, not as a literal,
    word-for-word conversion.

    Hard rules:
    - Preserve all Steam BBCode markup EXACTLY: tags such as [h1][/h1], [b][/b],
      [i][/i], [u][/u], [list][*][/list], [url=...][/url], [quote][/quote],
      [code], [strike], [spoiler], [img], [video], [previewyoutube]. Translate
      the visible text inside tags, never the tag names, attributes, or URLs.
    - Preserve Steam asset macros byte-for-byte: any occurrence of
      {STEAM_APP_IMAGE}, any /extras/... path, and every attribute value inside
      [img ...] and [video ...] tags (mp4=, webm=, poster=, autoplay=) must
      remain exactly as written.
    - Keep line breaks and paragraph structure intact.
    - Do NOT translate proper nouns: the game's title, character names, place
      names, brand names, and trademarks stay in their original form unless a
      glossary entry says otherwise.
    - Adapt idioms and tone to the target locale; localize, don't transliterate.
    - Output ONLY the translated text. No explanations, no notes, no quotation
      marks wrapping the result, no markdown code fences.
    """
)


class ClaudeTranslator(Translator):
    """Translate text with Anthropic's Claude models."""

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        max_tokens: int = 8000,
        api_key: str | None = None,
        client: object | None = None,
    ) -> None:
        """Create a translator.

        Args:
            model: Anthropic model id.
            max_tokens: Output token ceiling. Kept under ~16k so non-streaming
                requests don't risk SDK HTTP timeouts.
            api_key: Optional explicit key. If omitted, the SDK reads
                ANTHROPIC_API_KEY from the environment.
            client: Optional pre-built Anthropic client (mainly for tests).
        """
        self.model = model
        self.max_tokens = max_tokens
        if client is not None:
            self._client = client
        else:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - depends on env
                raise RuntimeError(
                    "The 'anthropic' package is required for the Claude "
                    "translator. Install it with: pip install anthropic"
                ) from exc
            self._client = (
                anthropic.Anthropic(api_key=api_key)
                if api_key
                else anthropic.Anthropic()
            )

    # -- prompt building -----------------------------------------------------
    @staticmethod
    def _build_user_prompt(request: TranslationRequest) -> str:
        parts: list[str] = [
            f"Translate the following Steam store text from "
            f"{request.source_language} into {request.target_language}.",
        ]

        if request.is_short_description:
            limit = request.char_limit or 300
            parts.append(
                "This is the store SHORT DESCRIPTION. Keep it punchy and within "
                f"{limit} characters; Steam truncates longer text on the page."
            )

        if request.do_not_translate:
            terms = ", ".join(request.do_not_translate)
            parts.append(f"Keep these terms unchanged (do not translate): {terms}.")

        if request.glossary:
            lines = "\n".join(
                f"- {term} -> {translation}"
                for term, translation in request.glossary.items()
            )
            parts.append("Use these preferred translations:\n" + lines)

        if request.style:
            parts.append(f"Tone and style guidance: {request.style}")

        parts.append("Text to translate:\n\n" + request.text)
        return "\n\n".join(parts)

    # -- translation ---------------------------------------------------------
    def translate(self, request: TranslationRequest) -> str:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": self._build_user_prompt(request)}],
        )
        return self._extract_text(response).strip()

    @staticmethod
    def _extract_text(response: object) -> str:
        """Concatenate the text blocks from an Anthropic Messages response."""
        chunks: list[str] = []
        for block in getattr(response, "content", []) or []:
            if getattr(block, "type", None) == "text":
                chunks.append(block.text)
        return "".join(chunks)
