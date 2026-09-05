---
name: {{PORT_SKILL_NAME}}
description: Port a project's {{SOURCE_NAME}} configuration to {{TARGET_NAME}}, keeping the {{SOURCE_NAME}} files in place. Scans the project for {{SOURCE_NAME}} config artifacts, maps each to its {{TARGET_NAME}} equivalent using the coding-agent-concept-mapping knowledge base, and creates or edits the matching {{TARGET_NAME}} files. Use when migrating a repo from {{SOURCE_NAME}} to {{TARGET_NAME}}.
argument-hint: [project path]
disable-model-invocation: true
allowed-tools: Read, Write, Edit, Glob, Grep, Skill
---

# Port {{SOURCE_NAME}} to {{TARGET_NAME}}

Migrates one project's agent configuration from {{SOURCE_NAME}} (the source) to
{{TARGET_NAME}} (the target). This is a project level port: it touches only files
inside the given project, never global or machine level config. Source files are
preserved. The {{TARGET_NAME}} config is created alongside them, not on top of
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
  scope. Its per concept table names the {{SOURCE_NAME}} and {{TARGET_NAME}}
  file or location, so it is both your worklist and your file map.
- **Detailed mapping and porting-in notes for one concept:** the detail file
  `../coding-agent-concept-mapping/ref/XY-concept-name.md` linked from the index, or invoke
  the `coding-agent-concept-mapping` skill with the concept name.

If a concept is not in the index, it has not been mapped yet. Skip it and note it
in your report; do not invent a mapping.

## Procedure

### 1. Resolve the project

Determine the project root from `$ARGUMENTS` or the current working directory.
All scanning and all writing stays inside it.

### 2. Load the concept roster

Read `../coding-agent-concept-mapping/ref/00-context-index.md`. For each concept, note the
{{SOURCE_NAME}} primary file or location and the {{TARGET_NAME}} primary file or
location from its table. This roster is never hardcoded; it comes from the index
every run.

### 3. Scan for source artifacts

For each concept in the roster, look inside the project for the {{SOURCE_NAME}}
file or location the index named, using Glob and Grep. Record which concepts are
actually present in this project. Those are the ones to port.

### 4. Map each present concept

For every concept found, open its detail file
`../coding-agent-concept-mapping/ref/XY-concept-name.md` (or invoke `coding-agent-concept-mapping` with the
concept name) and read its aspect tables and the `Porting-in notes` row for
{{TARGET_NAME}}. When the detail file is thin on a target specific point, consult
the `{{TARGET_DOCS_SKILL}}` skill for the current {{TARGET_NAME}} file format and
field names, and `{{SOURCE_DOCS_SKILL}}` for the source. Do not migrate from
memory; these tools change often.

### 5. Execute the migration

Create or edit the {{TARGET_NAME}} file or files named by the mapping,
translating paths, filenames, formats, and field names per the concept detail.
Follow the {{TARGET_NAME}} porting-in notes exactly, since that is where the
friction lives (renamed files, changed field keys, format shifts such as JSON to
TOML). Preserve every {{SOURCE_NAME}} file untouched: the target config coexists
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
- **Ground target details in `{{TARGET_DOCS_SKILL}}`.** When the mapping is thin,
  check the current docs; do not guess field names or paths.
- **A concept absent from the index is out of scope.** Skip it and report it.
