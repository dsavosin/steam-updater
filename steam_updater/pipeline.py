"""Orchestrate translating a Steam localization export into many languages."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from steam_updater import languages
from steam_updater.config import Config
from steam_updater.steam_json import StoreListing
from steam_updater.translator.base import TranslationRequest, Translator

log = logging.getLogger("steam_updater")


@dataclass
class FieldResult:
    """Outcome for one (language, field) pair."""

    language: str
    field_key: str
    status: str  # "translated", "skipped-existing", "skipped-no-source", "error"
    detail: str = ""
    chars: int = 0


@dataclass
class PipelineResult:
    """Aggregate outcome of a translation run."""

    results: list[FieldResult] = field(default_factory=list)

    def add(self, result: FieldResult) -> None:
        self.results.append(result)

    def count(self, status: str) -> int:
        return sum(1 for r in self.results if r.status == status)

    @property
    def translated(self) -> int:
        return self.count("translated")

    @property
    def errors(self) -> list[FieldResult]:
        return [r for r in self.results if r.status == "error"]

    def summary(self) -> str:
        return (
            f"{self.translated} translated, "
            f"{self.count('skipped-existing')} kept (already present), "
            f"{self.count('skipped-no-source')} skipped (no source text), "
            f"{len(self.errors)} errors"
        )


class TranslationPipeline:
    """Translate the configured fields of a StoreListing into target languages."""

    def __init__(self, config: Config, translator: Translator | None) -> None:
        """Create a pipeline.

        Args:
            config: What to translate and how.
            translator: Backend that performs translation. May be None only in
                dry-run mode, where no translation is performed.
        """
        self.config = config
        self.translator = translator

    def run(
        self,
        listing: StoreListing,
        *,
        overwrite: bool = False,
        dry_run: bool = False,
    ) -> PipelineResult:
        """Translate ``listing`` in place and return a per-field report.

        Args:
            listing: The parsed export; mutated in place with translations.
            overwrite: Re-translate fields that already exist for a language.
            dry_run: Report what would be translated without calling the API.
        """
        result = PipelineResult()
        src = self.config.source_language

        if src not in listing.languages:
            raise ValueError(
                f"Source language '{src}' not found in the export. "
                f"Available: {', '.join(sorted(listing.languages)) or '(none)'}."
            )

        for code in self.config.target_languages:
            target_fields = listing.fields_for(code)
            for field_key in self.config.fields:
                self._handle_field(
                    listing=listing,
                    target_fields=target_fields,
                    code=code,
                    field_key=field_key,
                    overwrite=overwrite,
                    dry_run=dry_run,
                    result=result,
                )
        return result

    def _handle_field(
        self,
        *,
        listing: StoreListing,
        target_fields: dict[str, str],
        code: str,
        field_key: str,
        overwrite: bool,
        dry_run: bool,
        result: PipelineResult,
    ) -> None:
        cfg = self.config
        source_text = listing.source_text(cfg.source_language, field_key)

        if source_text is None:
            log.warning("No source text for %s in %s; skipping.", field_key, cfg.source_language)
            result.add(FieldResult(code, field_key, "skipped-no-source"))
            return

        existing = target_fields.get(field_key)
        if existing and existing.strip() and not overwrite:
            log.info("Keeping existing %s for %s (use --overwrite to replace).", field_key, code)
            result.add(FieldResult(code, field_key, "skipped-existing"))
            return

        is_short = field_key == cfg.short_description_field
        if dry_run:
            log.info("[dry-run] would translate %s -> %s", field_key, code)
            result.add(FieldResult(code, field_key, "translated", detail="dry-run"))
            return

        assert self.translator is not None, "translator required outside dry-run"
        request = TranslationRequest(
            text=source_text,
            target_language=languages.language_name(code),
            source_language=languages.language_name(cfg.source_language),
            field_key=field_key,
            is_short_description=is_short,
            char_limit=cfg.short_description_max_chars if is_short else None,
            do_not_translate=list(cfg.do_not_translate),
            glossary=dict(cfg.glossary),
            style=cfg.style,
        )

        try:
            translated = self.translator.translate(request)
        except Exception as exc:  # noqa: BLE001 - report and continue other fields
            log.error("Failed to translate %s for %s: %s", field_key, code, exc)
            result.add(FieldResult(code, field_key, "error", detail=str(exc)))
            return

        detail = ""
        if is_short and len(translated) > cfg.short_description_max_chars:
            detail = (
                f"exceeds {cfg.short_description_max_chars} char limit "
                f"({len(translated)}); Steam may truncate it"
            )
            log.warning("Short description for %s %s.", code, detail)

        target_fields[field_key] = translated
        log.info("Translated %s -> %s (%d chars)", field_key, code, len(translated))
        result.add(
            FieldResult(code, field_key, "translated", detail=detail, chars=len(translated))
        )
