---
name: codex-docs
description: Look up authoritative, up-to-date OpenAI Codex documentation covering the CLI, IDE extension, Codex app, cloud, subagents, skills, plugins and marketplaces, MCP, sandboxing, configuration, enterprise, and integrations. Use when the user asks how a Codex feature works, what a config field does, how to set up the CLI/IDE/app/cloud/skills/plugins/MCP, when troubleshooting a Codex error or unexpected behavior, or when you need to cite current official docs rather than rely on training-cutoff knowledge.
argument-hint: [topic or doc title]
allowed-tools: WebFetch
---

# Codex Docs

Lazy-loads the official OpenAI Codex documentation by reading the developer hub index at `https://developers.openai.com/llms.txt`, picking the most relevant page(s), and fetching them on demand. Always prefer this skill over recalling docs from memory — the docs change frequently.

If the user passed an argument (`$ARGUMENTS`), treat it as the topic to look up. Otherwise infer the topic from the conversation.

## When to use this skill

Use it whenever the question is about Codex itself or anything in its docs scope:

- Codex CLI: install, slash commands, command-line options, features, configuration, sandboxing, authentication
- Codex IDE extension, ChatGPT desktop app (automations, commands, worktrees, computer use, Chrome extension), and Codex cloud/web
- Concepts: sandboxing, customization, subagents, skills, plugins and marketplaces, MCP, cyber safety
- Enterprise setup, integrations (GitHub, Linear, Slack), Amazon Bedrock, the app-server protocol, troubleshooting

If the question is about the broader **OpenAI API / OpenAI SDK** (not the Codex coding agent), that lives under `developers.openai.com/api` and is out of scope for this skill.

## Where the docs actually live

OpenAI moved the Codex documentation body to a new host, and the old entry points are broken in ways that will silently derail this skill if you don't know about them. Three facts to internalize:

1. **`https://developers.openai.com/codex/llms.txt` is dead.** It 308-redirects to `https://learn.chatgpt.com/docs/llms.txt`, which returns 404. So does `codex/llms-full.txt`. The developer hub's own root index still advertises the broken `codex/llms.txt` link — ignore it.
2. **The working index is the hub-wide `https://developers.openai.com/llms.txt`.** It absorbed the entire Codex map into `## Codex — <Topic>` sections, in the same `- [Title](URL): description` format as before.
3. **Content pages redirect across hosts.** A `https://developers.openai.com/codex/<slug>.md` URL 308-redirects to `https://learn.chatgpt.com/docs/<slug>.md`. WebFetch does **not** follow cross-host redirects; it returns the redirect target to you instead. So fetching a Codex page normally takes two WebFetch calls. See step 3.

The slug mapping is not always a straight host swap (`codex/skills.md` lands on `docs/build-skills.md`, `codex/config-reference.md` lands on `docs/config-file/config-reference.md`), which is another reason never to hand-assemble a `learn.chatgpt.com` URL yourself. Let the redirect tell you.

Plugin-building pages are the exception: they live at `https://developers.openai.com/plugins/<path>.md` under the `## Plugins — <Topic>` sections and fetch directly with no redirect.

## Procedure

### 1. Read the index

```
WebFetch url=https://developers.openai.com/llms.txt
        prompt="Return the raw markdown of every section whose header starts with '## Codex —' or '## Plugins —'. I need each `- [Title](URL): description` line unmodified, including the section headers."
```

The hub index is ~840 lines covering several product families. Codex occupies the `## Codex — <Topic>` sections and plugin authoring occupies `## Plugins — <Topic>`; the rest (OpenAI API, Ads, Workspace Agents, Agentic Commerce) is out of scope, which is why the prompt above narrows to those two families rather than pulling the whole file.

Within the Codex and Plugins families, load all their entries in one shot and search them directly. Don't pre-filter further by topic header before you've seen the entries — the per-topic grouping is just how the page is laid out, not a reason to skip parts of the map.

### 2. Pick the right page(s)

Match the user's question against the **description** (text after the colon), not just the title. Then:

- Pick **1–3 pages per batch**, not more. The index is for triage, not bulk loading.
- One specific feature ("how do Codex slash commands work?") → one page.
- Cross-concept question ("how do skills relate to subagents?") → fetch each relevant page.
- Nothing in the index obviously matches → say so. Do not guess a URL.

### 3. Fetch the batch

For each chosen URL:

```
WebFetch url=<URL from index>
        prompt="<a question that captures what the user actually needs, not 'summarize this page'>"
```

A `developers.openai.com/codex/...` URL comes back as `REDIRECT DETECTED` pointing at `learn.chatgpt.com/docs/...`. That is expected, not an error. Call WebFetch again with the redirect URL and the same prompt. Count the pair as **one page** against the 9-page cap, and cite the `learn.chatgpt.com` URL that actually served the content.

A handful of index entries are stale upstream and 404 even after the redirect (roughly 5 of ~137 Codex entries, such as `codex/overview.md` and `codex/resources.md`). Treat one of those as "this page no longer exists", pick a different entry, and do not try to repair the slug by hand.

### 4. Evaluate, then loop or answer

After each batch, judge whether the fetched pages actually answer the user's question:

- **Enough** → answer, grounded in the fetched content. Cite the doc page (title + URL) when stating non-obvious facts so the user can verify.
- **Not enough** (the answer lives on a page you haven't read, or a fetched page pointed to another) → go back to step 2, pick the next 1–3 pages from the index, and fetch again.
- Keep looping until you can answer, up to a **default cap of 9 pages total** across all batches.
- **Still not enough at 9 pages** → stop. Tell the user honestly what you've read, what's still missing, and ask whether they want you to keep reading more pages. Don't silently blow past the cap or pad the answer with guesses.

## Rules

- **Never invent a doc URL.** If a page isn't in the index, it does not exist — say so instead of fabricating a slug. This applies double to `learn.chatgpt.com` URLs: reach them only by following a redirect, never by rewriting a host yourself.
- **Don't skip step 1**, even if you think you remember the right URL. Doc slugs get renamed; the index is the source of truth.
- **Use `developers.openai.com/llms.txt`, not `codex/llms.txt`.** The Codex-specific index returns 404 through its redirect. If you find yourself staring at a 404 on an index, this is why.
- **Loop in small batches, cap at 9 pages.** Fetch 1–3, check if that's enough, fetch more only if it isn't. A redirect pair counts as one page. If 9 pages still don't answer it, ask the user before reading more — don't grind through the whole index or fabricate the gap.
- **Stay in scope.** This skill covers the Codex product family: the `## Codex —` and `## Plugins —` sections of the hub index, whichever host currently serves them (`developers.openai.com/codex/*`, `developers.openai.com/plugins/*`, and their `learn.chatgpt.com/docs/*` redirect targets). For the general OpenAI API, point the user to `developers.openai.com/api`.
- **Cite the URL that served the content.** After a cross-host redirect that is the `learn.chatgpt.com/docs/<slug>.md` form, not the `developers.openai.com` one you started from.
- **Pass through what the docs say.** Don't merge aggressively with prior knowledge — the user wants current authoritative behavior, not a synthesis.
