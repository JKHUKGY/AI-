# Skills

A skill is a reusable, self contained package of instructions plus optional scripts and reference files that an agent loads on demand to gain a capability. The three tools converge closely here: each defines a skill as a directory whose entry file is `SKILL.md`, opened by YAML frontmatter that carries at least a description, and each loads the skill by progressive disclosure and can trigger it either explicitly or by matching the description. The main differences are the directory path, the size of the frontmatter contract, and how an isolated run works.

## 1. Directory structure and location

Every tool treats a skill as a folder whose entry file is `SKILL.md`, discoverable at several scopes. The paths differ: Claude Code keeps skills under `.claude/skills/`, while Codex and Antigravity both use the tool neutral `.agents/skills/`.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Entry file | `SKILL.md` | `SKILL.md` | `SKILL.md` |
| User / global | `~/.claude/skills/<name>/` | `~/.agents/skills/<name>/` | `~/.gemini/antigravity-cli/skills/` per the CLI docs, `~/.gemini/config/skills/<name>/` per the 2.0 docs |
| Project | `.claude/skills/<name>/` | `.agents/skills/<name>/`, scanned from the cwd up to the repo root | `.agents/skills/<name>/` (legacy `.agent/skills/`) |
| Admin / enterprise | through managed settings | `/etc/codex/skills/` | No equivalent documented |
| Supporting files | optional `scripts/`, plus reference and example files | optional `scripts/`, `references/`, `assets/`, and `agents/openai.yaml` | optional `scripts/`, `examples/`, `resources/` |
| Porting-in notes | move any `.agents/skills/` folders to `.claude/skills/`, since Claude Code does not read the neutral path | the `.agents/skills/` path is shared with Antigravity, so a repo's project skills often load as is | project skills share the `.agents/skills/` path, but the two doc sets still disagree on the global path, so keep skills in the repo folder |

---

## 2. Metadata contract

The entry file opens with YAML frontmatter. All three need little more than a description to match on, but the field set is very uneven: Claude Code exposes a large contract while Codex and Antigravity keep `SKILL.md` minimal and push richer metadata elsewhere.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Required fields | `description` recommended, `name` optional | `name` and `description` | `description`, `name` optional |
| Trigger text | `description` plus `when_to_use`, capped at 1,536 chars | `description` drives implicit matching | `description` |
| Tool and model control | `allowed-tools`, `disallowed-tools`, `model`, `effort` | not in `SKILL.md`; richer metadata sits in `agents/openai.yaml` | No equivalent documented |
| Execution control | `context: fork`, `agent`, `hooks`, `paths`, `argument-hint`, `arguments` | policy such as `allow_implicit_invocation` in `agents/openai.yaml` | No equivalent documented |
| Porting-in notes | the frontmatter is a superset, so imported skills keep working and can gain fields like `allowed-tools` afterward | keep only `name` and `description` in `SKILL.md` and move any richer metadata into `agents/openai.yaml` | only `name` and `description` are documented, so drop unsupported frontmatter fields |

---

## 3. Invocation

Every tool supports both an explicit trigger and automatic activation that matches the skill description against the task. The explicit trigger token is what differs.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Explicit trigger | `/skill-name` | `$skill-name`, or the `/skills` command | a registered skill becomes a slash command such as `/refactor-ui`; `/skills` browses them |
| Automatic activation | Claude matches the `description` unless `disable-model-invocation` is set | Codex matches the `description` | the agent decides from context, or you name the skill |
| Argument passing | `$ARGUMENTS`, `$N`, `$name`, and more substitutions | not documented for skills; the deprecated custom prompts carried it | not documented |
| Porting-in notes | the `/skill-name` command comes from the directory name, not the frontmatter `name` | mention a skill with `$name`, and note that argument substitution belonged to custom prompts, not skills | registered skills turn into slash commands automatically, so expect `/<skill>` rather than an `@` or `$` prefix |

---

## 4. Content model and execution

All three load a skill by progressive disclosure: only its name and description stay in context until the skill is chosen, then the full `SKILL.md` loads. They diverge on isolated execution and on preprocessing.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Loading | progressive, description first and body on use | progressive, name and description first and body on use | progressive, through discovery then activation then execution |
| Isolated run | `context: fork` runs the skill in a subagent with its own context | inline; subagents are a separate feature | inline; subagents are a separate feature |
| Scripts | files under `scripts/` are executed, not loaded into context | optional `scripts/` for deterministic steps | `scripts/`, which the agent is told to run with `--help` rather than read |
| Preprocessing | `` !`command` `` injects shell output before the model sees the content | not documented | not documented |
| Porting-in notes | add `context: fork` for an isolated run, and use `!` injection to fold in live data | skills run inline, so reach for a subagent when isolation is needed | skills run inline, and helper scripts are meant to be run rather than pasted in |

---

## 5. Signature features and distribution

Beyond authoring, each tool ships starter skills, gates tools, and packages skills for sharing. Claude Code and Codex both fold an older feature into skills, while Antigravity keeps skills separate from its rules and workflows.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Built in skills | many bundled, such as `/code-review`, `/debug`, and `/loop` | `skill-creator` and `plan`, plus a `$skill-installer` | none documented |
| Tool pre approval | `allowed-tools` grants tools without prompting while the skill is active | implicit triggering is gated by an `allow_implicit_invocation` policy | No equivalent documented |
| Distribution unit | plugins, or commit `.claude/skills/` to the repo | plugins bundle two or more skills | plugins bundle skills together with other assets |
| Superseded feature | custom commands were merged into skills | custom prompts are deprecated in favor of skills | rules and workflows stay separate, not superseded |
| Porting-in notes | an old `.claude/commands/*.md` still works and behaves like a skill of the same name | move any custom prompt into a skill, since prompts are deprecated | keep skills distinct from rules and workflows, which cover context and step sequences rather than reusable capabilities |

---

## 6. Sources

**Claude Code**

- Extend Claude with skills: https://code.claude.com/docs/en/skills.md
- Commands: https://code.claude.com/docs/en/commands.md

**Codex**

- Agent Skills: https://learn.chatgpt.com/docs/build-skills.md
- Custom Prompts: https://learn.chatgpt.com/docs/custom-prompts.md

**Antigravity**

- Skills: https://antigravity.google/docs/skills
- CLI Plugins: https://antigravity.google/docs/cli/plugins
- CLI Reference: https://antigravity.google/docs/cli/reference
