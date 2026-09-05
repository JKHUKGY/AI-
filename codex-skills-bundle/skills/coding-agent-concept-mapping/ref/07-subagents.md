# Subagents

A subagent is a delegated agent with its own system prompt, tool set, and isolated context, spawned to handle a focused task without cluttering the main conversation. All three tools have the concept and all isolate the subagent's context, but they differ on how a subagent is defined, whether the main agent delegates to it on its own, and how much a subagent can be tailored. Claude Code and Antigravity have converged on nearly the same shape, a Markdown file whose YAML frontmatter configures the agent and whose body is the system prompt, while Codex uses TOML and spawns only when asked.

## 1. Definition file and format

A subagent needs its definition somewhere. Claude Code and Antigravity both use one Markdown file per agent with YAML frontmatter, so a definition often ports with only field renames, while Codex uses TOML.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| File | `.claude/agents/<name>.md` | `.codex/agents/<name>.toml` | `.agents/agents/<name>.md`, or `.agents/agents/<name>/agent.md` |
| Format | Markdown, and the body is the system prompt | TOML | Markdown with YAML frontmatter, and the body is the system prompt |
| Scope | project and user, plus plugin and managed | user `~/.codex/agents/` and project `.codex/agents/` | workspace `.agents/agents/`, global `~/.gemini/config/agents/`, and a plugin's `plugins/<name>/agents/` |
| Runtime definition | No equivalent; a definition is always a file | No equivalent | a `define_subagent` tool creates a transient subagent for the session |
| Porting-in notes | put the system prompt in the Markdown body and the config in YAML frontmatter | rewrite a Markdown agent as TOML, with the prompt in `developer_instructions` | the file shape matches Claude Code, so move it to `.agents/agents/` and rename the frontmatter fields; set `subagent: true` or it cannot be invoked |

---

## 2. Config fields

The fields that shape a subagent decide how tightly it can be specialized. Claude Code exposes the largest set, Codex a compact one, and Antigravity now sits between them with a documented frontmatter schema.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Identity | `name` and `description` | `name` and `description` | `name` and `description`, both required |
| System prompt | the Markdown body | `developer_instructions` | the Markdown body after the frontmatter |
| Tool access | `tools` allow list and `disallowedTools` deny list | `sandbox_mode` and `mcp_servers` | a `tools` allow list naming exact tools such as `view_file` and `run_command` |
| Model | `model`, defaulting to `inherit` | `model` and `model_reasoning_effort` | `model`, one of `inherit`, `flash`, or `pro`, defaulting to `inherit` |
| Command execution | governed by the permission settings | `sandbox_mode` | `commandExecutionPolicy`, one of `off`, `auto`, `eager`, or `sandbox` |
| Attachable resources | `mcpServers`, `hooks`, `memory`, and more | `mcp_servers` | `mcpServers`, plus `skills` and `plugins` paths |
| Role gating | any agent can be delegated to | any agent can be spawned | `subagent` and `mainAgent` booleans decide whether it can be invoked or chosen as the primary |
| Porting-in notes | a rich frontmatter set also covers permissions, memory, hooks, and more | tool access is a sandbox mode and MCP list, not a per tool allow list | the field names differ from Claude Code (`commandExecutionPolicy`, `mainAgent`) and a misspelled entry in `tools` is documented to hang the subagent, so check tool names exactly |

---

## 3. Invocation

Whether the main agent reaches for a subagent on its own, or only when told, is the sharpest behavioral split. Each tool also ships a small set of built in agent types.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Automatic delegation | yes, driven by the `description` | no, explicit only | yes, the planner uses the `description` to decide when to delegate |
| Explicit trigger | name it, `@agent-<name>`, or `claude --agent` | a direct instruction to spawn | the `invoke_subagent` tool, or pick it in the `/agents` panel |
| Built in types | `Explore`, `Plan`, `general-purpose` | `default`, `worker`, `explorer` | `research`, `browser` (only via `/browser`), and `self` |
| Workspace for the child | the same working tree | the same working tree | `inherit`, `branch` for an isolated git worktree, or `share` |
| Porting-in notes | add "use proactively" to the `description` to encourage automatic delegation | nothing runs a subagent unless you ask, so name it in the instruction | the `description` is what the planner reads, so write it for delegation; `branch` gives a subagent its own git worktree, which has no peer elsewhere |

---

## 4. Context and tool isolation

Every tool runs a subagent in its own context and returns only a summary, so the main conversation stays clean. They differ on how a subagent's permissions relate to the parent's.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Context | a fresh window with no conversation history; only a summary returns | fresh context, only summaries return | a clean slate that does not inherit the parent's conversation history |
| Tool ceiling | bounded by `tools` and the permission settings | inherits the parent sandbox, overridable per agent | inherits the parent's command prefixes, file scopes, and sandbox settings |
| Escalation | a subagent can be granted its own MCP servers and hooks | a subagent can narrow but not widen host keys | a subagent can never escalate beyond the parent |
| Unapproved actions | the subagent's prompt surfaces to the user | the subagent's prompt surfaces to the user | permission bubbling sends the request up to the main panel, reachable with `Alt+J` |
| Porting-in notes | give a subagent its own `mcpServers`, `hooks`, or `memory` when it needs them | a subagent reapplies the parent's runtime overrides and cannot loosen them | a subagent inherits the parent's approvals and bubbles anything unapproved back up rather than failing |

---

## 5. Parallelism and management

Running several subagents at once is where these systems converge in spirit but differ in controls. Claude Code and Antigravity both foreground background execution with a manager, while Codex exposes numeric caps.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Parallel and background | subagents run in background by default and in parallel | parallel by default, capped by `agents.max_threads` | background parallel threads are the headline model |
| Nesting | a subagent can spawn others, up to depth 5 | `agents.max_depth`, default 1 | up to depth 10, strictly enforced |
| Manager command | `/agents` prints where definitions live | no dedicated manager command | `/agents` opens the Agent Manager panel; `/tasks` tracks non agentic background processes |
| Lifecycle states | running, then a returned summary | running, then a returned summary | running, idle (re awakened by a message, keeping prior context), or killed |
| Inter agent messaging | No equivalent; results return to the parent | No equivalent; results return to the parent | agents message each other by conversation ID and can read each other's transcripts |
| Porting-in notes | `/tasks` and the @-mention typeahead track running background subagents | raise `agents.max_threads` for concurrency and `agents.max_depth` to allow nesting | an idle subagent is not finished, since messaging it wakes it up with its context intact, which is a lifecycle neither other tool has |

---

## 6. Sources

**Claude Code**

- Create custom subagents: https://code.claude.com/docs/en/sub-agents.md
- Run agents in parallel: https://code.claude.com/docs/en/agents.md

**Codex**

- Subagents: https://learn.chatgpt.com/docs/agent-configuration/subagents.md

**Antigravity**

- CLI Subagents: https://antigravity.google/docs/cli/subagents
- Subagents: https://antigravity.google/docs/subagents
- CLI Plugins: https://antigravity.google/docs/cli/plugins
