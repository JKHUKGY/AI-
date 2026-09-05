# Plugins and marketplaces

A plugin is the distribution unit that bundles several other concepts (skills, subagents, hooks, MCP servers, rules) into one installable directory, and a marketplace is the catalog that tells the agent where to fetch those plugins from. Claude Code and Codex converge almost completely here: both use a hidden manifest directory, a `marketplace.json` catalog, the same family of git and npm source types, and a `<tool> plugin marketplace add` command. Antigravity has the plugin half of the idea but not the marketplace half, so a plugin reaches an Antigravity user only as a local directory.

## 1. Plugin package layout and manifest

Every tool recognizes a directory as a plugin by the presence of a manifest file, and everything else in the package is discovered by convention around it. The manifest path differs in all three, and the field set ranges from a rich schema down to two keys, so the manifest is the first thing to rewrite when porting a package.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Manifest path | `.claude-plugin/plugin.json`, and the manifest itself is optional | `.codex-plugin/plugin.json` | `plugin.json` at the plugin root |
| Required fields | `name` only, when a manifest is present | `name`, with `version` and `description` used by every published example | `name`, matching `^[a-zA-Z0-9-_]+$` |
| Identity metadata | `version`, `description`, `author`, `homepage`, `repository`, `license`, `keywords` | the same set, plus an `interface` object for `displayName`, `category`, `capabilities`, icons, and legal URLs | `description` only, and the published schema sets `additionalProperties: false` |
| Component path overrides | `skills`, `commands`, `agents`, `hooks`, `mcpServers`, `lspServers`, `outputStyles`, `experimental` | `skills`, `mcpServers`, `apps`, `hooks` | No equivalent, the layout is fixed by convention |
| Path variable inside the package | `${CLAUDE_PLUGIN_ROOT}` and `${CLAUDE_PLUGIN_DATA}` | `${PLUGIN_ROOT}` and `${PLUGIN_DATA}`, with `CLAUDE_PLUGIN_ROOT` and `CLAUDE_PLUGIN_DATA` kept as legacy aliases | No equivalent documented |
| Validation helper | `claude plugin validate ./my-plugin`, with `--strict` | plugin submission validation on the OpenAI Platform | `$schema` pointing at `https://antigravity.google/schemas/v1/plugin.json` for editor validation |
| Porting-in notes | only `plugin.json` goes in `.claude-plugin/`, every component folder stays at the plugin root | rename `.claude-plugin/` to `.codex-plugin/`, keep the same root level component folders, and move display metadata into `interface` | flatten to a root `plugin.json` and strip every field except `name` and `description`, since the schema rejects extras, then rewrite any `${CLAUDE_PLUGIN_ROOT}` reference to a real path |

---

## 2. Bundled component types

The value of a plugin is that one install delivers several concepts at once, so what a plugin is allowed to carry decides how much of a setup survives the move. Claude Code carries the widest set, Codex is close behind but drops subagents from the plugin surface, and Antigravity carries a small set that uniquely includes rules.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Skills | `skills/<name>/SKILL.md`, or a bare `SKILL.md` at the plugin root for a single skill plugin | `skills/<name>/SKILL.md` | `skills/` |
| Flat commands | `commands/*.md`, loaded as skills | No equivalent, custom prompts are deprecated in favor of skills | No equivalent, a skill compiles into a slash command directly |
| Subagents | `agents/*.md`, exposed as `my-plugin:code-reviewer` | No equivalent documented as a plugin component | `agents/`, holding subagent definition templates |
| Hooks | `hooks/hooks.json`, or inline in `plugin.json` | `hooks/hooks.json`, and plugin hooks stay untrusted until the user reviews them | `hooks.json` at the plugin root |
| MCP servers | `.mcp.json`, scoped as `mcp__plugin_<plugin>_<server>__<tool>` | `.mcp.json` for bundled servers, plus `.app.json` mapping pre registered connections | `mcp_config.json` |
| Persistent context or rules | No equivalent, a `CLAUDE.md` at the plugin root is deliberately not loaded | No equivalent | `rules/`, holding markdown rules files |
| Other components | `lspServers`, `workflows/`, `output-styles/`, `themes/`, `monitors/`, `bin/` on PATH, and a default `settings.json` | `assets/` for icons and screenshots, browser extensions, and scheduled task templates | No equivalent |
| Porting-in notes | the richest target, so an imported plugin usually loses nothing and can gain LSP servers, monitors, or a `bin/` directory afterward | subagents have no plugin slot, so re express a ported `agents/*.md` as a skill or as a standalone `.codex/agents/<name>.toml` | only skills, subagents, rules, MCP, and hooks survive; drop commands, LSP, themes, and monitors, and rename `.mcp.json` to `mcp_config.json` and `hooks/hooks.json` to a root `hooks.json` |

---

## 3. Marketplaces and distribution sources

