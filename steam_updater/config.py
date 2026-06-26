"""Configuration loading for the Steam page updater."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from steam_updater import languages
from steam_updater.steam_json import DEFAULT_FIELDS, FIELD_SHORT_DESCRIPTION
from steam_updater.translator.claude import DEFAULT_MODEL


class ConfigError(ValueError):
    """Raised when a config file is malformed."""


@dataclass
class Config:
    """Settings controlling what gets translated and how.

    Attributes:
        source_language: Steam language code to translate from (default english).
        target_languages: Steam language codes to translate into.
        fields: Field keys to translate, e.g. app[content][about].
        model: Anthropic model id.
        max_tokens: Output token ceiling per translation request.
        short_description_field: Which field is treated as the short description.
        short_description_max_chars: Character budget for the short description.
        do_not_translate: Terms kept verbatim (game name, characters, ...).
        glossary: Preferred translations (term -> translation).
        style: Free-form tone/voice guidance passed to the translator.
    """

    target_languages: list[str]
    source_language: str = "english"
    fields: list[str] = field(default_factory=lambda: list(DEFAULT_FIELDS))
    model: str = DEFAULT_MODEL
    max_tokens: int = 8000
    short_description_field: str = FIELD_SHORT_DESCRIPTION
    short_description_max_chars: int = 300
    do_not_translate: list[str] = field(default_factory=list)
    glossary: dict[str, str] = field(default_factory=dict)
    style: str = ""

    def __post_init__(self) -> None:
        self.source_language = languages.normalize(self.source_language)
        self.target_languages = [
            languages.normalize(c)
            for c in self.target_languages
            if languages.normalize(c) != self.source_language
        ]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        if not isinstance(data, dict):
            raise ConfigError("Config must be a mapping.")

        targets = data.get("target_languages")
        if not targets:
            raise ConfigError("Config must list at least one target_language.")
        if not isinstance(targets, list):
            raise ConfigError("target_languages must be a list.")

        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        unknown = set(data) - known
        if unknown:
            raise ConfigError(
                f"Unknown config keys: {', '.join(sorted(unknown))}. "
                f"Allowed: {', '.join(sorted(known))}."
            )

        return cls(**data)

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover - depends on env
            raise RuntimeError(
                "PyYAML is required to read config files. "
                "Install it with: pip install pyyaml"
            ) from exc

        raw = Path(path).read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}
        return cls.from_dict(data)
