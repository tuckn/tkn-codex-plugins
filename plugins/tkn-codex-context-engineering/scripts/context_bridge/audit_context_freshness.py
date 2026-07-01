#!/usr/bin/env python3
"""Wrapper for auditing Codex context freshness."""

from context_bridge import main


if __name__ == "__main__":
    raise SystemExit(main(["audit-freshness", *(__import__("sys").argv[1:])]))
