# Concept Mapping File Standard

This document is the authoritative specification for every file the
`coding-agent-concept-mapping-builder` skill writes into `.claude/skills/coding-agent-docs/skills/coding-agent-concept-mapping/`.
It exists so that many independent authoring sessions can each produce one
concept file and still end up with a knowledge base that reads as if a single
hand wrote it. When a rule here conflicts with habit or with the old
`tmp/coding-agent-concept-mapping` files, this document wins.

Two kinds of artifact are governed here. The per concept detail files named
`XY-concept-name.md`, and the single rollup index named `00-context-index.md`.
The detail files carry the real content. The index is a short triage layer
generated from them.

---

## 1. Purpose and scope

The concept mapping knowledge base answers one question: a given
project level configuration concept exists in Claude Code, so how does the same
idea show up in Codex and in Antigravity, and what should someone watch for when
carrying a setup from one tool into another. The value is not a pile of facts
about each tool in isolation. The value is the alignment between them, laid out
so a reader can convert their mental model or their actual config from one tool
to the next.

Scope is deliberately narrow. Only project level, portable configuration
concepts belong here. Things a user keeps in a repository and would expect to
re-express when switching agents: the project prompt file, settings, skills,
commands, hooks, MCP servers, subagents, permissions, and their close
relatives. One off UI features, pricing, model catalogs, and anything that does
not translate into a file or a config decision stay out.

---

## 2. Tool columns and the seed model

Claude Code is the seed. Every concept is named and framed from the Claude Code
point of view, and Claude Code is always the first tool column. The other tools
are described by how they realize that same concept, or by the fact that they do
not realize it at all. This keeps the vocabulary stable and stops the knowledge
base from splintering into three parallel glossaries.

Each column maps the tool's command line interface as the canonical surface. All
three tools ship a CLI, and the CLI configuration is the common denominator, so
the knowledge base compares CLI against CLI and does not mix in editor panels.
Where a tool also has an IDE or other GUI, treat its settings as compatible with
and derived from the CLI configuration, and mention the GUI only when it diverges
from the CLI or expresses something the CLI cannot. This matters most for
Antigravity, which ships an IDE, a CLI, and an SDK: map the Antigravity CLI, and
read the CLI docs, not only the general or IDE pages. When the CLI docs are thin
on a point, mark it `unconfirmed` rather than substituting IDE panel behavior.

Every comparison table uses the same three columns, in this fixed order:

| Position | Column header | Source of truth |
|---|---|---|
| 1 | `Claude Code` | the `claude-code-docs` skill |
| 2 | `Codex` | the `codex-docs` skill |
| 3 | `Antigravity` | the `antigravity-docs` skill |

When a fourth tool is added later, it becomes a fourth column appended on the
right. No existing column changes. This is what keeps the design O(N): adding a
tool touches one new column per table, never the relationships between the
tools already present.

---

## 3. File layout, naming, and the concept registry

Every file lives under `.claude/skills/coding-agent-docs/skills/coding-agent-concept-mapping/ref/`. Detail files are
named `XY-concept-name.md`, where `XY` is a two digit zero padded number and
`concept-name` is lower case kebab case. The number `00` is reserved for the
index. Concepts take `01` and up, in the order fixed by the registry below.

The filename may contain hyphens because it is a path, not prose. The H1 title
inside the file may not, because it is a heading governed by the markdown style
rules in section 8. So `07-subagents.md` holds a document whose H1 is
`# Subagents`, and `06-mcp-servers.md` holds one titled `# MCP servers`.

The registry is the single place that assigns numbers. Before creating a new
detail file, claim its row here so two sessions never mint the same number.

| Number | Concept | Filename | Scope in one line |
|---|---|---|---|
| 00 | Context index | `00-context-index.md` | Generated rollup and triage index |
| 01 | Project prompt | `01-project-prompt.md` | The persistent project instruction file (CLAUDE.md and its peers) |
| 02 | Project settings | `02-project-settings.md` | The project config file, its format and load order |
| 03 | Skills | `03-skills.md` | Reusable skill packages and their SKILL.md contract |
| 04 | Custom commands | `04-custom-commands.md` | User defined slash commands |
| 05 | Hooks | `05-hooks.md` | Lifecycle event scripts and their control flow |
| 06 | MCP servers | `06-mcp-servers.md` | Model Context Protocol integration and config |
| 07 | Subagents | `07-subagents.md` | Delegated agents with their own prompt and tools |
| 08 | Permissions | `08-permissions.md` | Tool execution control, allow and deny and sandbox |
| 09 | Plugins and marketplaces | `09-plugins-and-marketplaces.md` | The plugin package, its manifest, and the catalog that distributes it |