A marketplace is a JSON catalog listing plugins and where each one is fetched from, which is what turns a plugin from a folder you copy into something a team installs by name. This is the sharpest split in the whole knowledge base: Claude Code and Codex have nearly identical catalogs and source types, and Antigravity has none.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Catalog file | `.claude-plugin/marketplace.json` at the repository root | `$REPO_ROOT/.agents/plugins/marketplace.json` for a repo catalog, `~/.agents/plugins/marketplace.json` for a personal one, with `$REPO_ROOT/.claude-plugin/marketplace.json` read for compatibility | No equivalent |
| Catalog schema | `name`, `owner`, `plugins[]`, plus optional `description`, `version`, `metadata.pluginRoot`, `renames`, `allowCrossMarketplaceDependenciesOn` | `name`, `interface.displayName`, `plugins[]`, with each entry carrying `policy.installation`, `policy.authentication`, and `category` | No equivalent |
| Plugin source types | a `./` relative path, `github`, `url`, `git-subdir`, `npm` | a `./` relative path or `local`, `url`, `git-subdir`, `npm` | No equivalent, `agy plugin install` takes a filesystem path |
| Git subdirectory support | `git-subdir` with `url`, `path`, `ref`, `sha`, cloned sparsely for monorepos | `git-subdir` with `url`, `path`, `ref`, `sha`, and an unresolvable entry is skipped rather than failing the catalog | No equivalent |
| Version pinning | `version` in `plugin.json` wins over the marketplace entry, and both falling back to the git commit SHA | `version` on the manifest and the marketplace entry, with `ref` or `sha` selectors on git sources | No equivalent, the staged directory is whatever was installed |
| Registering a marketplace | `claude plugin marketplace add <owner/repo, git URL, marketplace.json URL, or ./path>` with `--ref`, `--sparse`, `--scope`, or `/plugin marketplace add` | `codex plugin marketplace add <owner/repo, git URL, or ./path>` with `--ref` and `--sparse`, plus `list`, `upgrade`, `remove` | No equivalent |
| Public catalog | the official marketplace `anthropics/claude-plugins-official`, browsed in the `/plugin` Discover tab | the universal public Plugins Directory shared by ChatGPT and Codex, published through the OpenAI Platform submission portal | Google curated Build with Google bundles under Settings, Customizations, Build with Google Plugins, with no third party catalog |
| Porting-in notes | the catalog lives at `.claude-plugin/marketplace.json`, not under `.agents/`, so a Codex repo catalog has to be copied or moved to that path | a Claude Code `marketplace.json` is close enough to reuse, but move it to `.agents/plugins/`, and add `policy.installation`, `policy.authentication`, and `category` to every entry | there is nothing to point a catalog at, so publish the plugin as a git repository and tell users to clone it and run `agy plugin install <path>`, or drop it into the workspace plugins folder |

---

## 4. Install location, scope, and enablement

Where an installed plugin lands on disk and which config file records that it is on decides whether a teammate who clones the repository gets the same setup. Claude Code and Codex both keep a versioned cache plus a settings record, while Antigravity stages a single copy into the user profile.

| Dimension | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Install cache | `~/.claude/plugins/cache/`, with marketplace plugins copied in rather than used in place | `~/.codex/plugins/cache/$MARKETPLACE_NAME/$PLUGIN_NAME/$VERSION/`, where `$VERSION` is `local` for local plugins | `~/.gemini/antigravity-cli/plugins/<plugin_name>/`, staged by `agy plugin install` |
| In repository drop in | a folder under a skills directory holding `.claude-plugin/plugin.json` loads as `<name>@skills-dir` with no install step | plugins kept under `$REPO_ROOT/plugins/` and listed in the repo `marketplace.json` | `.agents/plugins/` or `_agents/plugins/` at the workspace root, per the IDE docs; the CLI docs document only the global path |
| Scope model | `user`, `project`, `local`, and `managed`, selected with `--scope` and recorded in the matching settings file | personal versus repo marketplace, plus workspace sharing inside the ChatGPT desktop app | global user profile for the CLI, workspace or global folder for the IDE, with no documented per scope enable |
| Enablement record | `enabledPlugins` and `extraKnownMarketplaces` in `settings.json` at any scope, and `defaultEnabled` in the manifest or marketplace entry | the on or off state of each plugin is stored in `~/.codex/config.toml`, with `[plugins."<name>".mcp_servers.<server>]` tuning a bundled server | `agy plugin enable` and `agy plugin disable`, with the storage location not documented |
| Management commands | `claude plugin init, install, uninstall, enable, disable, update, list, details, validate, prune, tag`, plus the `/plugin` interface | `codex plugin marketplace add, list, upgrade, remove`, plus the `/plugins` browser for install and enablement | `agy plugin list, install, enable, disable, uninstall` |
| Administrator control | `strictKnownMarketplaces`, `blockedMarketplaces`, `pluginSuggestionMarketplaces`, and a `CLAUDE_CODE_PLUGIN_SEED_DIR` prebuilt cache | `features.plugin_sharing = false` in cloud managed `requirements.toml` | No equivalent documented |
| Porting-in notes | commit `extraKnownMarketplaces` and `enabledPlugins` to `.claude/settings.json` so collaborators are prompted on trust, and remember a project scope plugin loads only after the workspace trust gate | there is no `codex plugin install` in the docs, so installation happens through the `/plugins` browser after the marketplace is registered, and bundled hooks stay skipped until the user trusts them | nothing about the install is recorded in the repository, so every collaborator installs by hand; ship a checked in `.agents/plugins/<name>/` folder if the setup has to travel with the repo |

---

## 5. Sources

**Claude Code**

- Plugins reference: https://code.claude.com/docs/en/plugins-reference.md
- Create and distribute a plugin marketplace: https://code.claude.com/docs/en/plugin-marketplaces.md

**Codex**

- Package your plugin: https://developers.openai.com/plugins/build/plugins.md
- Plugins: https://learn.chatgpt.com/docs/plugins.md
- Build plugins: https://learn.chatgpt.com/docs/build-plugins.md

**Antigravity**

- Plugins and skills (CLI): https://antigravity.google/docs/cli/plugins
- Plugins (Antigravity 2.0): https://antigravity.google/docs/plugins
- Plugins (IDE): https://antigravity.google/docs/ide/plugins
- Build with Google: https://antigravity.google/docs/build-with-google
