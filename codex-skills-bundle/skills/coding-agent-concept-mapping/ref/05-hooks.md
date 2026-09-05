# Hooks

A hook is a command that runs automatically at a fixed point in the agent's lifecycle, such as before a tool call or when a turn ends, giving deterministic control over behavior that a prompt alone cannot guarantee. All three tools share the core idea and the two central events, before and after a tool call, but they diverge sharply on where hooks are configured, how many events exist, and how a hook signals a decision. Codex mirrors the Claude Code protocol closely, while Antigravity reimplements the idea with its own file, a smaller event set, and a different control mechanism.

## 1. Configuration location and format

A hook binds a command to an event, and the first difference is simply where that binding lives. Claude Code keeps hooks inside its settings file, Codex allows either config tables or a sibling file, and Antigravity uses a dedicated file.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Where defined | the `hooks` key in `settings.json` | `[hooks]` in `.codex/config.toml`, or a sibling `hooks.json` | a dedicated `hooks.json` file |
| Location | user, project, local, and managed scopes, plus plugin and skill frontmatter | `~/.codex/` and the repo `.codex/`, with the project layer trust gated | workspace `.agents/`, or global `~/.gemini/config/` |
| Format | JSON | TOML tables, or JSON in `hooks.json` | JSON |
| Enable toggle | `disableAllHooks`, though managed hooks still run | `features.hooks = true`, plus a per hook trust review | an `enabled` boolean per hook, default true |
| Porting-in notes | hooks are a key inside `settings.json`, not a separate file | turn on `features.hooks` and trust each hook, since a feature gated or untrusted hook silently does not run | move hooks out of the settings file into their own `hooks.json` under `.agents/` |

---

## 2. Event types

The lifecycle events decide when a hook can fire. Claude Code exposes by far the most, Codex mirrors its core names with a few additions, and Antigravity defines only five, centered on tool calls and model invocations.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Around a tool call | `PreToolUse`, `PostToolUse`, plus failure and batch variants | `PreToolUse`, `PostToolUse` | `PreToolUse`, `PostToolUse` |
| Around a model turn | `UserPromptSubmit`, `Stop`, `SubagentStart`, `SubagentStop` | `UserPromptSubmit`, `Stop`, `SubagentStart`, `SubagentStop` | `PreInvocation`, `PostInvocation`, `Stop` |
| Session lifecycle | `SessionStart`, `SessionEnd`, and more | `SessionStart` | No equivalent |
| Compaction and permission | `PreCompact`, `PostCompact`, `PermissionRequest` | `PreCompact`, `PostCompact`, `PermissionRequest` | No equivalent |
| Count documented | around thirty | ten | five |
| Porting-in notes | many events have no peer elsewhere, so a ported hook may need re targeting | the core event names match Claude Code closely | only five events exist, and they hang off tool calls and model invocations rather than sessions or prompts |

---

## 3. Matchers and filtering

Most events let a hook target a subset of occurrences rather than firing on all of them. The matcher model is nearly identical across the tools, but the coverage differs.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Matcher | regex on the tool name, a list, or omitted for all | regex on the tool name, `*` or omitted for all | regex on the tool name, `*` or empty for all |
| Where it applies | tool events plus several source typed events | tool events plus source typed session and compaction events | only `PreToolUse` and `PostToolUse` |
| Argument level filter | an `if` field matches the tool name and its arguments | not documented | not documented |
| Porting-in notes | use `if` for argument aware matching, which is unique to Claude Code | matchers are regex as in Claude Code, applied to an event specific field | matchers affect only the two tool events, and the other three always fire |

---

## 4. Execution and flow control

This is the sharpest divergence. Claude Code and Codex both signal a decision through the exit code and structured JSON, while Antigravity drives everything through JSON on stdout and uses different field casing.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Input to the hook | JSON on stdin, snake_case fields | JSON on stdin, snake_case fields | JSON on stdin, camelCase fields |
| Blocking signal | exit code `2`, or JSON `permissionDecision: deny` | exit code `2`, or JSON `permissionDecision: deny` | JSON `decision` of `deny` or `ask`; exit codes are not the mechanism |
| Modify the action | `updatedInput` and `additionalContext` | `updatedInput`, plus continuation prompts | `permissionOverrides`, `injectSteps`, and `terminationBehavior` |
| Concurrency | matching hooks run in parallel, the most restrictive decision wins | matching hooks run concurrently | an array of handlers per matched event |
| Timeout default | 600 seconds | 600 seconds | 30 seconds |
| Porting-in notes | a hook can tighten but not loosen permissions, and `deny` beats `allow` | the protocol is nearly identical to Claude Code, so a hook script often ports with little change | flow control is JSON on stdout rather than exit codes, and fields are camelCase, so a Claude Code or Codex hook script must be rewritten |

---

## 5. Handler types and signature features

Beyond shell commands, the tools differ on what a hook can be and on the tooling around it. Claude Code is far richer here, while Codex and Antigravity keep to shell commands.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Handler types | `command`, `http`, `mcp_tool`, `prompt`, and `agent` | `command` only | `command` only |
| Project path in payload | `${CLAUDE_PROJECT_DIR}` and related variables | `cwd` in the stdin JSON | `workspacePaths` in the stdin JSON |
| Browse command | `/hooks`, a read only menu | `/hooks`, to manage and trust | `/hooks`, to browse active hooks |
| Managed control | `allowManagedHooksOnly` | `managed_dir` and `allow_managed_hooks_only` | No equivalent documented |
| Porting-in notes | only Claude Code offers non shell handlers such as `http` and `prompt` | only shell command hooks exist, so fold any logic into a script | only shell command hooks exist, and enterprise managed hooks are not documented |

---

## 6. Sources

**Claude Code**

- Hooks reference: https://code.claude.com/docs/en/hooks.md
- Automate actions with hooks: https://code.claude.com/docs/en/hooks-guide.md

**Codex**

- Hooks: https://learn.chatgpt.com/docs/hooks.md
- Configuration Reference: https://learn.chatgpt.com/docs/config-file/config-reference.md

**Antigravity**

- Hooks: https://antigravity.google/docs/hooks
- IDE Hooks: https://antigravity.google/docs/ide/hooks
- CLI Reference: https://antigravity.google/docs/cli/reference
