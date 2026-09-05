# Changelog

All notable changes to the `coding-agent-concept-mapping` skill are documented here.

## [0.1.3] - 2026-07-29

- Refreshed concepts 01 through 08 against the current docs after both upstreams moved.
- Rewrote the Antigravity column of `07-subagents.md`. Antigravity now documents a full file-based subagent spec, so five cells that read `unconfirmed` or `No equivalent` are resolved: the definition lives at `.agents/agents/<name>.md` (global `~/.gemini/config/agents/`, plugin `plugins/<name>/agents/`) as Markdown with YAML frontmatter whose body is the system prompt, exactly the Claude Code shape; the frontmatter exposes `tools`, `model` (`inherit`, `flash`, `pro`), `commandExecutionPolicy`, `mcpServers`, `skills`/`plugins`, and the `subagent`/`mainAgent` role gates; nesting is capped at depth 10. Added rows for the `inherit`/`branch`/`share` workspace option (a `branch` subagent gets its own git worktree, unique among the three), the running/idle/killed lifecycle, and inter-agent messaging.
- Resolved the MCP precedence cell in `06-mcp-servers.md` from `unconfirmed` to workspace over global, sourced from the new `cli/mcp` page, and added the `cwd` and `disabled` keys plus a transport row.
- Sharpened the Antigravity global skills path in `03-skills.md` to name both paths the two doc sets disagree on, rather than picking one silently.
- Replaced every dead Antigravity `assets/docs/....md` source URL with the server-rendered page URL, and re-pointed every Codex `developers.openai.com/codex/*.md` source at the `learn.chatgpt.com/docs/*` location it now redirects to. All 51 source URLs in the knowledge base verified reachable.
- Fixed the maintenance pointer in `SKILL.md`, `README-cn.md`, and `00-context-index.md`. It was a relative path to `coding-agent-concept-mapping-builder`, which is unresolvable by construction: the knowledge base ships inside the `coding-agent-docs` plugin and the builder deliberately does not, so no number of `../` hops reaches it from an installed plugin. Now an absolute GitHub URL, stated in one sentence that also says the builder is maintainer side and not shipped.

## [0.1.2] - 2026-07-29

- Add the `plugins-and-marketplaces` concept (09), covering the plugin package
  and manifest, bundled component types, marketplace catalogs and source types,
  and install location, scope, and enablement.

## [0.1.1] - 2026-07-03

- Initial release.
- Add the following concepts:
    - project-prompt
    - project-settings
    - skills
    - custom-commands
    - hooks
    - mcp-servers
    - subagents
    - permissions
