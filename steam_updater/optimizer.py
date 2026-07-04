"""SSO (Steam Store Optimization) description optimizer.

Given the game context, JTBD/audience analysis, example descriptions from
comparable games, and a manifest of media assets, ask Claude to write an
optimized store description + short description in the source language. The
result then feeds the existing translation pipeline.

Media assets are embedded via Steam's ``{STEAM_APP_IMAGE}/extras/<file>``
macro, which Steam resolves to the files uploaded under Store Page ->
Description Assets. The macro is language-independent, so translations carry
the embeds through unchanged.
"""

from __future__ import annotations

import json
import re
import textwrap
from dataclasses import dataclass, field

from steam_updater.resources import OptimizerResources
from steam_updater.translator.claude import DEFAULT_MODEL

DEFAULT_MAX_TOKENS = 16000
SHORT_DESCRIPTION_MAX_CHARS = 300

# Matches {STEAM_APP_IMAGE}/extras/<filename> inside [img] bodies and
# [video ...] attribute values; a filename ends at whitespace, a bracket
# (opening bracket of the closing tag, e.g. ...gif[/img]) or a quote.
_ASSET_REF_RE = re.compile(r"\{STEAM_APP_IMAGE\}/extras/([^\s\[\]\"']+)")

_SYSTEM_PROMPT = textwrap.dedent(
    """\
    You are a Steam store page copywriter and SSO (Steam Store Optimization)
    expert. You write store descriptions that convert visits into wishlists
    and sales.

    Principles:
    - Hook first: the opening line must sell the core fantasy of the game in
      one sentence. No throat-clearing, no "Welcome to...".
    - Front-load searchable genre keywords (the terms players actually type
      into Steam and Google) naturally into the first paragraph and the short
      description.
    - Structure for scanning: short paragraphs, [h2] section headers,
      [list][*]...[/list] feature bullets. No walls of text.
    - Write feature bullets as player fantasies and jobs-to-be-done ("Build a
      ship that's truly yours"), not as spec sheets ("200+ modules").
    - Place each media asset directly after the copy describing the feature it
      showcases, using the exact BBCode snippet provided for it. Use each
      asset at most once. Never invent asset filenames.
    - End with a clear wishlist call to action.
    - The short description must fit the character budget you are given, stand
      alone (it shows in search results and the top of the page), and contain
      the strongest hook plus primary genre keywords. Plain text only — no
      BBCode in the short description.
    - Use Steam BBCode only ([h1] [h2] [b] [i] [list] [*] [img] [video]
      [url=...]). No HTML, no markdown.
    - Match the structural patterns of the example descriptions you are given,
      but never copy their wording or their features.
    - Ground every claim in the provided game context. Do not invent features,
      accolades, review quotes, or numbers.
    """
)


class OptimizerError(RuntimeError):
    """Raised when the optimizer response cannot be used."""


@dataclass
class OptimizedDescription:
    """The optimizer's output for the source language."""

    about: str
    short_description: str


