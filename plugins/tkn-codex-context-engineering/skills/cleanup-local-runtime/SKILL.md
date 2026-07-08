---
name: cleanup-local-runtime
description: Clean up legacy repository-local `.local` runtime and working folders by preserving reusable scripts and small durable inputs, recreating Python `.venv` or Node.js `node_modules` from dependency definitions, deleting temporary caches and generated intermediates, and removing `.local` after validation. Use when the user asks to remove `.local`, migrate `.local/pydeps`, replace ad hoc dependency folders with `.venv` or `node_modules`, or classify old working artifacts into scripts, data, runtime dependencies, final outputs, and disposable temporary files.
---

# Cleanup Local Runtime

Use this skill when a project has accumulated legacy `.local` working files and the user wants to remove or normalize them.

The goal is to preserve reusable project knowledge, recreate runtime dependencies through normal package managers, and delete disposable working artifacts without turning `.local` into another permanent archive.

## Relationship To Working Root Policy

If the user already chose a runtime destination, follow that choice.

If the destination is unclear, use `use-project-working-root` first to decide whether runtime files belong in the project folder or in the private Codex working root. Do not silently create `.venv`, `node_modules`, or dependency caches in a synced document workspace.

Do not write this policy to global `AGENTS.md`.

## Core Rules

- Do not move installed package files from `.local` directly into `.venv` or `node_modules`.
- Recreate dependencies from `requirements.txt`, `pyproject.toml`, `package.json`, lockfiles, or inferred top-level dependencies.
- Keep final outputs where the project already expects them, such as `notes/`, `sources/`, `docs/`, `reports/`, or user-specified output folders.
- Move reusable scripts to `scripts/`.
- Move small durable script inputs, overrides, fixtures, and manually curated JSON/YAML/CSV files to `scripts/data/`.
- Delete files that would only have gone to `%TEMP%` or `/tmp` once the original task is complete.
- If a file might be durable and deletion risk is unclear, stop and ask or place it in a clearly named review folder only with user approval.

## Inventory

Before moving or deleting anything:

1. Read project instructions and check Git status.
2. List top-level `.local` contents, sizes, and file counts.
3. Search `.local` scripts and active project files for references to:
   - `.local`
   - `pydeps`
   - `.deps`
   - `node_modules`
   - cache/output folder names
