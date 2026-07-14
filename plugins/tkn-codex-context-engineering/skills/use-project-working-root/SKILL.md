---
name: use-project-working-root
description: Resolve and use the right runtime working root for a Codex Project before creating Python virtual environments, Node.js package folders, dependency caches, or large runtime work files. Use when the user asks to use .codex-working, set up a project working root, create or use .venv, install Python or Node.js dependencies, create node_modules, run package-manager setup, or decide whether runtime files belong in the Codex project folder or in the private per-project working root.
---

# Use Project Working Root

Use this skill before creating durable runtime files for Python, Node.js, package managers, or large generated working data.

The goal is to avoid putting runtime trees into synced document workspaces while still allowing normal runtime layout inside real software repositories.

## Core Decision

First decide whether runtime files should live in the Codex project folder or in the private Codex working root.

Use the Codex project folder itself only when all of these are true:

1. The project root is a Git repository.
2. The project folder is not under OneDrive, SharePoint, Dropbox, Google Drive, or an Obsidian Vault.
3. The user created the folder for coding, or the existing files clearly show it is a software repository.
4. `.gitignore` already ignores runtime and cache folders such as `node_modules`, `.venv`, and tool caches, or the task includes adding those ignores before installing dependencies.
5. Project-local environment definitions exist, such as `package.json`, `pyproject.toml`, `requirements.txt`, lockfiles, or equivalent setup files.
6. Before adding or updating dependencies, inspect and follow the existing package manager or Python environment policy.

If any condition is not met, use the private Codex working root for durable runtime work.

User intent wins over heuristics. If the user explicitly asks to use the project folder or the private working root, follow that instruction unless it creates an obvious sync, privacy, or repository hygiene risk.

## Classification Checks

Before installing dependencies, check the current workspace narrowly:

- Use Git metadata to find the project root when possible.
- Check the current path and ancestors for sync-folder signals such as `OneDrive`, `SharePoint`, `Dropbox`, `Google Drive`, or equivalent provider folders.
- Check the current path and ancestors for an Obsidian Vault marker such as `.obsidian`.
- Inspect `.gitignore` before creating runtime files.
- Inspect environment definition files before choosing a package manager or Python setup.

Do not perform broad recursive scans of home folders or sync roots just to classify the workspace.

## Private Working Root

The default private working root is:

```text
%USERPROFILE%\.codex-working\projects\<projectId>\
```

Use the actual registered `projectId` from `.tkn/codex-context.yaml`.

This root is available only after the project has been registered with `init-project-context` and the marker resolves through the private registry:

```text
~/.tkn/codex-context/state/index.jsonl
```

If registration is missing or the registry cannot resolve the current workspace, do not create a durable private runtime folder. Guide the user to run `init-project-context` first. For throwaway scratch only, use the OS temporary directory.

Do not infer `projectId` from the folder name alone.

## Working Root Layout

Treat the working root as a possible future private Git repository. Prefer normal repository layout at the root rather than nested runtime folders.

Python projects use:

```text
<working-root>\
  .venv\
  pyproject.toml or requirements.txt
  scripts\ or src\
  .gitignore
```

Node.js projects use:

```text
<working-root>\
  package.json
  package-lock.json, pnpm-lock.yaml, or yarn.lock
  node_modules\
  scripts\ or src\
  .gitignore
```

Do not create generic `cache`, `tmp`, `work`, `env\python`, or `env\node` folders by default.

Language and tool caches that naturally belong to the runtime may live in the working root when they improve future runs and are ignored by Git. Examples include `__pycache__`, `.pytest_cache`, `.ruff_cache`, `.mypy_cache`, `.cache`, package-manager stores, and build caches.

## Project AGENTS.md Reminder

When this skill chooses the private Codex working root, add or update the Codex project folder's `AGENTS.md` with a short reminder unless the user explicitly declines or the task is read-only. This is the persistence mechanism that makes future Codex runs use the same working-root policy after the skill has been invoked once.

Keep the text generic and safe for committed repositories; do not write private absolute paths.

Suggested block:

```markdown
## Codex working root

This project uses a private Codex working root for runtime files.

Do not create `.venv`, `node_modules`, package caches, or large generated working files in this project folder. When Python or Node.js runtime files are needed, use the `use-project-working-root` skill first and work under the resolved private working root.
```

If `AGENTS.md` already contains an equivalent rule, leave it alone. If the file exists, append the block in the closest appropriate section. If the file does not exist, create a short `AGENTS.md` with only the reminder.

Do not add this reminder when the project folder itself qualifies as the runtime root under the Core Decision criteria.

## Python Practice

Before creating or using Python runtime files:

1. Inspect existing files: `pyproject.toml`, `requirements.txt`, `uv.lock`, `poetry.lock`, setup files, README setup instructions, and existing `.venv` policy.
2. Prefer `uv` when available.
3. If `uv` is available, create the environment at the runtime root:

   ```text
   uv venv .venv
   ```

4. Install dependencies through the selected project definition:
   - `uv pip install -r requirements.txt` when `requirements.txt` is the source.
   - `uv pip install -e .` when `pyproject.toml` defines the package and editable install is appropriate.
   - Follow existing project commands when README or scripts define them.
5. If `uv` is unavailable, use the active Python:

   ```text
   python -m venv .venv
   .venv\Scripts\python -m pip install -r requirements.txt
   ```

6. Do not install packages into project-local `.local`, `pydeps`, or ad hoc dependency folders.
7. Ignore normal Python runtime artifacts in `.gitignore`.

## Node.js Practice

Before creating or using Node.js runtime files:

1. Inspect existing files: `package.json`, `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `.npmrc`, `.yarnrc.yml`, README setup instructions, and `packageManager`.
2. Follow the existing package manager:
   - `pnpm` when `pnpm-lock.yaml` or `packageManager` says pnpm.
   - `yarn` when `yarn.lock` or `packageManager` says yarn.
   - `npm` when `package-lock.json` exists or no other policy is present.
3. Put `node_modules` at the selected runtime root.
4. Do not run package install commands in a synced document workspace.
5. Ignore normal Node.js runtime artifacts in `.gitignore`.

## Gitignore Baseline

When creating or refreshing a working root `.gitignore`, include entries relevant to the selected language and tools. Keep lockfiles tracked.

Typical Python entries:

```gitignore
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
.mypy_cache/
.coverage
htmlcov/
build/
dist/
.cache/
```

Typical Node.js entries:

```gitignore
node_modules/
.npm/
.pnpm-store/
.yarn/
dist/
build/
.cache/
```

Use the repository's existing `.gitignore` style when one exists.

## Safety

- Keep private absolute paths out of files likely to be committed.
- Do not silently fall back to a synced project folder when the private working root is not writable.
- Ask for the narrowest filesystem permission needed when the selected working root is outside the current sandbox.
- Keep final user-facing outputs in the location requested by the user; the working root is for runtime and intermediate work, not the final content root.
- If a working root grows into real software, it may be initialized as a private Git repository later.
