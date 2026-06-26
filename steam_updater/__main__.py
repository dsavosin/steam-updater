"""Enable ``python -m steam_updater``."""

import sys

from steam_updater.cli import main

if __name__ == "__main__":
    sys.exit(main())
