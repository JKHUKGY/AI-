---
name: port-coding-agent-skill-generator
description: Generate or update the paired port and checker skills that migrate a project's configuration from one AI coding agent to another. Use when you need to (re)create a port-<source>-to-<target> doer skill and its port-<source>-to-<target>-checker review skill, for example when invoked as /port-coding-agent-skill-generator cc to cdx or /port-coding-agent-skill-generator claude code to codex.
argument-hint: <source> to <target>
disable-model-invocation: true
allowed-tools: Read, Write, Edit
---

# Port Skill Generator

The single maintenance point for the family of port skills. There are three
coding agents (Claude Code, Codex, Antigravity) and every ordered pair needs two
skills: a `port-<source>-to-<target>` doer that performs a project level
migration, and a `port-<source>-to-<target>-checker` that reviews one read only.
That is twelve skills. Rather than hand maintain twelve files, this generator
stamps them all from two templates so they stay identical in structure and only
differ in the source and target agent. To change how every port skill behaves,
edit a template here and regenerate, never edit the generated skills by hand.

If the user passed an argument (`$ARGUMENTS`), it names the migration direction,
in the form `<source> to <target>` (for example `cc to cdx`, `claude code to
codex`, `ag to cc`). Parse it. If it is missing or ambiguous, ask which direction.

## What it produces

Two skills per run, both under this repo's `.claude/skills/`:

- `.claude/skills/<port-name>/SKILL.md` from [ref/port-skill-template.md](ref/port-skill-template.md)
- `.claude/skills/<checker-name>/SKILL.md` from [ref/checker-skill-template.md](ref/checker-skill-template.md)

Each run creates the two directories if absent and overwrites the two `SKILL.md`
files if present. Regenerating is how a port pair gets updated.

## The agent roster is hardcoded, the concept list is not

Draw a sharp line between two kinds of knowledge:

- **The agent roster** (which agents exist, their canonical names, slugs, and doc
  lookup skills) is small and stable. Adding a fourth agent is a deliberate,
  rare event. It is fine to resolve it from the table below. The authoritative
  roster and the fixed tool column order live in the concept mapping standard at
  `../coding-agent-concept-mapping-builder/ref/mapping-file-standard.md` (section 2); keep the
  table below in sync with it, and if an agent is missing here, that standard is
  the source of truth.
- **The concept list** (project prompt, settings, skills, commands, hooks, MCP
  servers, subagents, permissions, and whatever gets added next) grows
  continually. Never bake it into this generator or into the templates. The
  generated skills read it fresh at run time from the concept mapping index. The
  templates already do this; do not add a concept list to them.

## Agent resolution table

Match each side of the direction against this table, case insensitively. Trim
surrounding whitespace and treat internal spaces and hyphens as equivalent
(`claude code` == `claude-code`).

| Accepted inputs | Canonical name | Slug | Docs skill |
|---|---|---|---|
| `cc`, `claude`, `claude code`, `claude-code`, `claudecode` | Claude Code | `claude-code` | `claude-code-docs` |
| `cdx`, `codex` | Codex | `codex` | `codex-docs` |
| `ag`, `antigravity`, `gemini` | Antigravity | `antigravity` | `antigravity-docs` |

## Procedure

### 1. Parse the direction

Split `$ARGUMENTS` on the word `to` (surrounded by spaces) into a source phrase
and a target phrase. Resolve each phrase through the agent resolution table to a
canonical name, slug, and docs skill. If either side does not resolve, or the two
sides resolve to the same agent, stop and ask the user to restate the direction.

### 2. Derive the substitution values

From the two resolved agents, compute every placeholder the templates use:

| Placeholder | Value |
|---|---|
| `{{SOURCE_NAME}}` | source canonical name, e.g. `Claude Code` |
| `{{TARGET_NAME}}` | target canonical name, e.g. `Codex` |
| `{{SOURCE_SLUG}}` | source slug, e.g. `claude-code` |
| `{{TARGET_SLUG}}` | target slug, e.g. `codex` |
| `{{SOURCE_DOCS_SKILL}}` | source docs skill, e.g. `claude-code-docs` |
| `{{TARGET_DOCS_SKILL}}` | target docs skill, e.g. `codex-docs` |
| `{{PORT_SKILL_NAME}}` | `port-{{SOURCE_SLUG}}-to-{{TARGET_SLUG}}` |
| `{{CHECKER_SKILL_NAME}}` | `{{PORT_SKILL_NAME}}-checker` |

### 3. Read the templates

Read [ref/port-skill-template.md](ref/port-skill-template.md) and
[ref/checker-skill-template.md](ref/checker-skill-template.md) in full. They are
complete `SKILL.md` files with `{{PLACEHOLDER}}` markers and no author comments to
strip.

### 4. Write the port skill

Substitute every placeholder in the port template and write the result to
`.claude/skills/{{PORT_SKILL_NAME}}/SKILL.md`, overwriting if it exists. Verify no
`{{` marker survives.

### 5. Write the checker skill

Do the same with the checker template, writing to
`.claude/skills/{{CHECKER_SKILL_NAME}}/SKILL.md`.

### 6. Report

Tell the user the two skill paths written, the resolved direction (source to
target with canonical names), and remind them that these files are generated:
future changes belong in the templates here, followed by a regenerate.

## Rules

- **Two templates, one truth.** All behavior common to every port pair lives in
  the templates. Never diverge a single generated skill by hand.
- **Do not hardcode concepts.** Neither this generator nor the templates carry a
  concept list. The generated skills read the concept roster from
  `coding-agent-concept-mapping/ref/00-context-index.md` every run.
- **Validate the direction.** Both sides must resolve to distinct known agents.
  Refuse a same agent or unknown agent direction.
- **Overwrite to update.** Regenerating a pair replaces its two `SKILL.md` files;
  that is the intended update path.
- **Keep the roster in sync.** The agent table mirrors
  `../coding-agent-concept-mapping-builder/ref/mapping-file-standard.md` section 2. If a new
  agent is added there, add its row here before generating its pairs.
