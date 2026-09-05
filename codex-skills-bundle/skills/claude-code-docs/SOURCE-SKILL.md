---
name: claude-code-docs
description: Look up authoritative, up-to-date Claude Code documentation covering the CLI, settings, permissions, hooks, MCP, skills, plugins and marketplaces, subagents, agent teams, workflows, worktrees, sandboxing, channels, routines, scheduled tasks, the desktop/web/mobile/Slack/IDE surfaces, code review, the Agent SDK (Python and TypeScript), gateways, Bedrock/Vertex/Foundry deployment, enterprise admin, and troubleshooting. Use when the user asks how a Claude Code feature works, what a config field does, how to set up hooks/MCP/skills/subagents/plugins, when troubleshooting a Claude Code error or unexpected behavior, or when you need to cite current official docs rather than rely on training-cutoff knowledge. Also triggers on Chinese requests such as 查一下 Claude Code 文档、Claude Code 官方文档怎么说、Claude Code 的 hooks/MCP/skills/权限/配置 怎么用.
argument-hint: [topic or doc title]
allowed-tools: WebFetch
---

# Claude Code Docs

Answers Claude Code questions from the official docs on demand: WebFetches the `llms.txt`
index (a flat list of every page, with a real description per entry), picks the pages that
match, and fetches those as raw markdown. Always prefer this skill over recalling docs from
memory — the docs change faster than training data.

If the user passed an argument (`$ARGUMENTS`), treat it as the topic to look up. Otherwise
infer the topic from the conversation.

## When to use this skill

Use it whenever the question is about Claude Code itself or anything in its docs scope:

- **CLI and session surface** — slash commands, CLI flags, interactive mode, keybindings,
  status line, output styles, fullscreen, voice dictation, sessions, checkpointing, worktrees
- **Configuration** — settings, environment variables, permissions and permission modes,
  memory/CLAUDE.md, model config, the `.claude` directory, server-managed settings
- **Extensibility** — hooks, MCP, skills, plugins, plugin marketplaces, subagents, agent
  teams, dynamic workflows, channels, routines, scheduled tasks, computer use
- **Agent SDK** (Python and TypeScript) — agent loop, sessions, streaming, custom tools,
  hooks, permissions, structured outputs, tool search, hosting, observability
- **Surfaces and integrations** — desktop app, web, mobile, Slack, Chrome, VS Code, JetBrains,
  devcontainers, GitHub Actions, GitLab CI/CD
- **Enterprise and deployment** — admin setup, Bedrock, Google Cloud, Microsoft Foundry, LLM
  gateways, Claude apps gateway, network config, analytics, costs, security, data usage
- **Reference and troubleshooting** — tools reference, error reference, glossary, changelog,
  the weekly `What's new` pages, troubleshooting

Out of scope: the **Anthropic API / Anthropic SDK** itself (Messages API, pricing, model ids).
Use the `claude-api` skill for that.

## How this site works

Measured 2026-07-30; full fact sheet in [references/mechanism.md](references/mechanism.md).

- **Index**: `https://code.claude.com/docs/llms.txt` — 38,847 B (~9,700 tokens), 174 entries,
  100% with prose descriptions. One flat `## Docs` section; there is no sub-section routing to
  lean on, so the descriptions are the only triage signal.
- **Content**: every index URL already ends in `.md` and serves raw markdown as-is. Measured
  `hooks.md` = 242,078 B of markdown vs 2,423,751 B for the HTML page — ~90% cheaper. There is
  no separate `.md` twin to construct; use the URL exactly as the index gives it.
- **Page sizes vary by 25×**: measured 10,628 B (`troubleshooting.md`) to 272,484 B
  (`settings.md`); `hooks.md` 242,078 B, `cli-reference.md` 104,140 B, `mcp.md` 80,866 B,
  `overview.md` 16,445 B. Ask WebFetch a pointed question — a vague prompt on a 270 KB page
  wastes most of the fetch.
