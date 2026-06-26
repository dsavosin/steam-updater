"""Mapping of Steam store-localization language codes to human-readable names.

Steamworks' localization JSON keys each language by its Steam "API language
code" (lowercase English-ish names such as ``english``, ``schinese``,
``koreana``). When we ask Claude to translate, we want a descriptive target
language name (including the regional variant) rather than an ISO code, because
the model produces better marketing copy when told, e.g., "Brazilian
Portuguese" instead of "pt-BR".

The list mirrors the languages Steam supports for store-page localization. See
https://partner.steamgames.com/doc/store/localization/languages
"""

from __future__ import annotations

# Steam API language code -> descriptive language name for the translator.
STEAM_LANGUAGES: dict[str, str] = {
    "arabic": "Arabic",
    "bulgarian": "Bulgarian",
    "schinese": "Simplified Chinese",
    "tchinese": "Traditional Chinese",
    "czech": "Czech",
    "danish": "Danish",
    "dutch": "Dutch",
    "english": "English",
    "finnish": "Finnish",
    "french": "French",
    "german": "German",
    "greek": "Greek",
    "hungarian": "Hungarian",
    "indonesian": "Indonesian",
    "italian": "Italian",
    "japanese": "Japanese",
    "koreana": "Korean",
    "norwegian": "Norwegian",
    "polish": "Polish",
    "portuguese": "Portuguese (Portugal)",
    "brazilian": "Brazilian Portuguese",
    "romanian": "Romanian",
    "russian": "Russian",
    "spanish": "Spanish (Spain)",
    "latam": "Latin American Spanish",
    "swedish": "Swedish",
    "thai": "Thai",
    "turkish": "Turkish",
    "ukrainian": "Ukrainian",
    "vietnamese": "Vietnamese",
}


def is_supported(code: str) -> bool:
    """Return True if ``code`` is a known Steam store-localization language."""
    return code.lower() in STEAM_LANGUAGES


def language_name(code: str) -> str:
    """Return the descriptive name for a Steam language ``code``.

    Falls back to the raw code (title-cased) for languages not in the table so
    that unusual or newly-added Steam codes still produce a usable prompt.
    """
    return STEAM_LANGUAGES.get(code.lower(), code.replace("_", " ").title())


def normalize(code: str) -> str:
    """Normalize a user-supplied language code to Steam's lowercase form."""
    return code.strip().lower()
