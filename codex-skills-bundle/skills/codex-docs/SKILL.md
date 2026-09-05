---
name: codex-docs
description: Look up authoritative, up-to-date OpenAI Codex documentation covering
  the CLI, IDE extension, Codex app, cloud, subagents, skills, plugins and marketplaces,
  MCP, sandboxing, configuration, enterprise, and integrations. Use when the user
  asks how a Codex feature works, what a config field does, how to set up the CLI/IDE/app/cloud/skills/plugins/MCP,
  when troubleshooting a Codex error or unexpected behavior, or when you need to cite
  current official docs rather than rely on training-cutoff knowledge.
---

# Codex compatibility entrypoint

Read [SOURCE-SKILL.md](SOURCE-SKILL.md) in full, then follow its original workflow. That file and all original supporting resources are preserved byte for byte. Apply only these host compatibility mappings:

- `Read`, `Glob`, and `Grep`: use available file-reading and search tools; `Bash`: use the shell; `Write` and `Edit`: use file editing tools; `WebFetch` and `WebSearch`: use available browsing tools. If a required capability is unavailable, report it rather than pretending to execute it.
- `Skill`, `/skill-name`, and `coding-agent-docs:skill-name`: load the corresponding sibling `../skill-name/SKILL.md` and follow it. The Codex user invocation is `$skill-name`.
- `$ARGUMENTS` means the arguments supplied in the user's request, not an automatically populated shell variable. Preserve the original defaults when no arguments are supplied.
- `${CLAUDE_SKILL_DIR}` means this skill's directory. `${CLAUDE_PLUGIN_ROOT}/skills/<name>/...` resolves to the sibling `../<name>/...`. Substitute concrete paths before executing commands; do not assume Claude environment variables exist.
- Resolve ordinary relative resource paths from this directory. When reading bundled resources referenced under `.claude/skills/coding-agent-docs/skills/<name>/` or `.claude/skills/<name>/`, use the corresponding sibling skill directory. Paths describing a target project's Claude configuration, migration inputs/outputs, examples, or maintainer source files retain their original meaning; do not globally replace them. Maintenance of the upstream repository requires that source checkout.
- The original `argument-hint` is usage documentation. The original `allowed-tools` describes intended capabilities and is not a Codex permission enforcement mechanism. Preserve the workflow's operation limits using the actual host permissions. Explicit-only invocation is represented in `agents/openai.yaml` where applicable.

Do not rewrite the source content, change its subject from Claude to Codex, or invent an equivalent for unsupported behavior. Original examples and templates remain unchanged.
