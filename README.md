# steam-updater

**Optimize** a Steam store page's written description and short description
with Claude (SSO — Steam Store Optimization), **embed your GIF/MP4 feature
showcases**, **translate** the result into many languages, and push it to
Steam through Steamworks' localization **JSON export/import** workflow.

```
Steamworks ──export──▶ optimize ──review──▶ translate ──▶ import + publish
 (Edit Store Page)    (Claude writes       (Claude, all      (Steamworks)
                       SSO copy + embeds)   target langs)
```

## Why JSON export/import (and not a direct API)

Steam has **no public write API for store page descriptions.** The store page
text is edited on the Steamworks partner site, and Valve's own partner docs and
third-party localization integrations confirm there is no automatic API for it.

What Steam *does* support is a localization round-trip: on **Edit Store Page**
you can **export** the page's text for all languages as a single JSON file and
**import** an updated version of that file. This tool sits in the middle of that
round-trip:

```
Steamworks ──export JSON──▶  steam-updater  ──translated JSON──▶  Steamworks
 (Edit Store Page)         (Claude translates)                  (import + publish)
```

This is the reliable, officially-supported path: no scraping, no storing your
Steam credentials, and you stay in control of the final publish step.

## How it works

1. The export JSON is keyed by Steam language code, with each language holding
   field keys such as `app[content][about]` (the full description) and
   `app[content][short_description]`:

   ```json
   {
     "itemid": "1234567",
     "languages": {
       "english": {
         "app[content][about]": "[h1]Halcyon Drift[/h1] ...",
         "app[content][short_description]": "A brutal space-survival roguelike..."
       }
     }
   }
   ```

2. For every target language you list, the tool asks Claude to translate the
   source language's fields, then writes a new JSON with those languages filled
   in. Existing top-level keys, the `itemid`, and untouched languages/fields are
   preserved verbatim so the re-import is a clean round-trip.

3. Claude is instructed to **preserve Steam BBCode** (`[h1]`, `[b]`, `[list]`,
   `[url=...]`, …), **keep proper nouns** (game title, character names)
   untranslated, honour a **glossary**, and respect the short description's
   **~300-character** budget.

## Install

```bash
git clone <this repo> && cd steam-updater
pip install -e .
# or, without installing the console script:
pip install -r requirements.txt
```

Set your Anthropic API key (the SDK reads it from the environment):

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

## Usage

### 1. Export from Steamworks

On your app's **Edit Store Page**, use the localization export and choose the
**JSON** format with **all languages** selected. Save it as e.g. `export.json`.

### 2. Optimize (optional but recommended)

Scaffold the resources folder once and fill it in:

```bash
steam-updater init-resources          # creates resources/
```

- **`resources/game.md`** — game context: pitch, genre keywords, features,
  target audience, JTBD analysis, tone. The optimizer only uses what's written
  here; it won't invent features.
- **`resources/examples/`** — store descriptions from comparable games (one
  file each). The optimizer mimics their *structure and style*, never their
  wording.
