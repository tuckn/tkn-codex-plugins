#!/usr/bin/env python3
"""Wrapper for initializing a project in the versioned Codex context store."""

from context_bridge import main


if __name__ == "__main__":
    raise SystemExit(main(["init-project", *(__import__("sys").argv[1:])]))
