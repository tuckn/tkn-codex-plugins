# tkn-codex-plugins

[English](README.md) | [日本語](README_ja.md)

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

This repository stores finished plugin bundles. Development source trees should live in separate
repositories and publish completed bundles into `plugins/<plugin-name>/`.

## Plugins

### Tuckn Codex Context Engineering

This plugin organizes Brain Dumps into Markdown planning notes and searches local Codex chat
history. Its two bundled Skills are `organize-brain-dump` and `search-all-codex-chats`.

Path:

```text
plugins/tkn-codex-context-engineering/
```

Details:

- [Plugin README](plugins/tkn-codex-context-engineering/README.md)
- [日本語 README](plugins/tkn-codex-context-engineering/README_ja.md)

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
