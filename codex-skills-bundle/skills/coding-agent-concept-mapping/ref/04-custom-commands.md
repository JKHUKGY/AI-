# Custom commands

A custom command is a user defined slash command that expands a short trigger into a saved prompt or procedure. This concept has collapsed into skills, and the three tools sit at different points along that collapse. Claude Code merged its `.claude/commands/` files into skills but still runs the old files. Codex kept custom prompts but marked them deprecated in favor of skills. Antigravity documents no separate custom command mechanism at all: a skill simply compiles into a `/name` slash command, which is where the other two are heading. Antigravity workflows are a related but distinct primitive, a multi step sequence invoked as `/workflow-name`, not a plain saved prompt.

## 1. Mechanism and status

The first thing to know for this concept is which mechanism provides custom commands and whether it is still the recommended path. In every tool the answer points back toward skills, and Antigravity shows the endpoint where the dedicated mechanism has disappeared entirely.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Dedicated command mechanism | `.claude/commands/*.md` | custom prompts in `~/.codex/prompts/` | none documented; a skill compiles into a `/name` command |
| Status | legacy, still supported | deprecated | no separate mechanism exists to be legacy |
| The command today | a skill, which outranks a same named command | a skill | the skill itself |
| Porting-in notes | author new commands as skills, since the old files keep working but skills add supporting files and auto invocation | write a skill, since custom prompts are deprecated | there is no commands folder; author a skill and it becomes `/<name>`, and reserve workflows (`/workflow-name`) for multi step procedures |

---

## 2. File location and format

Where the definition lives and how it is shaped decides whether a ported command travels with the repo. Claude Code commands are committed files, Codex prompts are home directory only, and an Antigravity custom command is really a skill package.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Location | project `.claude/commands/`, personal `~/.claude/commands/` | `~/.codex/prompts/` only, not shared through the repo | the skill folder (see the Skills concept); the workflow file path is unconfirmed |
| Unit | one Markdown file per command | one top level Markdown file per prompt, no subdirectories | a `SKILL.md` package, that is a directory rather than a lone file |
| Metadata | the same YAML frontmatter contract as skills | `description` and `argument-hint` frontmatter | the skill `name` and `description` frontmatter |
| Name source | the file name without its extension | the file name, shown as `/prompts:<name>` | the skill `name` field, which defaults to the folder name |
| Porting-in notes | commands can be committed to the repo, unlike Codex prompts | prompts live only in the home directory, so a ported command must be recreated per user | a custom command is a skill directory, so it ports exactly like a skill does |

---

## 3. Arguments and substitution

Passing arguments is the sharpest split. Claude Code is the richest, Codex adds named `KEY=value` arguments, and Antigravity documents no argument passing for either skills or workflows.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Positional | `$1`, `$N`, and `$ARGUMENTS[N]` | `$1` through `$9`, and `$ARGUMENTS` for all | No documented equivalent |
| Named | `$name` declared in the `arguments` field | uppercase names like `$FILE`, supplied as `KEY=value` | No documented equivalent |
| Shell or file injection | `` !`command` `` runs a shell command before the model sees the body | No equivalent | No documented equivalent |
| Literal dollar | `\$` escapes a dollar sign | `$$` emits a single dollar sign | not applicable |
| Porting-in notes | positional and named substitution plus `!` shell injection all carry over from the command body | use `KEY=value` for named arguments, and note there is no shell or file injection | neither skills nor workflows document argument substitution, so pass any context in the prompt text instead |

---

## 4. Invocation and namespacing

All three trigger with a leading slash, but they differ on where user commands come from, how they compose, and whether the defined commands can be browsed.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Trigger | `/command-name` at the start of a message | `/prompts:<name>` or `/<name>` | `/<skill-name>` from a skill, or `/workflow-name` |
| Namespacing | plugin skills use `plugin:name`, and a skill outranks a same named command | the `prompts:` prefix | none documented |
| Composition | stack several skills in one message | not documented | a workflow can call other workflows |
| Browse | the `/` menu | the `/` menu | `/skills` browses skills; there is no `/commands` or `/workflows` browser |
| Porting-in notes | a command is recognized only at the start of a message, and a same named skill takes precedence | prompts appear under the `prompts:` namespace in the slash menu | the built in slash commands are a fixed set, and user commands come only from skills and workflows |

---

## 5. Sources

**Claude Code**

- Commands: https://code.claude.com/docs/en/commands.md
- Extend Claude with skills: https://code.claude.com/docs/en/skills.md

**Codex**

- Custom Prompts: https://learn.chatgpt.com/docs/custom-prompts.md
- Agent Skills: https://learn.chatgpt.com/docs/build-skills.md

**Antigravity**

- CLI Plugins: https://antigravity.google/docs/cli/plugins
- CLI Reference: https://antigravity.google/docs/cli/reference
- Rules and Workflows: https://antigravity.google/docs/rules-workflows
