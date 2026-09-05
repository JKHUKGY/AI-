<!--
TEMPLATE: concept file skeleton for .claude/skills/coding-agent-docs/skills/coding-agent-concept-mapping/ref/XY-concept-name.md

Copy this file, rename it to the registered XY-concept-name.md, fill it in, and
delete every HTML comment. The final file must contain no comments.

Read ref/mapping-file-standard.md before using this. The rules there win over
any impression this skeleton gives.

Reminders baked into the shape below:
- H1 title has no dash, no quotes, no brackets. Write "Subagents", not "Sub-agents".
- Aspect sections are numbered H2, with a --- rule between every pair of H2.
- Column order is fixed: Claude Code (seed), then Codex, then Antigravity.
- The last table row is always "Porting-in notes", one note per tool, or "—" when nothing bites.
- Every non obvious fact comes from the doc skills, and lands in the Sources section.
- Use "No equivalent" (never a blank cell) when a tool lacks the aspect.
- Two to six aspect sections. Only keep a facet if the tools actually differ along it.
-->

# {Concept name, hyphen free}

<!-- One to three sentences: what this concept is, and the role it plays in an agent workflow. Prose only, no table. -->
{Definition paragraph.}

## 1. {Aspect title, for example File location and naming}

<!-- One to three sentences: what this facet is and why it matters when porting a setup between tools. -->
{Aspect intro.}

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| {dimension 1} | {value} | {value} | {value} |
| {dimension 2} | {value} | {value} | {value} |
| Porting-in notes | {what bites when arriving at Claude Code} | {what bites when arriving at Codex} | {what bites when arriving at Antigravity} |

---

## 2. {Aspect title, for example File format and syntax}

{Aspect intro.}

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| {dimension 1} | {value} | {value} | {value} |
| Porting-in notes | {note or —} | {note or —} | {note or —} |

<!--
Add or remove aspect sections as the concept demands, two to six total.
Renumber the H2 headings so they stay sequential. Keep a --- rule between each pair.
-->

---

## {N}. Sources

<!--
Record the doc pages actually read, grouped by tool, as title and URL.
This is what lets a later maintainer re verify without redoing the discovery.
-->

**Claude Code**

- {Doc title}: {URL}

**Codex**

- {Doc title}: {URL}

**Antigravity**

- {Doc title}: {URL}
