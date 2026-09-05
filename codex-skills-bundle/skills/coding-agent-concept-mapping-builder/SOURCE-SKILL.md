---
name: coding-agent-concept-mapping-builder
description: Author and maintain the cross tool concept mapping knowledge base under .claude/skills/coding-agent-docs/skills/coding-agent-concept-mapping/. Use when adding a new concept, refreshing an existing XY-concept-name.md against current docs, or rolling the concept files up into 00-context-index.md. Grounds every claim in the claude-code-docs, codex-docs, and antigravity-docs skills and follows ref/mapping-file-standard.md.
argument-hint: [concept name or XY number]
allowed-tools: Read, Write, Edit, WebFetch, Skill
---

# Concept Mapping Builder

Builds and maintains the concept mapping knowledge base that lives in the
sibling skill at `.claude/skills/coding-agent-docs/skills/coding-agent-concept-mapping/`. That knowledge base explains
how each project level configuration concept in Claude Code maps onto Codex and
Antigravity, and what to watch when porting a setup between them. This builder is
how those files get written and kept current. The `coding-agent-concept-mapping` skill only
reads them at answer time.

If the user passed an argument (`$ARGUMENTS`), treat it as the concept to build
or update. Otherwise infer it from the conversation, or ask which concept.

## What it maintains

Two kinds of file, both under `.claude/skills/coding-agent-docs/skills/coding-agent-concept-mapping/ref/`:

- `XY-concept-name.md` — one detail file per concept, the real content. This is
  authored or updated first.
- `00-context-index.md` — a single short rollup that indexes every concept.
  This is regenerated from the detail files, second.

The exact format of both is fixed by [ref/mapping-file-standard.md](ref/mapping-file-standard.md).
A copy ready skeleton for a detail file is [ref/concept-file-template.md](ref/concept-file-template.md).
Read the standard before writing anything.

## When to use

- Adding a new concept to the knowledge base.
- Refreshing an existing detail file because a tool changed its docs or behavior.
- Reconciling `00-context-index.md` after one or more detail files changed.

## Procedure

### 1. Identify the concept and claim its slot

Resolve the concept to a registry row in the standard: its two digit number and
its `XY-concept-name.md` filename. If it is new, add a registry row first so the
number is reserved, then proceed. Confirm whether you are creating a fresh file
or updating an existing one by reading the current detail file if it exists.

### 2. Read the standard

Read [ref/mapping-file-standard.md](ref/mapping-file-standard.md) in full every
time. It defines the tool columns and their seed order, the aspect and table
shape, the O(N) porting-in row, the sourcing rules, how to handle a missing
equivalent, and the markdown style constraints. Do not author from memory of it.

### 3. Research each tool from its official docs

Gather the facts one tool at a time, always through the doc lookup skills, never
from training memory. Start with Claude Code, the seed, since it frames the
concept and its aspects. Then find the equivalent in the other two.

- Claude Code column: the `claude-code-docs` skill.
- Codex column: the `codex-docs` skill.
- Antigravity column: the `antigravity-docs` skill.

Decide the aspects from what actually differs across the tools. Keep the doc page
titles and URLs you relied on. They become the `Sources` section.

### 4. Write or update the detail file first

Author `.claude/skills/coding-agent-docs/skills/coding-agent-concept-mapping/ref/XY-concept-name.md` to the standard.
Start from `ref/concept-file-template.md`, fill every cell, delete all comments,
and record sources. Use `No equivalent` rather than a blank when a tool lacks an
aspect. When updating, change only what the refreshed docs require and keep the
rest stable so diffs stay reviewable.

### 5. Roll up the index second

Only after the detail file is correct, update `00-context-index.md`: its blurb,
the small per tool location table, and the link for this concept. Its summary
must agree with the detail file. If they disagree, the detail file is right and
the index is what you fix. For a brand new concept, insert its section in
registry order.

### 6. Report

Tell the user which detail file changed, whether the index was touched, which
doc pages grounded the new facts, and any cell you had to mark `No equivalent`
or leave `unconfirmed`.

## Rules

- **Detail first, index second, always.** The index only summarizes what a
  detail file already establishes. Never write the index for content that does
  not exist yet.
- **Ground every non obvious claim in current docs.** Route Claude Code facts
  through `claude-code-docs`, Codex through `codex-docs`, Antigravity through
  `antigravity-docs`. If the docs do not confirm it, mark it `unconfirmed` or
  drop the row. Do not backfill from memory.
- **Claude Code is the seed.** It is always the first tool column and it frames
  the concept vocabulary. Other tools are described relative to it.
- **The standard wins.** When in doubt about structure, naming, or table shape,
  [ref/mapping-file-standard.md](ref/mapping-file-standard.md) is authoritative.
- **No blank cells.** A tool without an equivalent gets `No equivalent` and a
  few words of context, never an empty cell.
- **Never point at this builder with a relative path.** The knowledge base ships
  inside the `coding-agent-docs` plugin and this builder does not, so a relative
  link is broken by construction once the plugin is installed elsewhere. Use the
  absolute URL, and say that the builder does not ship with the plugin:
  `https://github.com/MacHu-GWU/shsk_coding_agent_docs-project/blob/main/.claude/skills/coding-agent-concept-mapping-builder/SKILL.md`
- **Stay in scope.** Only project level, portable configuration concepts belong
  in the knowledge base. If a concept exists in only one tool, it does not go in.