- **`resources/assets.yaml`** — your GIF/MP4 showcase manifest (see
  [Media assets](#media-assets-gifs--videos) below).

Then produce the optimized source-language description:

```bash
steam-updater optimize -i export.json -o export.optimized.json
```

This writes the optimized description + short description into the source
language of a copy of the export, prints them for review along with an **upload
checklist** of asset files, and flags problems (invented asset references,
over-budget short description). **Review and edit the result** — then translate
it. Use `--dry-run` to inspect the assembled prompt without an API call.

### 3. Translate

With a config file (recommended — see [`config.example.yaml`](config.example.yaml)):

```bash
steam-updater translate -i export.optimized.json -o out.json -c config.example.yaml
```

Or quickly, with languages on the command line:

```bash
steam-updater translate -i export.optimized.json -o out.json -l french japanese schinese brazilian
```

Useful flags:

| Flag | Meaning |
|------|---------|
| `-l, --languages` | Steam language codes to translate into (overrides config). |
| `--source-language` | Language to translate from (default `english`). |
| `--fields` | Field keys to translate (default: about + short description). |
| `--model` | Anthropic model id (default `claude-opus-4-8`; e.g. `claude-sonnet-4-6` for lower cost). |
| `--overwrite` | Re-translate languages that already have text (otherwise kept). |
| `--dry-run` | Show what would be translated without calling the API. |
| `-v, --verbose` | Verbose logging. |

By default, languages/fields that **already have** a translation are left
untouched — so re-running only fills in what's missing. Use `--overwrite` to
regenerate everything.

### 4. Import back into Steamworks

Import `out.json` on the same Edit Store Page screen, review the diff in the
preview, and **publish**. Always eyeball the result — machine translation of
marketing copy benefits from a native-speaker pass before going live.

### One-shot pipeline

When you don't need the review pause between optimize and translate:

```bash
steam-updater pipeline -i export.json -o out.json -c config.yaml
```

Because the source text changes, the pipeline **overwrites** existing target
translations (stale translations of the old description would be wrong). Add
`--skip-optimize` to translate only.

### Other commands

```bash
steam-updater validate -i export.json     # inspect an export (languages, field counts)
steam-updater list-languages              # list supported Steam language codes
steam-updater init-resources              # scaffold the optimizer resources folder
```

## Media assets (GIFs & videos)

Steam has **no upload API for description assets** — files must be uploaded
once by hand in **Edit Store Page → Description Assets** (PNG/JPG/GIF/WEBP and,
since Steam's 2025 update, MP4/WEBM; animated assets max 12 s; ~1170 px wide
recommended; keep the page under ~15 MB total).

The smart part is *referencing*: uploaded assets are addressed with a stable,
language-independent macro that Steam resolves per viewer:

```
[img]{STEAM_APP_IMAGE}/extras/base_building.gif[/img]
[video mp4={STEAM_APP_IMAGE}/extras/combat.mp4 poster={STEAM_APP_IMAGE}/extras/combat_poster.png][/video]
```

So instead of dragging files into the editor every time you rewrite the
description, list them once in `resources/assets.yaml`:

```yaml
assets:
  - file: combat.mp4           # exact filename as uploaded
    type: video                # video | gif | image
    poster: combat_poster.png  # optional, videos only
    shows: "Fast-paced ship combat with modular weapons"
  - file: base_building.gif
    type: gif
    shows: "Drag-and-drop ship building"
```

The optimizer embeds each asset next to the feature copy it showcases, a
post-check verifies no asset name was invented, and the printed **upload
checklist** tells you exactly which files must exist in Description Assets.
Translations keep the macros byte-for-byte, so every language shows the same
media without re-uploading anything.

## Configuration

See [`config.example.yaml`](config.example.yaml). Key options:

- `source_language` / `target_languages` — what to translate from and into.
- `fields` — which `app[...]` keys to translate.
- `model` / `max_tokens` — which Claude model to use and its output ceiling.
- `resources_dir` / `optimizer_model` / `optimizer_max_tokens` — optimizer
  inputs folder and model (empty `optimizer_model` falls back to `model`).
- `do_not_translate` — proper nouns (game name, characters) kept verbatim.
- `glossary` — force specific renderings of specific terms.
- `style` — tone/voice guidance applied to every translation.
- `short_description_max_chars` — budget warned-on for the short description (300).

## Project layout

```
steam_updater/
  cli.py            # argparse CLI (optimize / translate / pipeline / ...)
  config.py         # YAML config model
  languages.py      # Steam language code -> descriptive name table
  steam_json.py     # parse/serialize the Steam localization export
  pipeline.py       # orchestration: translate configured fields per language
  resources.py      # optimizer inputs: game.md, examples/, assets.yaml
  optimizer.py      # SSO description optimizer + asset-reference validation
  translator/
    base.py         # Translator interface + TranslationRequest
    claude.py       # Anthropic Claude backend
resources/          # your game context, JTBD, examples, asset manifest
```

The `Translator` interface (`translator/base.py`) is deliberately small, so a
DeepL/Google/other backend can be dropped in later without touching the
pipeline.

## Development

```bash
pip install -e ".[dev]"
pytest
```

The test suite runs offline — translation tests use an injected fake client, so
no API key is needed.

## Limitations & notes

- **No direct Steam API.** The import/publish step is manual by design; this
  tool produces the file, you click publish. Likewise, description assets
  (GIFs/videos) must be uploaded once by hand — Steam offers no upload API —
  but the tool manages all references to them from then on.
- **Ground truth lives in `resources/game.md`.** The optimizer is instructed
  not to invent features or claims, so keep the game context accurate and
  current.
- **Review translations.** Especially short descriptions, which Steam truncates
  around 300 characters — the tool warns when a translation exceeds the budget.
- **Images with text** in your store page must be localized separately in
  Steamworks; this tool only handles the written description fields.
