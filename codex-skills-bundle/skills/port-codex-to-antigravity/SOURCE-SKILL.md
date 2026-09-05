---
name: port-codex-to-antigravity
description: Port a project's Codex configuration to Antigravity, keeping the Codex files in place. Scans the project for Codex config artifacts, maps each to its Antigravity equivalent using the coding-agent-concept-mapping knowledge base, and creates or edits the matching Antigravity files. Use when migrating a repo from Codex to Antigravity.
argument-hint: [project path]
disable-model-invocation: true
allowed-tools: Read, Write, Edit, Glob, Grep, Skill
---

# Port Codex to Antigravity

Migrates one project's agent configuration from Codex (the source) to
Antigravity (the target). This is a project level port: it touches only files
inside the given project, never global or machine level config. Source files are
preserved. The Antigravity config is created alongside them, not on top of
them, so a repo ends up configured for both agents.

If the user passed an argument (`$ARGUMENTS`), treat it as the path to the project
to port. Otherwise use the current working directory.

## Do not hardcode the concept list

The set of portable configuration concepts (project prompt, settings, skills,
custom commands, hooks, MCP servers, subagents, permissions, and more) grows over
time. Never rely on a list baked into this skill. The authoritative, current list
lives in the concept mapping knowledge base, which you read fresh every run. All
paths below are relative to this skill's own directory in the toolkit repo, not
to the project being ported.

- **Concept roster plus each agent's primary file or location:**
  `../coding-agent-concept-mapping/ref/00-context-index.md`. Every concept it lists is in
  scope. Its per concept table names the Codex and Antigravity
  file or location, so it is both your worklist and your file map.
- **Detailed mapping and porting-in notes for one concept:** the detail file
  `../coding-agent-concept-mapping/ref/XY-concept-name.md` linked from the index, or invoke
  the `coding-agent-docs:coding-agent-concept-mapping` skill with the concept name.

If a concept is not in the index, it has not been mapped yet. Skip it and note it
in your report; do not invent a mapping.

## Procedure

### 1. Resolve the project

Determine the project root from `$ARGUMENTS` or the current working directory.
All scanning and all writing stays inside it.

### 2. Load the concept roster

Read `../coding-agent-concept-mapping/ref/00-context-index.md`. For each concept, note the
Codex primary file or location and the Antigravity primary file or
location from its table. This roster is never hardcoded; it comes from the index
every run.

### 3. Scan for source artifacts

For each concept in the roster, look inside the project for the Codex
file or location the index named, using Glob and Grep. Record which concepts are
actually present in this project. Those are the ones to port.

### 4. Map each present concept

For every concept found, open its detail file
`../coding-agent-concept-mapping/ref/XY-concept-name.md` (or invoke `coding-agent-docs:coding-agent-concept-mapping` with the
concept name) and read its aspect tables and the `Porting-in notes` row for
Antigravity. When the detail file is thin on a target specific point, consult
the `coding-agent-docs:antigravity-docs` skill for the current Antigravity file format and
field names, and `coding-agent-docs:codex-docs` for the source. Do not migrate from
memory; these tools change often.

### 5. Execute the migration

Create or edit the Antigravity file or files named by the mapping,
translating paths, filenames, formats, and field names per the concept detail.
Follow the Antigravity porting-in notes exactly, since that is where the
friction lives (renamed files, changed field keys, format shifts such as JSON to
TOML). Preserve every Codex file untouched: the target config coexists
with the source, it never replaces it.

### 6. Report

Tell the user, concept by concept: which source artifact was found, which target
file was created or edited, and anything skipped, such as an unmapped concept, a
`No equivalent` cell, or a detail you could not confirm in the docs.

## Rules

- **Project level only.** Never write outside the project or touch global or
  machine level config.
- **Never overwrite source files.** Source and target configs coexist.
- **The concept list comes from the index, never from this skill.** Re-read
  `../coding-agent-concept-mapping/ref/00-context-index.md` every run.
- **Ground target details in `coding-agent-docs:antigravity-docs`.** When the mapping is thin,
  check the current docs; do not guess field names or paths.
- **A concept absent from the index is out of scope.** Skip it and report it.
