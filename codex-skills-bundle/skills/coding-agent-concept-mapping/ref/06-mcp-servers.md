# MCP servers

An MCP server is an external process or endpoint that speaks the Model Context Protocol, giving the agent extra tools, resources, and prompts beyond its built ins. All three tools implement the same protocol and even share much of the same configuration shape, so this concept ports more cleanly than most. The friction lives in the details: which file holds the config and in what format, the field that names a remote server, and how a project's servers get trusted.

## 1. Configuration location and format

MCP servers are declared one entry per server, but the file and the format differ. Claude Code and Antigravity both use a JSON object keyed `mcpServers`, while Codex uses TOML tables.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Project file | `.mcp.json` at the repo root | `[mcp_servers.NAME]` in `.codex/config.toml` | `.agents/mcp_config.json` |
| User / global | `~/.claude.json`, in local and user scopes | `~/.codex/config.toml` | `~/.gemini/config/mcp_config.json` |
| Format | JSON, under `mcpServers` | TOML tables | JSON, under `mcpServers` |
| Add command | `claude mcp add` | `codex mcp add` | edit the file, or the `/mcp` manager |
| Porting-in notes | put shared servers in `.mcp.json`, and keep personal ones in `~/.claude.json` | convert an `mcpServers` JSON block into `[mcp_servers.NAME]` TOML tables | the JSON `mcpServers` shape matches Claude Code, but the file is `.agents/mcp_config.json`, not `.mcp.json` |

---

## 2. Transport types

Every tool supports a local stdio subprocess and a remote server reached over a URL, but the field that names a remote server differs in each, which is the most common thing to break on a port.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Local subprocess | `command`, `args`, `env`, with `type: stdio` | `command`, `args`, `env`, `env_vars` | `command`, `args`, `env`, `cwd` |
| Remote server | `url` with `type: http`, also `sse` and `ws` | `url` | `serverUrl`; `url` and `httpUrl` are rejected |
| Transport selector | the `type` field | the presence of `url` versus `command` | the presence of `serverUrl` versus `command` |
| Transports supported | stdio, http, sse, ws | stdio and http | stdio, Streamable HTTP, and SSE |
| Porting-in notes | set `type` explicitly, and prefer `http` since `sse` is deprecated | a remote server is just a `url`, with no `type` field | rename a remote server's `url` to `serverUrl`, since `url` and `httpUrl` are refused |

---

## 3. Scope and precedence

Servers can be defined at more than one scope, and each tool gates project servers behind a trust or approval step so a cloned repo cannot silently launch processes.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Scopes | local, project, and user | user, and project | global and workspace |
| Precedence | local over project over user, and the whole entry wins | the closest file wins, and a project cannot override auth keys | the workspace `.agents/mcp_config.json` takes priority over the global file |
| Trust and approval | a project `.mcp.json` server needs approval before first use | project servers load only for a trusted project | a server's tools default to Ask before running |
| Porting-in notes | a cloned repo's servers stay pending until approved, or set `enableAllProjectMcpServers` | mark the project trusted or its MCP servers are skipped | servers connect, but their tools wait behind an Ask prompt until permitted |

---

## 4. Authentication

All three can authenticate to remote servers with OAuth and can source secrets from the environment, but each adds its own conveniences.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| OAuth | `/mcp` or `claude mcp login`, tokens refreshed | `codex mcp login`, stored per `mcp_oauth_credentials_store` | automatic for DCR servers, or a manual `oauth` object |
| Static secrets | a `headers` object, or `--header` at add time | `bearer_token_env_var` and `http_headers` | a `headers` object |
| Env and interpolation | `${VAR}` and `${VAR:-default}` expand inside the file | `env` and `env_vars`, each with a `local` or `remote` source | `env` on stdio servers |
| Provider specific | `apiKeyHelper` for model requests | not documented | `authProviderType: google_credentials` |
| Porting-in notes | use `${VAR}` interpolation to keep secrets out of the committed `.mcp.json` | source secrets from environment variables via `env_vars` and `bearer_token_env_var` | Google backed servers can use `google_credentials`, which has no peer elsewhere |

---

## 5. Management and tool control

Beyond declaring servers, each tool offers an in session command and a way to withhold specific tools or whole servers. Claude Code adds the deepest managed and enterprise controls.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| In session command | `/mcp` to view, authenticate, and reconnect | `/mcp` to view active servers | `/mcp` opens the manager overlay |
| Enable or disable a server | `enabledMcpjsonServers` and `disabledMcpjsonServers` | `enabled` and `required` per server | a `disabled` boolean on the entry, or the manager overlay |
| Tool filtering | managed allow and deny lists, plus tool deferral | `enabled_tools` allow list and `disabled_tools` deny list | a `disabledTools` deny list |
| Managed control | `managed-mcp.json`, `allowedMcpServers`, `deniedMcpServers` | per tool approval modes | permission resources such as `mcp(server/*)` |
| Porting-in notes | an organization can pin the whole server set through `managed-mcp.json` | filter tools per server with `enabled_tools` and `disabled_tools`, and gate them with approval modes | withhold tools with `disabledTools`, and govern execution through `mcp(...)` permission rules |

---

## 6. Sources

**Claude Code**

- Connect Claude Code to tools via MCP: https://code.claude.com/docs/en/mcp.md
- Connect to MCP servers: https://code.claude.com/docs/en/mcp-quickstart.md
- Control MCP server access for your organization: https://code.claude.com/docs/en/managed-mcp.md

**Codex**

- Model Context Protocol: https://learn.chatgpt.com/docs/extend/mcp.md?surface=cli
- Configuration Reference: https://learn.chatgpt.com/docs/config-file/config-reference.md

**Antigravity**

- MCP (CLI): https://antigravity.google/docs/cli/mcp
- Model Context Protocol: https://antigravity.google/docs/mcp
- CLI Reference: https://antigravity.google/docs/cli/reference
