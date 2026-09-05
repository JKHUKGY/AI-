# Project prompt

A project prompt is a persistent instruction file kept in the repository that an agent loads at the start of every session, so shared context such as build commands, conventions, and architecture notes does not have to be repeated by hand. In Claude Code this is `CLAUDE.md`. Codex expresses the same idea as `AGENTS.md`, while Antigravity has no single always-on file and instead spreads the role across a global `GEMINI.md` and a project rules directory.

## 1. File location and naming

Each tool reads its project prompt from a known filename, and the names diverge, so a ported repository has to be renamed or re-pointed before the agent will pick it up. Antigravity is the outlier because it has no canonical single file at all.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Default filename | `CLAUDE.md` | `AGENTS.md` | No single file; global `~/.gemini/GEMINI.md` plus project `.agents/rules/*.md` |
| Project location | repo root `./CLAUDE.md` or `./.claude/CLAUDE.md` | repo root `AGENTS.md`, plus nested directories | `.agents/rules/` directory (legacy `.agent/rules/`) |
| Alternate names | not renameable; import another file with `@` | `project_doc_fallback_filenames` config lists names to try when `AGENTS.md` is absent; a directory's `AGENTS.override.md` supersedes its `AGENTS.md` | any `.md` rule file; no fixed names |
| Porting-in notes | rename the source to `CLAUDE.md`, or keep it and import it with `@AGENTS.md` | drop the file in as `AGENTS.md`, or add its name to `project_doc_fallback_filenames` | split the prompt into one or more `.agents/rules/` files and set the main one to `Always On` |

---

## 2. Scope and precedence

All three tools layer instructions from a broad scope down to a specific one, but the number of layers and the rule for combining them differ. This matters when a repository carries personal or organization wide guidance that has to land in the right layer after a move.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Managed / org level | `/Library/Application Support/ClaudeCode/CLAUDE.md` and OS peers, or `claudeMd` in managed settings | No equivalent | No equivalent |
| Global / user level | `~/.claude/CLAUDE.md` | `~/.codex/AGENTS.md` (relocatable via `CODEX_HOME`) | `~/.gemini/GEMINI.md` |
| Project level | `./CLAUDE.md` or `./.claude/CLAUDE.md` | repo root `AGENTS.md` | `.agents/rules/*.md` |
| Local personal (gitignored) | `./CLAUDE.local.md` | `AGENTS.override.md` per directory | No equivalent |
| Combine rule | every level concatenated, broad to specific | concatenated root down, deeper files win | unconfirmed; rules apply by activation mode, not directory position |
| Porting-in notes | fold personal notes into `CLAUDE.local.md`, which has no peer on the other tools | there is no managed tier; use `AGENTS.override.md` as the personal layer instead of a `.local` file | there is no documented precedence, so mark must apply content `Always On` rather than trusting file position |

---

## 3. Import and reference syntax

A project prompt often pulls in other files so a large instruction set stays modular. Claude Code and Antigravity share an `@` import syntax, whereas Codex has none and achieves modularity only by splitting content across directories.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Import syntax | `@path/to/file`, usable inline anywhere | No equivalent; split content across nested `AGENTS.md` files | `@filename` inside a rule file |
| Path resolution | relative to the importing file; absolute paths and `~` supported | not applicable | a non absolute path resolves relative to the repository; an absolute path is used as is |
| Nesting depth | up to 4 hops | not applicable | unconfirmed |
| Code block handling | `@` inside code spans and fences is left literal | not applicable | unconfirmed |
| Porting-in notes | convert any include mechanism into `@` imports, and wrap a literal `@` in backticks | there is no import, so inline the referenced text or move it into a nested `AGENTS.md` | `@` works inside rule files, but a non absolute path resolves from the repo root, not from the rule file |

---

## 4. Load behavior

How the files are discovered and merged at run time decides which instructions actually reach the model. Claude Code and Codex both walk the directory tree but in opposite directions, and Antigravity replaces traversal with per rule activation modes.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Directory traversal | cwd upward to root, loading every level's `CLAUDE.md` and `CLAUDE.local.md` | root downward to the current directory | unconfirmed |
| Subdirectory files | load lazily when Claude reads files there (JIT) | one file per directory on the path, loaded up front | unconfirmed; governed by activation mode |
| Combined order | root first, deeper files appended later; local file after the main file | root first, deeper files override | not positional; set by `Always On`, `Glob`, `Model Decision`, or `Manual` |
| After context compaction | root `CLAUDE.md` re-injected; nested files reload on next access | unconfirmed | unconfirmed |
| Porting-in notes | nested files are JIT, so do not expect them before Claude opens that subtree | traversal stops at the current directory, so files below it are ignored | give must apply content the `Always On` mode, since no traversal guarantee is documented |

---

## 5. Signature features

Beyond the shared file mechanics, each tool adds distinctive capabilities around generation, sizing, memory, and modular rules. These are the parts most likely to have no clean counterpart on another tool.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Scaffold command | `/init` analyzes the repo and generates `CLAUDE.md` | No equivalent | No equivalent |
| Size handling | soft target under 200 lines; the full file still loads | `project_doc_max_bytes`, default 32 KiB, caps the read | hard cap of 12,000 characters per rule file |
| Separate memory store | Auto Memory in `~/.claude/projects/<project>/memory/`; `MEMORY.md` loads first 200 lines or 25 KB | memories in `~/.codex/memories/`, opt in via `memories = true` | No equivalent |
| Exclude mechanism | `claudeMdExcludes` glob list; a managed file cannot be excluded | No equivalent | No equivalent |
| Modular rules | `.claude/rules/*.md` with optional `paths` frontmatter for conditional loading | No equivalent; only nested `AGENTS.md` | `.agents/rules/*.md` with activation modes |
| Porting-in notes | after moving in, run `/init` to seed, then split path scoped guidance into `.claude/rules/` | fold any always apply rules straight into `AGENTS.md`, since memories are a recall layer and not guaranteed; watch the 32 KiB read cap | express each source instruction as a rule with the right activation mode, and keep every file under 12,000 characters |

---

## 6. Sources

**Claude Code**

- How Claude remembers your project: https://code.claude.com/docs/en/memory.md
- Explore the .claude directory: https://code.claude.com/docs/en/claude-directory.md

**Codex**

- Custom instructions with AGENTS.md: https://learn.chatgpt.com/docs/agent-configuration/agents-md.md
- Memories: https://learn.chatgpt.com/docs/customization/memories.md?surface=app
- Configuration Reference: https://learn.chatgpt.com/docs/config-file/config-reference.md

**Antigravity**

- Rules and Workflows: https://antigravity.google/docs/rules-workflows
