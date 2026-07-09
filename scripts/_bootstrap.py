"""Shared path bootstrap for standalone scripts."""
from __future__ import annotations

import pathlib
import sys


def ensure_paths() -> None:
    root = pathlib.Path(__file__).resolve().parent.parent
    for path in (str(root), str(root / "src")):
        if path not in sys.path:
            sys.path.insert(0, path)