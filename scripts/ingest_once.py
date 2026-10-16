#!/usr/bin/env python3
"""Convenience wrapper: python scripts/ingest_once.py"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ingest.pipeline import main

if __name__ == "__main__":
    main()
