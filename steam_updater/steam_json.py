"""Read and write Steamworks store-page localization JSON.

Steam's exported store-localization file looks like::

    {
      "itemid": "18435",
      "languages": {
        "english": {
          "app[content][about]": "...",
          "app[content][short_description]": "A brutal survival strategy game..."
        },
        "french": { ... }
      }
    }

``itemid`` is the store item / app id. ``languages`` is keyed by Steam's API
language code; each value maps localizable field keys (the ``app[...]`` form
used by the partner site) to their text. The file may carry many more fields
than we translate; we only touch the ones we are asked to and preserve the rest
verbatim so the re-import stays a faithful round-trip.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Default field keys to translate. These are the two the request targets:
# the full written description ("about") and the short description.
FIELD_ABOUT = "app[content][about]"
FIELD_SHORT_DESCRIPTION = "app[content][short_description]"
DEFAULT_FIELDS = [FIELD_ABOUT, FIELD_SHORT_DESCRIPTION]


class SteamJsonError(ValueError):
    """Raised when the localization JSON is missing required structure."""


@dataclass
class StoreListing:
    """In-memory representation of a Steam localization export.

    Attributes:
        itemid: The store item / app id (kept as a string, matching Steam).
        languages: Mapping of Steam language code -> {field key -> text}.
        extra: Any other top-level keys in the file, preserved for round-trips.
    """

    itemid: str
    languages: dict[str, dict[str, str]]
    extra: dict[str, Any] = field(default_factory=dict)

    # -- construction --------------------------------------------------------
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StoreListing":
        if not isinstance(data, dict):
            raise SteamJsonError("Top-level JSON must be an object.")
        if "languages" not in data or not isinstance(data["languages"], dict):
            raise SteamJsonError(
                "Localization JSON must contain a 'languages' object. "
                "Export it from Steamworks with the JSON format and all "
                "languages selected."
            )

        languages: dict[str, dict[str, str]] = {}
        for code, fields in data["languages"].items():
            if not isinstance(fields, dict):
                raise SteamJsonError(
                    f"languages['{code}'] must be an object of field -> text."
                )
            # Coerce values to str; Steam stores everything as text.
            languages[code] = {k: ("" if v is None else str(v)) for k, v in fields.items()}

        extra = {k: v for k, v in data.items() if k not in ("languages", "itemid")}
        itemid = str(data.get("itemid", "")).strip()
        return cls(itemid=itemid, languages=languages, extra=extra)

    @classmethod
    def load(cls, path: str | Path) -> "StoreListing":
        raw = Path(path).read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:  # pragma: no cover - message passthrough
            raise SteamJsonError(f"Invalid JSON in {path}: {exc}") from exc
        return cls.from_dict(data)

    # -- serialization -------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.itemid:
            out["itemid"] = self.itemid
        # Preserve any other top-level keys Steam included.
        out.update(self.extra)
        out["languages"] = self.languages
        return out

    def dump(self, path: str | Path, *, indent: int = 2) -> None:
        text = json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)
        Path(path).write_text(text + "\n", encoding="utf-8")

    # -- accessors -----------------------------------------------------------
    def fields_for(self, code: str) -> dict[str, str]:
        """Return the (mutable) field map for ``code``, creating it if absent."""
        return self.languages.setdefault(code, {})

    def source_text(self, code: str, field_key: str) -> str | None:
        """Return the text for ``field_key`` in language ``code`` or None."""
        lang = self.languages.get(code)
        if lang is None:
            return None
        value = lang.get(field_key)
        if value is None or value.strip() == "":
            return None
        return value

    def available_fields(self, code: str) -> list[str]:
        """List the field keys present for a given language."""
        return sorted(self.languages.get(code, {}).keys())
