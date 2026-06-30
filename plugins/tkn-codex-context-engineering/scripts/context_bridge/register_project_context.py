#!/usr/bin/env python3
"""Wrapper for registering a repository in user-global Codex context."""

from context_bridge import main


if __name__ == "__main__":
    raise SystemExit(main(["register-project", *(__import__("sys").argv[1:])]))

