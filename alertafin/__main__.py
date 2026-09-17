"""Permite `python -m alertafin` como alias del entry point `alertafin`."""

import sys

from alertafin.cli import main

if __name__ == "__main__":
    sys.exit(main())