@dataclass
class ValidationReport:
    """Post-generation checks on an optimized description."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    upload_checklist: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_output(
    optimized: OptimizedDescription,
    resources: OptimizerResources,
    *,
    short_max_chars: int = SHORT_DESCRIPTION_MAX_CHARS,
) -> ValidationReport:
    """Check asset references, unused assets, and the short-description budget.

    Only files referenced by the description (plus their posters) land on the
    upload checklist — those are the ones that must exist in Steamworks ->
    Description Assets for the page to render.
    """
    report = ValidationReport()

    known: dict[str, object] = {}
    for asset in resources.assets:
        known[asset.file] = asset
        if asset.poster:
            known[asset.poster] = asset

    referenced = set(_ASSET_REF_RE.findall(optimized.about))

    for name in sorted(referenced):
        if name not in known:
            report.errors.append(
                f"Description references '{name}', which is not in the asset "
                "manifest — the model invented it. Remove the reference or add "
                "the asset to resources/assets.yaml."
            )

    for asset in resources.assets:
        if asset.file not in referenced:
            report.warnings.append(
                f"Asset '{asset.file}' ({asset.shows}) was not used in the "
                "description."
            )
        else:
            report.upload_checklist.append(asset.file)
            if asset.poster:
                report.upload_checklist.append(asset.poster)

    if _ASSET_REF_RE.search(optimized.short_description):
        report.errors.append(
            "The short description embeds an asset; Steam renders it as plain "
            "text there."
        )

    if len(optimized.short_description) > short_max_chars:
        report.warnings.append(
            f"Short description is {len(optimized.short_description)} chars, "
            f"over the {short_max_chars}-char budget; Steam may truncate it."
        )

    return report


class DescriptionOptimizer:
    """Produce an SSO-optimized description with Claude."""

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        api_key: str | None = None,
        client: object | None = None,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        if client is not None:
            self._client = client
        else:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - depends on env
                raise RuntimeError(
                    "The 'anthropic' package is required for the optimizer. "
                    "Install it with: pip install anthropic"
                ) from exc
            self._client = (
                anthropic.Anthropic(api_key=api_key)
                if api_key
                else anthropic.Anthropic()
            )

    # -- prompt building ---------------------------------------------------
    @staticmethod
    def build_user_prompt(
        resources: OptimizerResources,
        *,
        current_about: str | None = None,
        current_short: str | None = None,
        language: str = "English",
        short_max_chars: int = SHORT_DESCRIPTION_MAX_CHARS,
    ) -> str:
        parts: list[str] = [
            f"Write an optimized Steam store description and short description "
            f"in {language}.",
            "## Game context, target audience, and JTBD analysis\n\n"
            + resources.game_context,
        ]

        if resources.assets:
            lines = []
            for asset in resources.assets:
                lines.append(
                    f"- {asset.file} ({asset.type}) — shows: {asset.shows}\n"
                    f"  Embed with exactly: {asset.bbcode()}"
                )
            parts.append(
                "## Available media assets\n\n"
                "Place each asset right after the copy for the feature it "
                "showcases. Use only these snippets, verbatim:\n\n"
                + "\n".join(lines)
            )
        else:
            parts.append(
                "## Available media assets\n\nNone. Do not embed any [img] or "
                "[video] tags."
            )

        for i, example in enumerate(resources.examples, start=1):
            parts.append(
                f"## Example description {i} (for structure and style only — "
                f"do not copy wording or features)\n\n{example}"
            )

        if current_about:
            parts.append(
                "## Current description (raw material — improve on it, keep "
                "what works)\n\n" + current_about
            )
        if current_short:
            parts.append("## Current short description\n\n" + current_short)

        parts.append(
            f"The short description must be at most {short_max_chars} "
            "characters of plain text."
        )
        return "\n\n".join(parts)

    # -- generation ----------------------------------------------------------
    def optimize(
        self,
        resources: OptimizerResources,
        *,
        current_about: str | None = None,
        current_short: str | None = None,
        language: str = "English",
        short_max_chars: int = SHORT_DESCRIPTION_MAX_CHARS,
    ) -> OptimizedDescription:
        prompt = self.build_user_prompt(
            resources,
            current_about=current_about,
            current_short=current_short,
            language=language,
            short_max_chars=short_max_chars,
        )
        response = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=_SYSTEM_PROMPT,
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "about": {
                                "type": "string",
                                "description": "The full store description in Steam BBCode.",
                            },
                            "short_description": {
                                "type": "string",
                                "description": "Plain-text short description.",
                            },
                        },
                        "required": ["about", "short_description"],
                        "additionalProperties": False,
                    },
                }
            },
            messages=[{"role": "user", "content": prompt}],
        )
        return self._parse_response(response)

    @staticmethod
    def _parse_response(response: object) -> OptimizedDescription:
        text = "".join(
            block.text
            for block in getattr(response, "content", []) or []
            if getattr(block, "type", None) == "text"
        )
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise OptimizerError(
                f"Optimizer returned non-JSON output: {text[:200]!r}"
            ) from exc
        about = str(data.get("about", "")).strip()
        short = str(data.get("short_description", "")).strip()
        if not about or not short:
            raise OptimizerError(
                "Optimizer output is missing 'about' or 'short_description'."
            )
        return OptimizedDescription(about=about, short_description=short)