Numbers 10 and up are open. Candidate concepts that may earn a number once a
real cross tool equivalence is confirmed: rules directories, workflows, output
styles, and dedicated memory stores. Do not create a file for a
candidate until it has a registry row. A concept that turns out to exist in only
one tool does not belong here at all.

---

## 4. Anatomy of a concept file

A concept file is a short narrative frame followed by a sequence of aspects.
Each aspect is one facet of the concept along which the tools can be compared,
and each aspect is one numbered H2 section holding a short intro and one table.

The fixed skeleton, top to bottom:

1. **H1 title.** The concept name, hyphen free. Nothing else on the line.
2. **Definition paragraph.** One to three sentences saying what the concept is
   and what role it plays in an agent workflow. No table, no list, just prose.
3. **Aspect sections.** Two to six numbered H2 sections. Each opens with one to
   three sentences of narrative that say what this facet is and why it matters
   for porting, then presents exactly one comparison table.
4. **Sources section.** A final numbered H2 named `Sources` listing the doc
   pages consulted, grouped by tool. This is what makes a claim checkable.

Which aspects to include is decided by the concept, not by a fixed list. Common
facets are file location and naming, file format and syntax, scope and
precedence, load behavior, and any signature feature unique to the concept. Only
include a facet if the tools actually differ along it in a way that matters when
porting. A file with three sharp aspects beats one with six padded ones.

A short, complete example of a single aspect section:

```markdown
## 1. File location and naming

Each tool reads its project prompt from a fixed filename at the repository
root, and the names differ, so a ported project has to be renamed or
re-pointed before the agent will pick it up.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Default filename | `CLAUDE.md` | `AGENTS.md` | `AGENTS.md` |
| Allowed locations | repo root or `.claude/` | repo root | repo root |
| Porting-in notes | rename the source file to `CLAUDE.md`, or import it with `@` | rename to `AGENTS.md` | rename to `AGENTS.md` |
```

---

## 5. Comparison tables and porting-in notes

Every aspect table shares one shape. The first column is the comparison axis and
its header is a concise noun such as `Dimension`. The remaining columns are the
three tools in the fixed order from section 2. Each data row states one
dimension of the aspect, tool by tool. Keep cells terse: a value, a path, a
short phrase. Inline code formatting for filenames, fields, and paths.

The last row of every table is always labelled `Porting-in notes` in its first
cell. Each tool cell answers a single question: when someone is moving a setup
from another tool into this one, what about this aspect will bite them. This is
the O(N) trick. Rather than writing every pairwise migration direction, which
grows as N by N minus one, each tool gets one note describing what is special
about arriving at that tool, because the friction of a migration lives mostly in
the destination. When a tool has nothing special to watch for a given aspect,
its porting cell is a single em free dash character `—` used as a placeholder,
which is allowed here because it is table shorthand, not a sentence break.

Do not add a second table to an aspect, and do not merge two aspects into one
oversized table. One aspect, one table, one porting row.

---

## 6. Sourcing, verification, and missing equivalents

Every non obvious factual claim in a concept file must come from the current
official documentation, retrieved through the doc lookup skills, not from
memory. Use `claude-code-docs` for the Claude Code column, `codex-docs` for the
Codex column, and `antigravity-docs` for the Antigravity column. These skills
exist precisely because the tools change often and training data goes stale.

The `Sources` section at the foot of each file records what was read, so a
later maintainer can re verify without redoing the discovery. List the doc pages
per tool as title and URL, and the URL must be the one the doc skill actually
retrieved content from, never a link that only renders for a human.

