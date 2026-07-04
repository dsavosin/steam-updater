"""Load optimizer resources: game context, example descriptions, asset manifest.

The ``resources/`` folder gives the description optimizer everything it needs
to write good Steam store copy:

    resources/
      game.md            # game context, target audience, JTBD, tone
      assets.yaml        # media manifest (gifs / mp4s uploaded to Steamworks)
      examples/          # store descriptions from other games to mimic
        some-game.md

Only ``game.md`` is required; examples and assets are optional.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("steam_updater")

GAME_CONTEXT_FILE = "game.md"
ASSETS_FILE = "assets.yaml"
EXAMPLES_DIR = "examples"
EXAMPLE_SUFFIXES = {".md", ".txt"}

ASSET_TYPES = {"gif", "image", "video"}


class ResourceError(ValueError):
    """Raised when the resources folder is missing or malformed."""


@dataclass
class Asset:
    """One media asset uploaded to Steamworks -> Description Assets.

    Attributes:
        file: Exact filename as uploaded (Steam serves it under
            ``{STEAM_APP_IMAGE}/extras/<file>``).
        type: One of ``gif``, ``image``, ``video``.
        shows: What game feature the asset showcases — the optimizer uses this
            to place the asset next to the matching feature copy.
        poster: Optional poster image filename (videos only).
    """

    file: str
    type: str
    shows: str
    poster: str | None = None

    def bbcode(self) -> str:
        """Return the BBCode snippet that embeds this asset in a description."""
        if self.type == "video":
            poster = (
                f" poster={{STEAM_APP_IMAGE}}/extras/{self.poster}" if self.poster else ""
            )
            return f"[video mp4={{STEAM_APP_IMAGE}}/extras/{self.file}{poster}][/video]"
        return f"[img]{{STEAM_APP_IMAGE}}/extras/{self.file}[/img]"


@dataclass
class OptimizerResources:
    """Everything the optimizer needs, loaded from the resources folder."""

    game_context: str
    examples: list[str] = field(default_factory=list)
    assets: list[Asset] = field(default_factory=list)

    @classmethod
    def load(cls, directory: str | Path) -> "OptimizerResources":
        root = Path(directory)
        if not root.is_dir():
            raise ResourceError(
                f"Resources folder not found: {root}. "
                "Create it with: steam-updater init-resources"
            )

        game_path = root / GAME_CONTEXT_FILE
        if not game_path.is_file():
            raise ResourceError(
                f"{game_path} is required — it holds the game context, target "
                "audience, and JTBD analysis the optimizer works from. "
                "Scaffold a template with: steam-updater init-resources"
            )
        game_context = game_path.read_text(encoding="utf-8").strip()
        if not game_context:
            raise ResourceError(f"{game_path} is empty — fill in the game context.")

        examples = cls._load_examples(root / EXAMPLES_DIR)
        assets = cls._load_assets(root / ASSETS_FILE)
        return cls(game_context=game_context, examples=examples, assets=assets)

    # -- helpers ---------------------------------------------------------
    @staticmethod
    def _load_examples(directory: Path) -> list[str]:
        if not directory.is_dir():
            log.warning(
                "No examples folder at %s — the optimizer writes better copy "
                "when given store descriptions from comparable games.",
                directory,
            )
            return []
        examples: list[str] = []
        for path in sorted(directory.iterdir()):
            if path.suffix.lower() not in EXAMPLE_SUFFIXES:
                continue
            if path.name.lower() == "readme.md":
                continue
            text = path.read_text(encoding="utf-8").strip()
            if text:
                examples.append(text)
        if not examples:
            log.warning("No example descriptions found in %s.", directory)
        return examples

    @staticmethod
    def _load_assets(path: Path) -> list[Asset]:
        if not path.is_file():
            log.warning(
                "No asset manifest at %s — the optimized description will not "
                "embed gifs/videos.",
                path,
            )
            return []

        try:
            import yaml
        except ImportError as exc:  # pragma: no cover - depends on env
            raise RuntimeError(
                "PyYAML is required to read the asset manifest. "
                "Install it with: pip install pyyaml"
            ) from exc

        data: Any = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        entries = data.get("assets") if isinstance(data, dict) else None
        if entries is None:
            raise ResourceError(f"{path} must contain a top-level 'assets:' list.")
        if not isinstance(entries, list):
            raise ResourceError(f"'assets' in {path} must be a list.")

        assets: list[Asset] = []
        seen: set[str] = set()
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise ResourceError(f"{path}: assets[{i}] must be a mapping.")
            missing = {"file", "type", "shows"} - set(entry)
            if missing:
                raise ResourceError(
                    f"{path}: assets[{i}] is missing {', '.join(sorted(missing))}."
                )
            asset = Asset(
                file=str(entry["file"]).strip(),
                type=str(entry["type"]).strip().lower(),
                shows=str(entry["shows"]).strip(),
                poster=(str(entry["poster"]).strip() if entry.get("poster") else None),
            )
            if asset.type not in ASSET_TYPES:
                raise ResourceError(
                    f"{path}: assets[{i}] has unknown type '{asset.type}'. "
                    f"Allowed: {', '.join(sorted(ASSET_TYPES))}."
                )
            if asset.poster and asset.type != "video":
                raise ResourceError(
                    f"{path}: assets[{i}] ('{asset.file}') sets a poster but is "
                    f"a {asset.type}; posters only apply to videos."
                )
            if asset.file in seen:
                raise ResourceError(f"{path}: duplicate asset file '{asset.file}'.")
            seen.add(asset.file)
            assets.append(asset)
        return assets

    def upload_checklist(self) -> list[str]:
        """Filenames that must exist in Steamworks -> Description Assets."""
        files: list[str] = []
        for asset in self.assets:
            files.append(asset.file)
            if asset.poster:
                files.append(asset.poster)
        return files


# -- scaffolding ---------------------------------------------------------

GAME_TEMPLATE = """\
# Game context

