# -*- coding: utf-8 -*-
"""`python -m hato` -- the same entry point as the `hato` console script."""
import sys

from hato.cli import main

if __name__ == "__main__":
    sys.exit(main())