- **Gotcha — `llms-full.txt`**: `https://code.claude.com/docs/llms-full.txt` is 6,556,407 B
  (~1.64M tokens). It is a full-text dump, not an index. Never fetch it.

## Procedure

### 1. Read the index

```
WebFetch url=https://code.claude.com/docs/llms.txt
        prompt="Return the raw markdown. I need every `- [Title](URL): description` line unmodified."
```

Each entry is `- [Title](https://code.claude.com/docs/en/<slug>.md): description`.

Don't skip this step, even if you think you remember the right URL. Slugs get renamed and
pages get added weekly; the index is the source of truth.

### 2. Pick the right page(s)

Match against the **description** (the text after the colon), not just the title. Then:

- Pick **1–3 pages per batch**, not more. The index is for triage, not bulk loading.
- One specific feature ("how do hooks work?") → one page.
- Cross-concept question ("how do skills relate to subagents?") → fetch each relevant page.
- Note that some topics live in two places — e.g. `hooks.md` (reference) vs `hooks-guide.md`
  (how-to) vs `agent-sdk/hooks.md` (SDK). Pick the one matching what was actually asked.

### 3. If nothing in the index looks like a match

Do **not** conclude the topic is undocumented. Escalate, in order:

1. **Widen with synonyms.** The docs' word is often not the user's. Measured on this index:
   "resume" appears in **zero** titles but in five descriptions (it lives under
   `sessions.md`, *Manage sessions*). Same shape: "auto-approve" → *permission modes*;
   "parallel checkouts" → *worktrees*; "cron" → *scheduled tasks* / *routines*.
2. **Translate a non-English query into English first.** This index is English-only. Measured:
   the Chinese query `钩子` scores **0** matches while `hook` scores 17 — a non-English miss
   says nothing about coverage. Never report "not documented" off a non-English search.
3. **Ask "what recently changed?"** — `whats-new/index.md` plus the 18 weekly
   `whats-new/2026-wNN.md` pages cover new features that older, stabler pages don't mention yet.
4. **Only then** say it is not in the docs, and state what you searched.

### 4. Fetch the batch

For each chosen URL, use it verbatim from the index (it already ends in `.md`):

```
WebFetch url=<URL from index>
        prompt="<a question that captures what the user actually needs, not 'summarize this page'>"
```

### 5. Evaluate, then loop or answer

After each batch, judge whether the fetched pages actually answer the question:

- **Enough** → answer, grounded in the fetched content. Cite the doc page (title + URL) when
  stating non-obvious facts so the user can verify.
- **Not enough** (the answer lives on a page you haven't read, or a fetched page pointed to
  another) → go back to step 2, pick the next 1–3 pages, and fetch again.
- Keep looping to a **default cap of 9 pages** total across all batches.
- **Still not enough at 9 pages** → stop. Tell the user what you've read, what's still missing,
  and ask whether to keep going. Don't silently blow past the cap or pad the answer with guesses.

## Context budget

| Step | Cost | Notes |
| :--- | :--- | :--- |
| index | ~9,700 tok | once per question; re-use it across batches in the same turn |
| page | ~3k–68k tok raw | 1–3 per batch; WebFetch reduces this before it reaches context |

Typical question: index + 1–2 pages. Re-read the index only if the conversation moves to an
unrelated topic — not between batches.

## Rules

- **Never invent a doc URL.** If a page isn't in the index, it does not exist — say so instead
  of fabricating a slug. A 404 on an index URL means the index is stale; re-run
  `/docs-skill-builder check` on this skill.
- **Never fetch `llms-full.txt`** (6.5 MB / ~1.64M tokens).
- **Loop in small batches, cap at 9 pages.** Fetch 1–3, check if that's enough, fetch more only
  if it isn't. Don't grind through the index or fabricate the gap.
- **Stay in scope.** This skill covers `code.claude.com/docs/*` only. For the Anthropic API use
  `claude-api`.
- **Pass through what the docs say.** Don't merge aggressively with prior knowledge — the user
  wants current authoritative behavior, not a synthesis.