<!-- Fill in every section. The optimizer works only from what is written
     here — it will not invent features or claims. -->

## Pitch

One or two sentences: what is the game and what is its core fantasy?

## Genre and keywords

Genre(s) and the search terms players actually type into Steam and Google
(e.g. "space survival roguelike", "base building", "crew management").

## Features

The real, shipped (or firmly planned) features, one per line. Be concrete.

## Target audience

Who buys this game? What other games do they play?

## JTBD analysis

What "job" does the player hire this game for? What feeling or experience
are they buying? (e.g. "I want to feel like a scrappy captain barely holding
a ship together.")

## Tone and voice

How should the store copy sound? (e.g. punchy and confident, dry humour,
grimdark...)
"""

ASSETS_TEMPLATE = """\
# Media assets for the store description.
#
# Each entry describes a gif/image/video you have uploaded (or will upload)
# in Steamworks -> Edit Store Page -> Description Assets. The optimizer
# embeds them next to the feature copy they showcase using the
# {STEAM_APP_IMAGE}/extras/<file> macro, so the description works in every
# language without re-uploading anything.
#
# Steam constraints: animated assets max 12 seconds; ~1170px wide recommended;
# keep each image under 5MB and the whole page under ~15MB.
#
# assets:
#   - file: combat_loop.mp4      # exact filename as uploaded
#     type: video                # video | gif | image
#     poster: combat_poster.png  # optional, videos only
#     shows: "Fast-paced ship combat with modular weapons"
#   - file: base_building.gif
#     type: gif
#     shows: "Drag-and-drop ship building"

assets: []
"""

EXAMPLES_README = """\
# Example descriptions

Drop store descriptions from comparable games here, one file per game
(`.md` or `.txt`, this README is ignored). Copy the text (or raw BBCode)
from their Steam pages.

The optimizer mimics their *structure and style* — never their wording or
features. Two or three strong examples from games your audience already
plays work best.
"""


def scaffold(directory: str | Path, *, force: bool = False) -> list[Path]:
    """Create the resources folder from templates; returns files written.

    Existing files are left untouched unless ``force`` is set.
    """
    root = Path(directory)
    examples = root / EXAMPLES_DIR
    examples.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for path, content in (
        (root / GAME_CONTEXT_FILE, GAME_TEMPLATE),
        (root / ASSETS_FILE, ASSETS_TEMPLATE),
        (examples / "README.md", EXAMPLES_README),
    ):
        if path.exists() and not force:
            log.info("Keeping existing %s", path)
            continue
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written
