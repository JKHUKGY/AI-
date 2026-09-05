#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
plugin_release.py -- a zero-dependency, pure-standard-library CLI for
discovering, validating, and tagging Claude Code plugins that live under a git
repo's ``.claude/skills/`` directory.

It locates the enclosing git repository by walking up from the current
directory (or ``--repo-root``) until it finds a ``.git`` entry, then treats
that directory as the repo root. Under ``<repo-root>/.claude/skills/`` it looks
at every ``<folder-name>/`` and checks for ``<folder-name>/.claude-plugin/
plugin.json``:

* No ``plugin.json``  -> the folder is a standalone skill, not a plugin; ignored.
* Has ``plugin.json`` -> it must be valid: parseable JSON with non-empty
  ``name``, ``description``, and ``version`` fields, and ``version`` must match
  ``x.y.z`` (three dot-separated integers). A ``plugin.json`` that exists but
  fails any of these checks is a hard error.

Commands:

    list [--json]              Print the discovered/validated plugins.
    tag  [--no-push] [--force] Create a ``{name}--v{version}`` git tag for each
                               plugin (via ``claude plugin tag``), skipping tags
                               that already exist. Aborts before tagging if any
                               plugin manifest is invalid.

Examples:

    python3 plugin_release.py list
    python3 plugin_release.py list --json
    python3 plugin_release.py tag
    python3 plugin_release.py tag --no-push
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# A release version is exactly three dot-separated integers, e.g. 0.1.2.
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
REQUIRED_FIELDS = ("name", "description", "version")


class PluginError(Exception):
    """Raised when a plugin.json exists but is malformed or incomplete."""


def find_repo_root(start: Path) -> Path:
    """Walk up from ``start`` until a ``.git`` entry is found; return that dir."""
    start = start.resolve()
    for path in [start, *start.parents]:
        # `.git` is a directory in a normal clone, or a file in a worktree.
        if (path / ".git").exists():
            return path
    raise SystemExit(f"error: no .git found in {start} or any parent directory")


def iter_skill_dirs(repo_root: Path):
    """Yield each immediate subdirectory of ``<repo-root>/.claude/skills/``."""
    skills_dir = repo_root / ".claude" / "skills"
    if not skills_dir.is_dir():
        return
    for child in sorted(skills_dir.iterdir()):
        if child.is_dir():
            yield child


def load_plugin(skill_dir: Path):
    """
    Inspect one ``.claude/skills/<folder>/`` directory.

    Returns a plugin dict for a valid plugin, ``None`` if the folder is a
    standalone skill (no ``.claude-plugin/plugin.json``), or raises
    ``PluginError`` if the manifest exists but is invalid.
    """
    manifest = skill_dir / ".claude-plugin" / "plugin.json"
    if not manifest.is_file():
        return None  # standalone skill, not a plugin -- silently ignored

    try:
        data = json.loads(manifest.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise PluginError(f"{manifest}: cannot parse JSON ({exc})")

    if not isinstance(data, dict):
        raise PluginError(f"{manifest}: top-level JSON must be an object")

    missing = [f for f in REQUIRED_FIELDS if not data.get(f)]
    if missing:
        raise PluginError(
            f"{manifest}: missing or empty required field(s): {', '.join(missing)}"
        )

    version = data["version"]
    if not isinstance(version, str) or not VERSION_RE.match(version):
        raise PluginError(
            f"{manifest}: version {version!r} is not in x.y.z format"
        )

    name = data["name"]
    return {
        "name": name,
        "description": data["description"],
        "version": version,
        "dir": skill_dir,
        "manifest": manifest,
        "tag": f"{name}--v{version}",
    }


def discover(repo_root: Path):
    """Return ``(plugins, errors)`` for all plugins under ``.claude/skills/``."""
    plugins, errors = [], []
    for skill_dir in iter_skill_dirs(repo_root):
        try:
            plugin = load_plugin(skill_dir)
        except PluginError as exc:
            errors.append(str(exc))
            continue
        if plugin is not None:
            plugins.append(plugin)
    return plugins, errors


def tag_exists(repo_root: Path, tag: str) -> bool:
    result = subprocess.run(
        ["git", "tag", "-l", tag],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip() == tag


def cmd_list(args) -> int:
    repo_root = find_repo_root(Path(args.repo_root or "."))
    plugins, errors = discover(repo_root)

    if args.json:
        payload = {
            "repo_root": str(repo_root),
            "plugins": [
                {
                    "name": p["name"],
                    "description": p["description"],
                    "version": p["version"],
                    "dir": str(p["dir"].relative_to(repo_root)),
                    "tag": p["tag"],
                }
                for p in plugins
            ],
            "errors": errors,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"repo root: {repo_root}")
        if not plugins:
            print("  (no valid plugins under .claude/skills/)")
        for p in plugins:
            rel = p["dir"].relative_to(repo_root)
            print(f"  {p['name']}  {p['version']}  ->  {p['tag']}   [{rel}]")
        for exc in errors:
            print(f"  ERROR: {exc}", file=sys.stderr)

    return 1 if errors else 0


def cmd_tag(args) -> int:
    repo_root = find_repo_root(Path(args.repo_root or "."))
    plugins, errors = discover(repo_root)

    # Fail fast: never tag anything if any manifest is invalid.
    if errors:
        print("Plugin manifest validation failed:", file=sys.stderr)
        for exc in errors:
            print(f"  - {exc}", file=sys.stderr)
        return 1

    if not plugins:
        print("No plugins found under .claude/skills/")
        return 0

    print(f"Discovered {len(plugins)} plugin(s) under {repo_root}/.claude/skills/")
    for p in plugins:
        tag = p["tag"]
        print(f"\n[{p['name']}] version {p['version']} -> tag {tag!r}")

        if not args.force and tag_exists(repo_root, tag):
            print(f"  Tag {tag!r} already exists locally, skipping "
                  f"(use --force to move it).")
            continue

        # `claude plugin tag` derives {name}--v{version} from plugin.json,
        # validates the plugin, requires a clean working tree under the plugin
        # dir, then (with --push) creates and pushes the tag to origin.
        cmd = ["claude", "plugin", "tag"]
        if not args.no_push:
            cmd.append("--push")
        if args.force:
            cmd.append("--force")
        subprocess.run(cmd, cwd=p["dir"], check=True)
        verb = "Created" if args.no_push else "Created and pushed"
        print(f"  {verb} tag {tag!r}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="plugin_release.py",
        description="Discover, validate, and tag Claude Code plugins under "
                    "<git-root>/.claude/skills/.",
    )
    parser.add_argument(
        "--repo-root",
        help="Directory to start the .git search from (default: current dir).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List and validate discovered plugins.")
    p_list.add_argument("--json", action="store_true",
                        help="Emit machine-readable JSON.")
    p_list.set_defaults(func=cmd_list)

    p_tag = sub.add_parser(
        "tag", help="Create {name}--v{version} release tags (idempotent).")
    p_tag.add_argument("--no-push", action="store_true",
                       help="Create tags locally without pushing to origin.")
    p_tag.add_argument("--force", action="store_true",
                       help="Pass --force to `claude plugin tag` to move an "
                            "existing tag instead of skipping it.")
    p_tag.set_defaults(func=cmd_tag)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
