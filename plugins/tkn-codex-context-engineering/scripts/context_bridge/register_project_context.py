#!/usr/bin/env python3
"""Deprecated wrapper for init_project_context.py; retained for v0.6 migration."""

from context_bridge import main


if __name__ == "__main__":
    raise SystemExit(main(["register-project", *(__import__("sys").argv[1:])]))