Claude Code publishes a `.md` twin at the page URL with a `.md` suffix, so
`https://code.claude.com/docs/en/memory.md` is correct. Codex has moved: the
`https://developers.openai.com/codex/<slug>.md` URLs now issue a 308 to
`https://learn.chatgpt.com/docs/<slug>.md`, and `codex/llms.txt` redirects to a
404, so record the `learn.chatgpt.com` URL that actually served the page. Codex
plugin and skill building pages still live at
`https://developers.openai.com/plugins/...md` and fetch directly, with the whole
map at `https://developers.openai.com/llms.txt`. Antigravity is now server
rendered, so the page URL `https://antigravity.google/docs/cli/plugins` is
fetchable and is the `content_url` recorded in the `antigravity-docs` skill's
`docs-manifest.json`. Record that page URL. The older
`/assets/docs/....md` twins are gone and must not be used.

If a fact could not be confirmed in
the docs, do not launder it into a confident claim. Either leave the cell honest
with a short `unconfirmed` note, or omit the row.

When a tool genuinely has no equivalent for an aspect, write `No equivalent` in
that cell with a few words of context, never a blank. When a tool has no
equivalent for the whole concept, the concept file still carries its column, its
data cells read `No equivalent`, and the porting row explains the closest
workaround. A blank cell is ambiguous. It reads as forgotten rather than
absent, so it is never acceptable.

---

## 7. Markdown style compliance

Concept files and the index are project documents and follow the project
`markdown-style` rules. The points that bite most often here:

The H1 title carries exactly one per file and contains no dash of any kind, no
quotes, and no brackets. Write `Subagents`, not `Sub-agents`, and
`MCP servers`, not `MCP-servers`. Aspect sections are numbered H2 in the form
`## 1. Title`, `## 2. Title`, with a horizontal rule `---` on its own line
between every pair of H2 sections. Avoid H4 and deeper. In prose, avoid the em
dash, the en dash, and the hyphen used as a sentence break; start a fresh
sentence or use parentheses instead. The hyphen stays fine inside compound words
and inside filenames. No ASCII diagrams, no decorative emoji, no inline HTML for
styling. The one dash placeholder allowed inside a porting cell, described in
section 5, is the single exception and it is table shorthand rather than prose.

The final concept file contains no HTML comments. The template in
`concept-file-template.md` carries guidance comments for the author, and those
are stripped when the real file is written.

---

## 8. The index file

The index at `00-context-index.md` is the reader facing table of contents for
the whole knowledge base. It is short by design and derived from the detail
files, never a place where new facts first appear. Its job is triage: let a
reader see every concept at a glance and jump to the right detail file.

Its shape mirrors the detail files at a smaller scale. A brief opening paragraph
that states what the knowledge base covers, then one numbered H2 per concept in
registry order. Each concept section holds a one or two sentence blurb, a small
table whose rows are the tools and whose single data column names that tool's
primary file or location for the concept, and a link to the detail file. The
opening blurb and the primary location must agree with the detail file. If they
drift, the detail file is right and the index is what gets corrected.

### Never link to this builder with a relative path

The opening paragraph points a reader at this builder as the place the registry
and the format live. Write that pointer as the absolute URL below, never as a
relative path.

```
https://github.com/MacHu-GWU/shsk_coding_agent_docs-project/blob/main/.claude/skills/coding-agent-concept-mapping-builder/SKILL.md
```

The reason is a packaging boundary. The knowledge base ships inside the
`coding-agent-docs` plugin, whose root is `.claude/skills/coding-agent-docs/`.
This builder lives at `.claude/skills/coding-agent-concept-mapping-builder/`,
outside that root, and is deliberately not published with the plugin because it
is a maintainer tool. So no number of `../` hops can reach it from a generated
file once the plugin is installed on someone else's machine. A relative link
there is broken by construction, not by a miscount. Say in the same sentence
that the builder does not ship with the plugin, so a reader who cannot open it
understands why.

The same rule applies to the `Maintenance` section of the knowledge base's own
`SKILL.md`, which carries the identical pointer.

---

## 9. Build and update workflow

The order is fixed and it is detail first, index second. A concept file is
authored or updated to this standard before the index is touched, because the
index only summarizes what the detail file already establishes. Writing the
index first would mean summarizing content that does not exist yet.

The full step by step procedure the builder follows lives in the skill body at
`../SKILL.md`. This document defines what a correct file looks like. The skill
body defines the sequence of actions that produces one. Read both before
authoring: this standard tells you the shape, the skill tells you the moves.