4. Identify existing environment definitions:
   - Python: `pyproject.toml`, `requirements.txt`, `uv.lock`, `poetry.lock`, setup files.
   - Node.js: `package.json`, `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `packageManager`.
5. Identify whether `.local` contains copied dependency trees such as `pydeps`, `.deps`, `site-packages`, `node_modules`, package-manager caches, or model/runtime caches.

## Classification

Classify `.local` contents into these buckets.

### Preserve As Project Source

Move to `scripts/`:

- reusable `.py`, `.ps1`, `.js`, `.ts`, `.cmd`, `.bat`, or shell scripts;
- helper modules that were authored for the project;
- deterministic transformation or generation scripts.

Move to `scripts/data/`:

- small hand-authored inputs;
- answer overrides;
- mapping tables;
- compact raw JSON used by scripts;
- fixtures that are useful for future reruns.

Keep final outputs in their existing project folders. Do not move final deliverables into `scripts/`.

### Recreate As Runtime Dependencies

Treat these as disposable after replacement:

- `.local/pydeps`
- `.local/.deps`
- copied `site-packages`
- package manager stores or caches
- `node_modules`
- build trackers and wheel/build caches

For Python, infer top-level dependencies from imports, existing metadata, and existing project definitions. Prefer top-level dependencies over transitive dependency lists unless reproducibility requires pins.

For Node.js, infer dependencies from `package.json` or existing lockfiles. Do not infer a full dependency tree from `node_modules` unless there is no better source and the user approves.

### Delete As Temporary Or Generated

Delete after preservation and dependency recreation succeed:

- translation caches;
- previews and audits generated for one task;
- downloaded raw caches that can be regenerated and are not treated as durable source;
- `__pycache__` and compiled files;
- logs, build output, scratch folders, and temporary extracts;
- old package install targets once `.venv` or `node_modules` is working.

## Python Migration

When `.local` contains Python dependency artifacts:

1. Create or update a project dependency definition.
   - Prefer existing `pyproject.toml` or `requirements.txt`.
   - If none exists, create `requirements.txt` with inferred top-level dependencies.
   - Consider splitting heavy optional dependencies into files such as `requirements-optional.txt` when they are not always needed.
2. Create the environment at the selected runtime root.
   - Prefer `uv venv .venv` when `uv` is available.
   - Otherwise use `python -m venv .venv`.
3. Install from the dependency definition.
   - With `uv`: `uv pip install --python .venv\Scripts\python.exe -r requirements.txt`
   - Without `uv`: `.venv\Scripts\python.exe -m pip install -r requirements.txt`
4. If `uv venv` created an environment without `pip` and `python -m pip show` is needed for validation, run `.venv\Scripts\python.exe -m ensurepip --upgrade`.
5. Patch moved scripts so they import from the environment normally and do not modify `sys.path` to point at `.local`, `pydeps`, or `.deps`.

## Node.js Migration

When `.local` contains Node.js dependency artifacts:

1. Inspect `package.json`, lockfiles, and `packageManager`.
2. Keep or create `package.json` only when the project actually needs reusable Node.js runtime.
3. Use the existing package manager:
   - `pnpm` for `pnpm-lock.yaml` or `packageManager` pnpm;
   - `yarn` for `yarn.lock` or `packageManager` yarn;
   - `npm` for `package-lock.json` or when no other policy exists.
4. Install dependencies so `node_modules` is created at the selected runtime root.
5. Do not copy an old `.local/node_modules` tree into place.

## Script Patching

After moving scripts:

- Make project root detection explicit, usually from `Path(__file__).resolve().parents[1]` for scripts under `scripts/`.
- Replace `.local` input paths with `scripts/data` only for durable data.
- Replace generated preview or audit output paths with `scripts/output` or another ignored project output folder when future reruns need them.
- Replace reusable caches with an ignored cache folder only when caching materially improves future runs.
- Use the OS temporary directory for short-lived scratch files and delete those files before finishing.
- Do not write private absolute paths into scripts, README files, tests, or sample configuration.

## Ignore Rules

Update `.gitignore` before or with the migration. Keep existing project-specific entries and add only relevant runtime ignores.

Typical Python entries:

```gitignore
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
.mypy_cache/
.cache/
scripts/.cache/
scripts/output/
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
scripts/output/
```

Remove `.local/` from `.gitignore` when the project should not silently recreate `.local`. Leave it only if the user explicitly wants `.local` to remain an ignored durable workspace.

## Deletion Safety

On Windows, use one PowerShell flow for moves and deletes. Before recursive delete or move:

- resolve the absolute project root;
- resolve the absolute `.local` path;
- verify `.local` is inside the intended project root;
- verify the path leaf is exactly `.local`;
- use `Remove-Item -LiteralPath <resolved-local> -Recurse -Force`.

Do not build delete commands by piping paths from one shell into another. Do not delete `.local` until preservation, dependency installation, script patching, and validation have succeeded.

## Project Reminders

When the cleanup establishes a new project convention, add or update a short project-local `AGENTS.md` unless the user declines or the task is read-only.

Keep it brief:

```markdown
## Runtime

Use `.venv/` for Python dependencies or `node_modules/` for Node.js dependencies when this project is the selected runtime root. Keep reusable helper scripts under `scripts/` and small durable script inputs under `scripts/data/`. Do not recreate `.local/`, `pydeps/`, dependency caches, or large generated working files in this project folder.
```

If the runtime root is private `.codex-working`, let `use-project-working-root` provide the reminder instead.

## Validation

Before finishing, verify the concrete outcome:

- the new runtime root exists when needed;
- Python packages import or `python -m pip show` works inside `.venv`;
- Node package manager validation passes when Node.js was involved;
- moved scripts compile or run a representative dry-run;
- active scripts and config no longer reference `.local`, `pydeps`, or old dependency folders except in explicit "do not recreate" guidance;
- `.gitignore` ignores the new runtime and cache folders;
- `.local` no longer exists, or any remaining `.local` contents are explicitly reported;
- Git status shows no unexpected large runtime folder except ignored `.venv` or `node_modules`;
- any project context or session note that previously instructed `.local` use has been updated when that context is in scope.
