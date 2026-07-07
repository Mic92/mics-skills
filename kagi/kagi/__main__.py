"""Allow `python -m kagi ...` to run the umbrella CLI."""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
