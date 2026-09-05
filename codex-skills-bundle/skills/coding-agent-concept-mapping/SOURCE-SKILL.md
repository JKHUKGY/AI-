---
name: coding-agent-concept-mapping
description: Cross tool concept mapping knowledge base for AI coding agents. Use when you need to know how a project level configuration concept (project prompt, settings, skills, custom commands, hooks, MCP servers, subagents, permissions, plugins and marketplaces) corresponds across Claude Code, Codex, and Antigravity, or how to port such a setup from one tool to another.
argument-hint: [concept name]
allowed-tools: Read
---

# Concept Mapping

A knowledge base that aligns the project level configuration concepts of three
AI coding agents. Claude Code is the seed: every concept is named and framed
from the Claude Code point of view, and the Codex and Antigravity columns
describe how each realizes the same idea, or the fact that it has no equivalent.
The point is not three separate glossaries but the alignment between them, plus
concrete notes on what bites when porting a setup from one tool into another.

If the user passed an argument (`$ARGUMENTS`), treat it as the concept to look
up. Otherwise infer it from the conversation.

## How to use this skill

Read the index first, then load only the detail file you need.

### 1. Read the index

Start at [ref/00-context-index.md](ref/00-context-index.md). It lists every
concept with a one line blurb and each tool's primary file or location, and it
links to the detail file for each. Use it to find the concept that matches the
question. Do not answer a mapping question from memory when a detail file exists.

### 2. Load the relevant detail file

Each concept has a detail file named `ref/XY-concept-name.md`, discovered
through the index. Open the one that matches and read the aspect that the
question is about. Each detail file breaks the concept into aspects (file
location, format, scope, load behavior, and so on), and each aspect is a table
comparing the three tools, with a final `Porting-in notes` row saying what to
watch when arriving at each tool.

### 3. Answer, grounded in the file

Answer from what the detail file states, and cite the aspect or the `Sources`
section when the fact is not obvious. If the index has no matching concept, say
so rather than guessing. A concept absent from the knowledge base has not been
mapped yet.

## Maintenance

Every file here is generated. Do not add new facts by hand. To add a concept,
refresh one against current docs, or fix a mapping, use the maintainer side
`coding-agent-concept-mapping-builder` skill, which grounds every claim in the
`coding-agent-docs:claude-code-docs`, `coding-agent-docs:codex-docs`, and
`coding-agent-docs:antigravity-docs` skills, and which does not ship with this
plugin: https://github.com/MacHu-GWU/shsk_coding_agent_docs-project/blob/main/.claude/skills/coding-agent-concept-mapping-builder/SKILL.md
