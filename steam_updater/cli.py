"""Command-line interface for the Steam page updater.

Workflow:
  1. In Steamworks, open Edit Store Page, export the localization as JSON with
     all languages selected.
  2. Run ``steam-updater translate`` to fill in the target languages.
  3. Import the produced JSON back into Steamworks and publish.
"""

from __future__ import annotations

import argparse
import logging
import sys

from steam_updater import __version__, languages
from steam_updater.config import Config, ConfigError
from steam_updater.pipeline import TranslationPipeline
from steam_updater.steam_json import DEFAULT_FIELDS, StoreListing, SteamJsonError

log = logging.getLogger("steam_updater")


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )


def _build_config(args: argparse.Namespace) -> Config:
    if args.config:
        config = Config.load(args.config)
    elif args.languages:
        config = Config(target_languages=[])  # placeholder, filled below
    else:
        raise ConfigError(
            "Provide a --config file or one or more --languages to translate into."
        )

    # CLI overrides take precedence over the config file.
    if args.languages:
        config.target_languages = [
            languages.normalize(c)
            for c in args.languages
            if languages.normalize(c) != config.source_language
        ]
    if args.source_language:
        config.source_language = languages.normalize(args.source_language)
    if args.fields:
        config.fields = list(args.fields)
    if args.model:
        config.model = args.model

    if not config.target_languages:
        raise ConfigError("No target languages to translate into.")
    return config


def _cmd_translate(args: argparse.Namespace) -> int:
    config = _build_config(args)
    listing = StoreListing.load(args.input)

    unknown = [c for c in config.target_languages if not languages.is_supported(c)]
    if unknown:
        log.warning(
            "These target codes are not in the known Steam language list and "
            "will be translated with a best-effort name: %s",
            ", ".join(unknown),
        )

    translator = None
    if not args.dry_run:
        from steam_updater.translator.claude import ClaudeTranslator

        translator = ClaudeTranslator(model=config.model, max_tokens=config.max_tokens)

    pipeline = TranslationPipeline(config, translator)
    result = pipeline.run(listing, overwrite=args.overwrite, dry_run=args.dry_run)

    log.info("Done: %s", result.summary())
    for err in result.errors:
        log.error("  %s/%s: %s", err.language, err.field_key, err.detail)

    if args.dry_run:
        log.info("Dry run: no file written. Would update %d field(s).", result.translated)
        return 1 if result.errors else 0

    listing.dump(args.output)
    log.info("Wrote %s — import this back into Steamworks and publish.", args.output)
    return 1 if result.errors else 0


def _cmd_list_languages(_: argparse.Namespace) -> int:
    width = max(len(c) for c in languages.STEAM_LANGUAGES)
    for code, name in languages.STEAM_LANGUAGES.items():
        print(f"{code.ljust(width)}  {name}")
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    listing = StoreListing.load(args.input)
    print(f"itemid: {listing.itemid or '(none)'}")
    print(f"languages: {len(listing.languages)}")
    for code in sorted(listing.languages):
        fields = listing.available_fields(code)
        print(f"  {code}: {len(fields)} field(s)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="steam-updater",
        description=(
            "Translate a Steam store page's description and short description "
            "into many languages via Claude, using Steamworks' localization "
            "JSON export/import workflow."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_tr = sub.add_parser("translate", help="Translate an exported localization JSON.")
    p_tr.add_argument("-i", "--input", required=True, help="Exported Steam localization JSON.")
    p_tr.add_argument("-o", "--output", default="localization.translated.json",
                      help="Where to write the import-ready JSON.")
    p_tr.add_argument("-c", "--config", help="YAML config file.")
    p_tr.add_argument("-l", "--languages", nargs="+", metavar="CODE",
                      help="Steam language codes to translate into (overrides config).")
    p_tr.add_argument("--source-language", help="Source language code (default: english).")
    p_tr.add_argument("--fields", nargs="+", metavar="KEY",
                      help=f"Field keys to translate (default: {' '.join(DEFAULT_FIELDS)}).")
    p_tr.add_argument("--model", help="Anthropic model id (overrides config).")
    p_tr.add_argument("--overwrite", action="store_true",
                      help="Re-translate fields even if a translation already exists.")
    p_tr.add_argument("--dry-run", action="store_true",
                      help="Report what would change without calling the API.")
    p_tr.set_defaults(func=_cmd_translate)

    p_val = sub.add_parser("validate", help="Inspect an exported localization JSON.")
    p_val.add_argument("-i", "--input", required=True, help="Exported Steam localization JSON.")
    p_val.set_defaults(func=_cmd_validate)

    p_ll = sub.add_parser("list-languages", help="List supported Steam language codes.")
    p_ll.set_defaults(func=_cmd_list_languages)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(getattr(args, "verbose", False))
    try:
        return args.func(args)
    except (ConfigError, SteamJsonError, FileNotFoundError, ValueError) as exc:
        log.error("%s", exc)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
