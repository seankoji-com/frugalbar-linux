"""Homebrew launcher: do not import modules from the caller's working directory."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from frugalbar_linux.__main__ import main

sys.exit(main())
