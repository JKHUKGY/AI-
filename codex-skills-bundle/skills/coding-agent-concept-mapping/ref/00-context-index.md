# Concept Index

This is the table of contents for the cross tool concept mapping knowledge base.
It lists every project level configuration concept that has been mapped across
Claude Code, Codex, and Antigravity, with a one line blurb, each tool's primary
file or location, and a link to the full detail file. Read a concept's blurb
here to find the right detail file, then open that file for the aspect by aspect
comparison and the porting notes.

Concept sections are added in registry order as each detail file is authored.
The registry that assigns concept numbers, and the format both this index and
the detail files follow, live in the maintainer side
`coding-agent-concept-mapping-builder` skill, which does not ship with this
plugin: https://github.com/MacHu-GWU/shsk_coding_agent_docs-project/blob/main/.claude/skills/coding-agent-concept-mapping-builder/SKILL.md
This index is generated from the detail files and is not a place where new facts
first appear. When a concept below disagrees with its detail file, the detail
file is correct.

## 1. Project prompt

The persistent project instruction file an agent loads at the start of every
session. Claude Code and Codex each read one canonical file, while Antigravity
has no single always-on file and spreads the role across a global file and a
project rules directory.

| Tool | Primary file or location |
|---|---|
| Claude Code | `CLAUDE.md` at repo root or `.claude/` |
| Codex | `AGENTS.md` at repo root |
| Antigravity | `.agents/rules/*.md` plus global `~/.gemini/GEMINI.md` |

Detail: [01-project-prompt.md](01-project-prompt.md)

---

## 2. Project settings

The project level configuration that controls model, permissions, MCP servers,
and related behavior. Claude Code and Codex each keep one committed config file
per scope, while the Antigravity CLI keeps its settings in one user level file
and has no project level settings file.

| Tool | Primary file or location |
|---|---|
| Claude Code | `.claude/settings.json` (plus `.claude/settings.local.json`) |
| Codex | `.codex/config.toml` in the repo |
| Antigravity | `~/.gemini/antigravity-cli/settings.json`; no project file |

Detail: [02-project-settings.md](02-project-settings.md)

---

## 3. Skills

Reusable capability packages defined by a `SKILL.md` file with YAML frontmatter,
loaded on demand and triggered explicitly or by description match. The three
tools converge on the same entry file and contract; Codex and Antigravity share
the tool neutral `.agents/skills/` path, while Claude Code uses `.claude/skills/`.

| Tool | Primary file or location |
|---|---|
| Claude Code | `.claude/skills/<name>/SKILL.md` |
| Codex | `.agents/skills/<name>/SKILL.md` |
| Antigravity | `.agents/skills/<name>/SKILL.md` |

Detail: [03-skills.md](03-skills.md)

---

## 4. Custom commands

User defined slash commands that expand a trigger into a saved prompt or
procedure. The concept has collapsed into skills: Claude Code merged its command
files into skills, Codex deprecated custom prompts for skills, and Antigravity
documents no separate mechanism at all, since a skill compiles directly into a
`/name` command. Antigravity workflows are a distinct multi step primitive.

| Tool | Primary file or location |
|---|---|
| Claude Code | `.claude/commands/*.md` (legacy, merged into skills) |
| Codex | `~/.codex/prompts/*.md` (deprecated, use skills) |
| Antigravity | a skill compiles into `/<name>`; no separate command mechanism |

Detail: [04-custom-commands.md](04-custom-commands.md)

---

## 5. Hooks

Commands that run automatically at lifecycle events such as before or after a
tool call, for deterministic automation and gating. All three share the core
tool events but differ on config location, event count, and control mechanism.
Codex closely mirrors the Claude Code protocol (exit code plus JSON on stdin),
while Antigravity uses a separate `hooks.json`, only five events, and JSON on
stdout for flow control.

| Tool | Primary file or location |
|---|---|
| Claude Code | `hooks` key in `.claude/settings.json` |
| Codex | `[hooks]` in `.codex/config.toml` or `hooks.json` |
| Antigravity | `hooks.json` in `.agents/` or `~/.gemini/config/` |

Detail: [05-hooks.md](05-hooks.md)

---

## 6. MCP servers

External Model Context Protocol servers that add tools, resources, and prompts.
All three implement the same protocol; Claude Code and Antigravity use a JSON
`mcpServers` object while Codex uses TOML tables, and the remote server field
differs (`url`, `url`, and `serverUrl`), which is the usual porting break. Each
exposes a `/mcp` command and OAuth login.

| Tool | Primary file or location |
|---|---|
| Claude Code | `.mcp.json` (project), `~/.claude.json` (local and user) |
| Codex | `[mcp_servers.NAME]` in `.codex/config.toml` |
| Antigravity | `.agents/mcp_config.json`, global `~/.gemini/config/mcp_config.json` |

Detail: [06-mcp-servers.md](06-mcp-servers.md)

---

## 7. Subagents

Delegated agents with their own system prompt, tools, and isolated context, for
focused or parallel work. Claude Code and Antigravity have converged on the same
shape, a Markdown file whose YAML frontmatter configures the agent and whose body
is the system prompt, and both auto delegate from the `description`, while Codex
uses TOML and spawns only when asked. All three isolate context and return a
summary.

| Tool | Primary file or location |
|---|---|
| Claude Code | `.claude/agents/<name>.md` |
| Codex | `.codex/agents/<name>.toml` |
| Antigravity | `.agents/agents/<name>.md` |

Detail: [07-subagents.md](07-subagents.md)

---

## 8. Permissions

Control over whether a tool call runs, prompts, or is blocked, enforced by the
tool not the model. Claude Code and Antigravity share one allow, ask, deny map
with a deny over ask over allow order and a `verb(target)` rule grammar, while
Codex splits the decision across a sandbox mode, an approval policy, permission
profiles, and command rules.

| Tool | Primary file or location |
|---|---|
| Claude Code | `permissions` in `.claude/settings.json` |
| Codex | `approval_policy` and `sandbox_mode` in `.codex/config.toml` |
| Antigravity | `permissions` in `~/.gemini/antigravity-cli/settings.json` |

Detail: [08-permissions.md](08-permissions.md)

---

## 9. Plugins and marketplaces

The package that bundles skills, subagents, hooks, MCP servers, and rules into
one installable unit, plus the catalog that distributes it. Claude Code and
Codex line up almost exactly: a hidden manifest directory, a `marketplace.json`
catalog, the same git and npm source types including `git-subdir`, and a
`plugin marketplace add` command. Antigravity has plugins but no marketplace at
all, so a plugin arrives only as a local directory.

| Tool | Primary file or location |
|---|---|
| Claude Code | `.claude-plugin/plugin.json`, catalog at `.claude-plugin/marketplace.json` |
| Codex | `.codex-plugin/plugin.json`, catalog at `.agents/plugins/marketplace.json` |
| Antigravity | `plugin.json` at the plugin root; no catalog |

Detail: [09-plugins-and-marketplaces.md](09-plugins-and-marketplaces.md)
