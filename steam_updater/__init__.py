"""Steam store page multi-language updater.

Translate a Steam store page's written description and short description into
many languages with Claude, then re-import the result through Steamworks'
localization JSON workflow.

Steam does not expose a public write API for store page descriptions, so this
tool operates on the multilingual JSON that Steamworks lets you export and
re-import from the partner site (Edit Store Page -> ... -> Export/Import).
"""

__version__ = "0.1.0"
