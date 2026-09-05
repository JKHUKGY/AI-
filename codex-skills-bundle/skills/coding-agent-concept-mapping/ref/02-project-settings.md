# Project settings

Project settings are the configuration that controls how the agent behaves in a repository: which model runs, what it is allowed to do, which servers and hooks are active, and what environment it sees. In Claude Code this is a JSON file at each scope, in Codex a TOML file at each scope, and in Antigravity a single user level CLI settings file at `~/.gemini/antigravity-cli/settings.json`, with no project level settings file.

## 1. File location and naming

Each tool keeps its configuration at a known place per scope. Claude Code and Codex each use one committed file for the whole project. The Antigravity CLI keeps its settings in one user level file and has no project level settings file, so a repo can only commit the narrower `.agents/` config.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| User / global | `~/.claude/settings.json` | `~/.codex/config.toml` (relocatable via `CODEX_HOME`) | `~/.gemini/antigravity-cli/settings.json` |
| Project committed | `.claude/settings.json` | `.codex/config.toml` in the repo | no project settings file; only `.agents/mcp_config.json` and `.agents/rules/` |
| Project local (gitignored) | `.claude/settings.local.json` | No equivalent | No equivalent |
| Enterprise / managed | `managed-settings.json` at an OS specific path | `/etc/codex/config.toml`, plus cloud managed policy | Google Cloud IAM, no policy file |
| Porting-in notes | expect one JSON file per scope, and move personal overrides into `.claude/settings.local.json` | put repo config in `.codex/config.toml`, which loads only when the project is trusted | there is no project settings file, so user preferences live in the one CLI `settings.json`, and only MCP travels in `.agents/mcp_config.json` |

---

## 2. Scope and precedence

When the same setting appears at more than one scope, each tool has a rule for which value wins. Claude Code and Codex both document a full order and gate project rules behind a trust decision. The Antigravity CLI documents only that a live override beats the file on disk.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Winning order, high to low | managed, CLI flags, local, project, user | CLI `-c`, project `.codex/config.toml`, profile file, user, system, defaults | runtime override, then the on disk `settings.json`, then system defaults |
| Merge vs override | scalar keys override, array keys such as permissions merge across scopes | closest file to the working directory wins; a project cannot override host keys like `model_provider` | `settings.json` stores only values that differ from the defaults; cross scope merge unconfirmed |
| Trust gating | project `allow` rules need a workspace trust prompt; the local file does not | project `.codex/` layers load only for trusted projects via `[projects."path"].trust_level` | unconfirmed |
| Porting-in notes | remember that arrays merge rather than replace, so a broad user rule still applies | mark the repo trusted or its `.codex/config.toml` is skipped, and keep host keys machine local | a runtime override holds only until the session ends, and there is no project scope, so set lasting values in the user `settings.json` |

---

## 3. What the settings control

The value of this concept is that one place gathers the model, permission, MCP, and related knobs. The same category surfaces as a JSON key in Claude Code, a TOML table in Codex, and a nested key or slash command in the Antigravity CLI. The deep comparison of each category lives in its own concept file; here is only where each is expressed.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Model | `model`, `fallbackModel` | `model`, `model_reasoning_effort` | the `/model` command, which persists the choice; the exact key is unconfirmed |
| Permissions | `permissions` allow and deny | `approval_policy`, `sandbox_mode`, `[permissions.NAME]` | a `permissions` object with `allow`, `deny`, and `ask` lists |
| Sandbox | part of `permissions` | `sandbox_mode` | `enableTerminalSandbox` boolean, default `false` |
| MCP servers | `enableAllProjectMcpServers` and the `enabledMcpjsonServers` family | `[mcp_servers.NAME]` | `.agents/mcp_config.json` and `~/.gemini/config/mcp_config.json` |
| Environment | `env` | `[shell_environment_policy]` | No equivalent documented; auth uses the OS keyring |
| Porting-in notes | one JSON file houses every category | categories split into TOML tables rather than nested JSON objects | model is chosen interactively, permissions and sandbox live in `settings.json`, and MCP is a separate file |

---

## 4. Format and syntax

The file format itself changes what a ported config has to become. JSON, TOML, and the CLI's sparse nested JSON each impose different rules for comments, structure, and validation.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Config style | file first, JSON | file first, TOML | file first, JSON, but only non default values are written to disk |
| Comments | not supported, plain JSON | `#` line comments | unconfirmed |
| Schema | `$schema` URL for editor validation | optional `#:schema` hint line | unconfirmed; docs only call the format forward compatible |
| Structure | flat keys and nested objects | nested tables like `[mcp_servers.NAME]` | nested JSON, for example the `permissions` object; the separate `keybindings.json` is flat |
| Porting-in notes | strip comments when converting from TOML, since JSON rejects them | reshape flat keys into TOML tables and quote project paths in `[projects."..."]` | write only the values you want to change, since defaults are never persisted |

---

## 5. Signature features

Beyond the shared idea of a config file, each tool adds its own layer for personal overrides, one off changes, and interactive control. These rarely have a clean counterpart elsewhere.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Personal override layer | `.claude/settings.local.json`, auto added to git ignore | separate profile files `~/.codex/<name>.config.toml` loaded with `--profile` | No equivalent (no project or local file) |
| One off override | `--settings` and other flags for the session | `-c key=value` parsed as TOML, highest precedence | a runtime override that holds until the session ends |
| Interactive control | `/config` opens a settings UI, and `/config key=value` sets one option | approval and sandbox prompts during a run | `/config` (alias `/settings`) opens a settings editor, plus `/model`, `/mcp`, and `/permissions` |
| Managed control | keys like `forceLoginMethod` and `policyHelper` are valid only in the managed file | cloud managed requirements override governed keys | enterprise control through Google Cloud IAM |
| Porting-in notes | keep anything personal in `.claude/settings.local.json` so it stays out of the shared file | profiles are now separate files rather than `[profiles]` tables, so keep each bundle as its own `<name>.config.toml` | there is no local file, so personal choices go in the user `settings.json` or a per session runtime override |

---

## 6. Sources

**Claude Code**

- Claude Code settings: https://code.claude.com/docs/en/settings.md
- Explore the .claude directory: https://code.claude.com/docs/en/claude-directory.md

**Codex**

- Config basics: https://learn.chatgpt.com/docs/config-file/config-basic.md
- Configuration Reference: https://learn.chatgpt.com/docs/config-file/config-reference.md
- Sample Configuration: https://learn.chatgpt.com/docs/config-file/config-sample.md
- Advanced Configuration: https://learn.chatgpt.com/docs/config-file/config-advanced.md

**Antigravity**

- CLI Settings: https://antigravity.google/docs/cli/settings
- CLI Reference: https://antigravity.google/docs/cli/reference
- CLI Permissions: https://antigravity.google/docs/cli/permissions
- CLI Sandbox: https://antigravity.google/docs/cli/sandbox
- Model Context Protocol: https://antigravity.google/docs/mcp
- Enterprise Features: https://antigravity.google/docs/enterprise
