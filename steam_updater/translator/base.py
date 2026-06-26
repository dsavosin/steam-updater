"""Translator interface shared by all backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class TranslationRequest:
    """A single piece of store-page text to translate.

    Attributes:
        text: The source text (may contain Steam BBCode such as [h1]...[/h1]).
        target_language: Descriptive target language, e.g. "Brazilian Portuguese".
        source_language: Descriptive source language, default "English".
        field_key: The Steam field key, e.g. "app[content][about]" — used for
            logging and to let backends special-case fields.
        is_short_description: True for the short-description field, which Steam
            limits to roughly 300 characters and which should stay punchy.
        char_limit: Optional hard character budget (used for short descriptions).
        do_not_translate: Terms to keep verbatim (game name, character names).
        glossary: Preferred translations for specific terms (term -> translation).
        style: Free-form tone/voice guidance for the translator.
    """

    text: str
    target_language: str
    source_language: str = "English"
    field_key: str = ""
    is_short_description: bool = False
    char_limit: int | None = None
    do_not_translate: list[str] = field(default_factory=list)
    glossary: dict[str, str] = field(default_factory=dict)
    style: str = ""


class Translator(ABC):
    """Translate store-page text into a target language.

    Implementations must preserve Steam BBCode markup and return only the
    translated text (no preamble, no surrounding quotes).
    """

    @abstractmethod
    def translate(self, request: TranslationRequest) -> str:
        """Translate ``request.text`` and return the translated string."""
        raise NotImplementedError
