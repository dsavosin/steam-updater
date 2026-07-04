"""Command-line interface for the Steam page updater.

Workflow:
  1. In Steamworks, open Edit Store Page, export the localization as JSON with
     all languages selected.
  2. Run ``steam-updater optimize`` to produce an SSO-optimized description in
     the source language. Review and edit the result.
  3. Run ``steam-updater translate`` to fill in the target languages.
  4. Import the produced JSON back into Steamworks and publish.

``steam-updater pipeline`` chains steps 2-3 for when no review pause is
needed; ``steam-updater init-resources`` scaffolds the resources folder the
optimizer reads (game context, JTBD, examples, asset manifest).
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


def _optimize_listing(
    listing: StoreListing,
    config: Config,
    resources_dir: str,
    *,
    dry_run: bool,
) -> int:
    """Optimize the source-language description in ``listing`` in place.

    Returns a process exit code (0 ok, 1 validation errors).
    """
    from steam_updater.optimizer import DescriptionOptimizer, validate_output
    from steam_updater.resources import OptimizerResources
    from steam_updater.steam_json import FIELD_ABOUT

    resources = OptimizerResources.load(resources_dir)
    src = config.source_language
    current_about = listing.source_text(src, FIELD_ABOUT)
    current_short = listing.source_text(src, config.short_description_field)

    log.info(
        "Optimizer context: %d chars of game context, %d example(s), %d asset(s).",
        len(resources.game_context),
        len(resources.examples),
        len(resources.assets),
    )

    if dry_run:
        prompt = DescriptionOptimizer.build_user_prompt(
            resources,
            current_about=current_about,
            current_short=current_short,
            language=languages.language_name(src),
            short_max_chars=config.short_description_max_chars,
        )
        log.info("[dry-run] assembled prompt is %d chars; no API call made.", len(prompt))
        print(prompt)
        return 0

    optimizer = DescriptionOptimizer(
        model=config.effective_optimizer_model,
        max_tokens=config.optimizer_max_tokens,
    )
    optimized = optimizer.optimize(
        resources,
        current_about=current_about,
        current_short=current_short,
        language=languages.language_name(src),
        short_max_chars=config.short_description_max_chars,
    )

    report = validate_output(
        optimized, resources, short_max_chars=config.short_description_max_chars
    )
    for warning in report.warnings:
        log.warning("%s", warning)
    for error in report.errors:
        log.error("%s", error)

    fields = listing.fields_for(src)
    fields[FIELD_ABOUT] = optimized.about
    fields[config.short_description_field] = optimized.short_description

    print("\n--- Optimized short description "
          f"({len(optimized.short_description)} chars) ---\n")
    print(optimized.short_description)
    print("\n--- Optimized description ---\n")
    print(optimized.about)

    if report.upload_checklist:
        print("\n--- Upload checklist ---")
        print("Make sure these files exist in Steamworks -> Edit Store Page -> "
              "Description Assets:")
        for name in report.upload_checklist:
            print(f"  [ ] {name}")

    return 0 if report.ok else 1


def _cmd_optimize(args: argparse.Namespace) -> int:
    # target_languages is irrelevant for optimize; the direct constructor
    # (unlike from_dict) accepts an empty list.
    config = Config.load(args.config) if args.config else Config(target_languages=[])
    if args.source_language:
        config.source_language = languages.normalize(args.source_language)
    if args.model:
        config.optimizer_model = args.model
    resources_dir = args.resources or config.resources_dir

    listing = StoreListing.load(args.input)
    code = _optimize_listing(listing, config, resources_dir, dry_run=args.dry_run)

    if not args.dry_run:
        listing.dump(args.output)
        log.info(
            "Wrote %s — review/edit the %s text, then run: "
            "steam-updater translate -i %s",
            args.output, config.source_language, args.output,
        )
    return code


def _cmd_pipeline(args: argparse.Namespace) -> int:
    config = _build_config(args)
    if args.model:
        config.optimizer_model = args.model
    resources_dir = args.resources or config.resources_dir

    listing = StoreListing.load(args.input)

    if args.skip_optimize or args.dry_run:
        log.info(
            "Skipping optimize stage (%s).",
            "--skip-optimize" if args.skip_optimize else "dry run",
        )
    else:
        code = _optimize_listing(listing, config, resources_dir, dry_run=False)
        if code != 0:
            log.error(
                "Optimizer validation failed; stopping before translation. "
                "Run 'steam-updater optimize' alone to review the output."
            )
            return code

    translator = None
    if not args.dry_run:
        from steam_updater.translator.claude import ClaudeTranslator

        translator = ClaudeTranslator(model=config.model, max_tokens=config.max_tokens)

    # The source text just changed, so stale target translations must go.
    pipeline = TranslationPipeline(config, translator)
    result = pipeline.run(listing, overwrite=True, dry_run=args.dry_run)

    log.info("Done: %s", result.summary())
    for err in result.errors:
        log.error("  %s/%s: %s", err.language, err.field_key, err.detail)

    if args.dry_run:
        log.info("Dry run: no file written.")
        return 1 if result.errors else 0

    listing.dump(args.output)
    log.info("Wrote %s — import this back into Steamworks and publish.", args.output)
    return 1 if result.errors else 0


def _cmd_init_resources(args: argparse.Namespace) -> int:
    from steam_updater.resources import scaffold

    written = scaffold(args.resources, force=args.force)
    if written:
        for path in written:
            log.info("Created %s", path)
        log.info(
            "Fill in game.md (context, audience, JTBD), drop example "
            "descriptions into examples/, and list your gifs/videos in "
            "assets.yaml."
        )
    else:
        log.info("All resource files already exist; nothing written.")
    return 0


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

    p_opt = sub.add_parser(
        "optimize",
        help="Write an SSO-optimized description into the source language of an export.",
    )
    p_opt.add_argument("-i", "--input", required=True, help="Exported Steam localization JSON.")
    p_opt.add_argument("-o", "--output", default="localization.optimized.json",
                       help="Where to write the optimized export JSON.")
    p_opt.add_argument("-c", "--config", help="YAML config file.")
    p_opt.add_argument("-r", "--resources",
                       help="Resources folder (default: 'resources' or config resources_dir).")
    p_opt.add_argument("--source-language", help="Source language code (default: english).")
    p_opt.add_argument("--model", help="Anthropic model id for the optimizer.")
    p_opt.add_argument("--dry-run", action="store_true",
                       help="Print the assembled prompt without calling the API.")
    p_opt.set_defaults(func=_cmd_optimize)

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

    p_pipe = sub.add_parser(
        "pipeline",
        help="Optimize then translate in one run (no review pause; targets are overwritten).",
    )
    p_pipe.add_argument("-i", "--input", required=True, help="Exported Steam localization JSON.")
    p_pipe.add_argument("-o", "--output", default="localization.translated.json",
                        help="Where to write the import-ready JSON.")
    p_pipe.add_argument("-c", "--config", help="YAML config file.")
    p_pipe.add_argument("-r", "--resources",
                        help="Resources folder (default: 'resources' or config resources_dir).")
    p_pipe.add_argument("-l", "--languages", nargs="+", metavar="CODE",
                        help="Steam language codes to translate into (overrides config).")
    p_pipe.add_argument("--source-language", help="Source language code (default: english).")
    p_pipe.add_argument("--fields", nargs="+", metavar="KEY",
                        help=f"Field keys to translate (default: {' '.join(DEFAULT_FIELDS)}).")
    p_pipe.add_argument("--model", help="Anthropic model id (overrides config for both stages).")
    p_pipe.add_argument("--skip-optimize", action="store_true",
                        help="Translate only; skip the optimizer stage.")
    p_pipe.add_argument("--dry-run", action="store_true",
                        help="Dry-run the translation stage (optimize is skipped too).")
    p_pipe.set_defaults(func=_cmd_pipeline)

    p_init = sub.add_parser(
        "init-resources",
        help="Scaffold the resources folder (game.md, assets.yaml, examples/).",
    )
    p_init.add_argument("-r", "--resources", default="resources",
                        help="Where to create the folder (default: resources).")
    p_init.add_argument("--force", action="store_true",
                        help="Overwrite existing template files.")
    p_init.set_defaults(func=_cmd_init_resources)

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
