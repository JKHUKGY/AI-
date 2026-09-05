# Permissions

Permissions decide whether a given tool call runs automatically, prompts the user, or is blocked, and they are enforced by the tool rather than by the model. Claude Code and Antigravity converge on nearly the same design: one allow, ask, deny map, a deny over ask over allow order, and a compact `verb(target)` rule grammar. Codex takes a different path, splitting the decision across a sandbox mode, an approval policy, permission profiles, and command rules, with no single allow ask deny map. This is the same divergence seen in settings and hooks, where two tools land on one model and Codex builds its own.

## 1. Configuration and decision model

The core question is how each tool decides whether a tool call runs. Claude Code and Antigravity both keep one allow, ask, deny map, while Codex splits the decision across a sandbox mode and an approval policy plus optional profiles.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Where | `permissions` in `settings.json` | `approval_policy` and `sandbox_mode` in `config.toml`, plus `[permissions.NAME]` profiles | `permissions` in `~/.gemini/antigravity-cli/settings.json` |
| Decision model | one allow, ask, deny map | two axes, a sandbox mode and an approval policy, with no single map | one allow, deny, ask map |
| Buckets | `allow`, `ask`, `deny` | `rules` decisions `allow`, `prompt`, `forbidden`, and profile values `read`, `write`, `deny` | `allow`, `deny`, `ask` |
| Porting-in notes | sort each rule into the `allow`, `ask`, or `deny` array | there is no single map, so pick a `sandbox_mode` and `approval_policy`, and express fine grained rules through profiles or `rules` | the model matches Claude Code, but the file is the CLI `settings.json` |

---

## 2. Rule syntax

How a single permitted or blocked action is written differs. Claude Code and Antigravity share a compact `verb(target)` grammar, while Codex uses TOML value maps and Starlark prefix rules.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Command rule | `Bash(git commit:*)` | `prefix_rule(pattern=["git","commit"], decision=...)` in Starlark | `command(git)`, `command(npm run (build\|lint\|test))` |
| File rule | `Read(//path)`, `Edit(/src/**)` | path to value maps such as `"." = "write"` and `"**/*.env" = "deny"` | `read_file(/path)`, `write_file(src/)` |
| Network rule | `WebFetch(domain:example.com)` | domain to value maps such as `"api.openai.com" = "allow"` | `read_url(domain)`, `execute_url(domain)` |
| MCP rule | `mcp__server__tool` | governed by profiles and approvals | `mcp(server/tool)`, `mcp(server/*)` |
| Porting-in notes | one `Tool(specifier)` grammar covers commands, files, domains, and MCP | rewrite command rules as Starlark `prefix_rule` entries and path or domain rules as TOML maps | the `verb(target)` forms mirror Claude Code, so `Bash(...)` becomes `command(...)` and `Read` or `Edit` become `read_file` or `write_file` |

---

## 3. Precedence

When several rules could match, the order in which they resolve determines the outcome. Claude Code and Antigravity state the same order, and Codex applies an equivalent most restrictive rule within each of its mechanisms.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Order | deny, then ask, then allow | most restrictive wins, `forbidden` over `prompt` over `allow` | deny, then ask, then allow |
| Default for an unlisted action | prompt on first use | depends on `approval_policy` and `sandbox_mode` | ask |
| Across scopes | rules merge, and a deny at any scope wins | profiles and rules layer, with deny taking precedence | deny beats ask beats allow |
| Porting-in notes | a deny cannot carry an allow exception, so scope denies carefully | the same most restrictive idea holds inside both profiles and `rules` | an unconfigured action defaults to ask, and `command(*)` in ask overrides a narrower allow |

---

## 4. Modes and sandbox

Each tool offers coarse preset modes and a sandbox layer that limits what a command can physically do, separate from the per action rules.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Preset modes | `default`, `acceptEdits`, `plan`, `auto`, `dontAsk`, `bypassPermissions` | `approval_policy` presets `untrusted`, `on-request`, `never` | `/permissions` presets `request-review`, `always-proceed`, `strict` |
| Sandbox | a separate `sandbox` object for the Bash tool | `sandbox_mode` of `read-only`, `workspace-write`, or `danger-full-access` | `enableTerminalSandbox`, off by default, with OS containment |
| Escape hatch | `bypassPermissions`, or `--dangerously-skip-permissions` | `--dangerously-bypass-approvals-and-sandbox` | `unsandboxed(...)` for allowlisted commands |
| Porting-in notes | sandboxing is a distinct layer from the allow and deny rules | the sandbox mode and the approval policy are independent axes that combine into a preset | the sandbox is a single boolean, and specific commands opt out with `unsandboxed` |

---

## 5. Managed control and commands

Every tool has an in session command to review permissions, but they differ sharply on enterprise enforcement. Claude Code and Codex both lock policy from a managed layer, while Antigravity documents none.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| In session command | `/permissions` to view and manage rules | `/permissions` to switch to read only | `/permissions` to switch presets |
| Managed enforcement | `allowManagedPermissionRulesOnly` in managed settings | `requirements.toml` pins policies and profiles | No equivalent documented |
| Lock the escape hatch | `disableBypassPermissionsMode` | `allowed_approval_policies` and `allowed_sandbox_modes` | No equivalent documented |
| Porting-in notes | an organization can force its rules with `allowManagedPermissionRulesOnly` | `requirements.toml` is the enforced enterprise layer that users cannot override | there is no documented enterprise permission locking, so rules stay per user |

---

## 6. Sources

**Claude Code**

- Configure permissions: https://code.claude.com/docs/en/permissions.md
- Choose a permission mode: https://code.claude.com/docs/en/permission-modes.md
- Configure the sandboxed Bash tool: https://code.claude.com/docs/en/sandboxing.md

**Codex**

- Permissions: https://learn.chatgpt.com/docs/permissions.md
- Sandbox: https://learn.chatgpt.com/docs/sandboxing.md
- Rules: https://learn.chatgpt.com/docs/agent-configuration/rules.md

**Antigravity**

- CLI Permissions: https://antigravity.google/docs/cli/permissions
- CLI Sandbox: https://antigravity.google/docs/cli/sandbox
- CLI Reference: https://antigravity.google/docs/cli/reference
