---
name: port-codex-to-claude-code-checker
description: Read-only review of how completely a project's Codex configuration has been ported to Claude Code. Scans both sides, compares them against the coding-agent-concept-mapping knowledge base, and writes a gap report to tmp/review-port-codex-to-claude-code.md. Makes no changes to the project config. Use to audit a Codex to Claude Code migration.
argument-hint: [project path]
allowed-tools: Read, Write, Glob, Grep, Skill
---

# Check port from Codex to Claude Code

Audits a project migration from Codex to Claude Code without
changing anything. It runs the same scan and mapping logic as the
`port-codex-to-claude-code` skill, but instead of writing target files it records what
is missing or mismatched and how to fix it, then saves a structured review
report.

If the user passed an argument (`$ARGUMENTS`), treat it as the path to the project
to review. Otherwise use the current working directory.

## Read only

This skill never creates, edits, or deletes any project configuration. Its one
and only write is the review report at `tmp/review-port-codex-to-claude-code.md` inside
the project. If that file already exists, overwrite it.

## Do not hardcode the concept list

The set of portable configuration concepts (project prompt, settings, skills,
custom commands, hooks, MCP servers, subagents, permissions, and more) grows over
time. Never rely on a list baked into this skill. The authoritative, current list
lives in the concept mapping knowledge base, which you read fresh every run. The
`../coding-agent-concept-mapping/...` paths below are relative to this skill's own directory in
the toolkit repo, not to the project being reviewed.

- **Concept roster plus each agent's primary file or location:**
  `../coding-agent-concept-mapping/ref/00-context-index.md`. Every concept it lists is in
  scope. Its per concept table names the Codex and Claude Code
  file or location.
- **Detailed mapping and porting-in notes for one concept:** the detail file
  `../coding-agent-concept-mapping/ref/XY-concept-name.md` linked from the index, or invoke
  the `coding-agent-docs:coding-agent-concept-mapping` skill with the concept name.

If a concept is not in the index, it has not been mapped yet. List it under
skipped concepts in the report; do not invent a mapping.

## Procedure

### 1. Resolve the project

Determine the project root from `$ARGUMENTS` or the current working directory.
All scanning stays inside it, and the only file you write is the report.

### 2. Load the concept roster

Read `../coding-agent-concept-mapping/ref/00-context-index.md`. For each concept, note the
Codex and Claude Code primary file or location from its table. This
roster is never hardcoded; it comes from the index every run.

### 3. Scan both sides

For each concept in the roster, look inside the project for both the
Codex artifact and the Claude Code artifact the index named, using
Glob and Grep. You are comparing what exists on the source side against what
exists on the target side.

### 4. Map and compare

For every concept present on the source side, open its detail file
`../coding-agent-concept-mapping/ref/XY-concept-name.md` (or invoke `coding-agent-docs:coding-agent-concept-mapping` with the
concept name) and determine what the Claude Code config should contain per the
mapping and the `Porting-in notes`. Compare that against what the target side
actually has. Consult the `coding-agent-docs:claude-code-docs` skill when you need current
Claude Code specifics. Classify each concept as fully ported, partially
ported, or missing on the target side.

### 5. Write the report

Write `tmp/review-port-codex-to-claude-code.md` inside the project, overwriting any
existing copy. Use this structure:

```
# Port review: Codex to Claude Code

Project: <resolved project path>

## Summary

- Concepts present on source: <n>
- Fully ported: <n>
- Gaps found: <n>
- Skipped (unmapped or no equivalent): <n>

## Gaps

### <concept name>
- Category: <concept name>
- Present on source: <the source artifact found>
- State on target: missing | partial | mismatched
- What is missing or wrong: <specific detail>
- Suggested change: <what to create or edit, described not applied>
- Priority / impact: <high | medium | low, and why>

（repeat one section per concept with a gap）

## Skipped concepts

- <concept>: <reason, e.g. no source artifact, unmapped, or No equivalent on target>
```

Record every concept that has a gap as its own section. Keep suggestions
descriptive: say what should change, never apply it.

### 6. Report to the user

Point the user at `tmp/review-port-codex-to-claude-code.md` and give a one line summary
of the counts. Do not apply any fix.

## Rules

- **Read only. Never modify project config.** The single allowed write is the
  report file.
- **The report path is fixed:** `tmp/review-port-codex-to-claude-code.md`, overwritten
  each run.
- **The concept list comes from the index, never from this skill.** Re-read
  `../coding-agent-concept-mapping/ref/00-context-index.md` every run.
- **Suggest, do not apply.** Every gap gets a described fix and a priority, with
  no edits to the project.
- **Ground target details in `coding-agent-docs:claude-code-docs`.** Do not judge a gap from
  memory of how Claude Code works.
