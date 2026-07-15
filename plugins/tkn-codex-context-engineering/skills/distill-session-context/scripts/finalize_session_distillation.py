#!/usr/bin/env python3
"""Finalize distillation metadata for one reviewed session note."""

from __future__ import annotations

import sys


sys.dont_write_bytecode = True
from distill_session_context import finalize_main


if __name__ == "__main__":
    raise SystemExit(finalize_main())
