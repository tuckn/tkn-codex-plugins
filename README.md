# tkn-codex-plugins

Tuckn's public Codex plugin marketplace.

## Install

Add this repository as a Codex plugin marketplace:

```sh
codex plugin marketplace add tuckn/tkn-codex-plugins --ref main
```

Codex reads the marketplace manifest from:

```text
.agents/plugins/marketplace.json
```

## Marketplace Layout

- `.agents/plugins/marketplace.json`: marketplace catalog for this repository.
- `plugins/`: publishable Codex plugin bundles.
- `scripts/sync_skills/`: legacy Skill copy-distribution tooling sourced from plugin bundles.

This repository stores finished plugin bundles. Development source trees should live in separate
repositories and publish completed bundles into `plugins/<plugin-name>/`.

## Plugins

### TKN Codex Context Engineering

Path:

```text
plugins/tkn-codex-context-engineering/
```

Plugin manifest:

```text
plugins/tkn-codex-context-engineering/.codex-plugin/plugin.json
```

Included Skills:

- `extract-codex-sessions`
- `import-global-context`
- `maintain-session-note`
- `maintain-working-context`
- `organize-brain-dump`
- `promote-global-context`
- `register-project-context`
- `record-decision`
- `resume-session`
- `review-decisions`

The plugin preserves and resumes Codex working context through repository project registration,
working context, session notes, decision records, local Codex session-log extraction, and explicit
import or promotion of user-global context through `~/.codex-context`.

## Adding Plugins

Add each new plugin under:

```text
plugins/<plugin-name>/
```

Each plugin must include:

```text
plugins/<plugin-name>/.codex-plugin/plugin.json
```

Then add a matching entry to:

```text
.agents/plugins/marketplace.json
```

Use repo-relative marketplace paths such as:

```json
{
  "name": "plugin-name",
  "source": {
    "source": "local",
    "path": "./plugins/plugin-name"
  },
  "policy": {
    "installation": "AVAILABLE",
    "authentication": "ON_INSTALL"
  },
  "category": "Productivity"
}
```

## Legacy Skill Sync

The preferred distribution path is the Codex plugin marketplace. For environments where plugins
are unavailable, `scripts/sync_skills/sync_skills.py` can still copy
`plugins/tkn-codex-context-engineering/skills/` into target repositories.

Create your local target manifest from the sample:

```powershell
Copy-Item scripts\sync_skills\targets_sample.json scripts\sync_skills\targets.json
```

Edit `scripts/sync_skills/targets.json` for your machine. This file is intentionally ignored by
Git because it contains local absolute paths. Windows paths are canonical; when the script runs
outside Windows, drive paths such as `C:\example\repo` are converted to `/mnt/c/example/repo`.

Manifest shape:

```json
{
  "targets": [
    {
      "name": "notes",
      "path": "C:\\example\\workspaces\\notes",
      "skillsPath": ".agents\\skills"
    }
  ]
}
```

Common commands:

```sh
python3 scripts/sync_skills/sync_skills.py --dry-run
python3 scripts/sync_skills/sync_skills.py --target notes
python3 scripts/sync_skills/sync_skills.py --target notes --skill maintain-session-note
python3 scripts/sync_skills/sync_skills.py --manifest scripts/sync_skills/targets_sample.json --dry-run
```
