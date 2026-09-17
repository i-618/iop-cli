"""Enables `python -m iop`."""
import sys

from iop.cli import main

if __name__ == "__main__":
    sys.exit(main())
