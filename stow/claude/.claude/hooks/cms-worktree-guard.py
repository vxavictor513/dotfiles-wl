#!/usr/bin/env python3
"""Claude Code PreToolUse hook: keep agents' writes out of the cms-platform-config
main checkout.

Several agents work that repo at once, and a checkout has one branch, one index and
one set of files. So the main checkout is read-only for agents and every writing task
gets its own worktree (cms-platform-config AGENTS.md, "Working agreements").

Blocked when the target is inside the main checkout:
  - Edit / MultiEdit / Write / NotebookEdit on a file git does not ignore
  - git commands that move HEAD or touch the index or working tree
  - shell redirects (>, >>) and rm / mv / cp / touch / mkdir / tee / sed -i
    aimed at files git does not ignore

Allowed everywhere: reads, git fetch / log / diff / status, `git worktree add`,
and anything inside a linked worktree, wherever it lives. A worktree is told
apart by its `.git` being a file, not by its path.

This is a guardrail, not a sandbox. A script that writes files itself
(python3 -c, perl -pi, ...) is not inspected.

Exit 0 allows the call. Exit 2 blocks it and shows stderr to the agent. Anything
unexpected also exits 2 (fail closed). To bypass in an emergency, remove the hook
from .claude/settings.local.json.

Runs on the macOS system python3 (3.9), so: standard library only, no 3.10+ syntax.
"""

import json
import os
import re
import shlex
import subprocess
import sys
from typing import Dict, List, Optional, Tuple

# Matches the origin URL of every clone, whatever directory it was cloned into.
REPO_URL_MARKER = "/_git/cms-platform-config"

WRITE_TOOLS = {
    "Edit": "file_path",
    "MultiEdit": "file_path",
    "Write": "file_path",
    "NotebookEdit": "notebook_path",
}

# git subcommands that move HEAD, or change the index or working tree.
GIT_WRITE_SUBCOMMANDS = {
    "add", "am", "apply", "checkout", "cherry-pick", "clean", "commit", "merge",
    "mv", "pull", "rebase", "reset", "restore", "revert", "rm", "stash", "switch",
    "update-ref",
}
GIT_STASH_READ_ONLY = {"list", "show"}
# Global git options that take their value as the next token.
GIT_OPTS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}

SHELL_OPERATORS = {"&&", "||", ";", "|", "&", "\n", "(", ")", ";;", "|&"}
# Wrappers that run the command after them, and their options that take a value.
COMMAND_PREFIXES: Dict[str, set] = {
    "command": set(), "builtin": set(), "exec": set(), "time": set(),
    "env": {"-u", "-C", "-S", "-P"},
    "sudo": {"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-R", "-t", "-T", "-U"},
}
# Commands where every non-option argument is written or removed.
FILE_WRITE_COMMANDS = {"rm", "mv", "touch", "mkdir", "rmdir", "tee", "truncate"}
# Commands where only the last argument is written.
FILE_COPY_COMMANDS = {"cp", "install", "ln"}

# Not <<< (a here-string has no body).
HEREDOC = re.compile(r"(?<!<)<<(?!<)(-?)\s*(['\"]?)(\w+)\2")
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


class Blocked(Exception):
    pass


# --- repository detection ---------------------------------------------------

def find_repo_root(path: str) -> Optional[str]:
    """Nearest ancestor of `path` (or `path` itself) that contains a `.git`."""
    current = path
    while not os.path.exists(current):
        current = os.path.dirname(current)
    if not os.path.isdir(current):
        current = os.path.dirname(current)
    while True:
        if os.path.exists(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def main_checkout_root(path: str) -> Optional[str]:
    """The cms-platform-config main checkout containing `path`, if any.

    A linked worktree's `.git` is a file pointing back at the main repo,
    so only a `.git` directory marks the main checkout.
    """
    root = find_repo_root(path)
    if root is None:
        return None
    git_dir = os.path.join(root, ".git")
    if not os.path.isdir(git_dir):
        return None
    try:
        with open(os.path.join(git_dir, "config"), encoding="utf-8") as f:
            config = f.read()
    except OSError:
        return None
    return root if REPO_URL_MARKER in config else None


def is_git_ignored(root: str, path: str) -> bool:
    """Ignored files (settings.local.json, handoff/, CLAUDE.md, ...) never reach
    a branch or the index, so writing them cannot collide with another session."""
    result = subprocess.run(
        ["git", "-C", root, "check-ignore", "-q", "--", path],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
    )
    return result.returncode == 0


def write_candidates(path: str) -> List[str]:
    """The path with only its parents resolved, and fully resolved: a symlink
    is checked both where it sits and where it points."""
    link = os.path.join(os.path.realpath(os.path.dirname(path)), os.path.basename(path))
    target = os.path.realpath(path)
    return [link] if link == target else [link, target]


def check_file_write(path: str, what: str) -> None:
    for candidate in write_candidates(path):
        root = main_checkout_root(candidate)
        if root is not None and not is_git_ignored(root, candidate):
            raise Blocked(f"{what} {path}", root)


def check_git_write(directory: str, what: str) -> None:
    root = main_checkout_root(os.path.realpath(directory))
    if root is not None:
        raise Blocked(what, root)


# --- shell command parsing --------------------------------------------------

def strip_heredocs(command: str) -> str:
    """Drop heredoc bodies so a commit message line is not read as a command."""
    lines = command.split("\n")
    kept: List[str] = []
    terminators: List[Tuple[str, bool]] = []
    for line in lines:
        if terminators:
            word, strip_tabs = terminators[0]
            # Like bash: the line must be exactly the word; <<- also allows leading tabs.
            if (line.lstrip("\t") if strip_tabs else line) == word:
                terminators.pop(0)
            continue
        kept.append(line)
        terminators.extend((m.group(3), m.group(1) == "-") for m in HEREDOC.finditer(line))
    return "\n".join(kept)


def tokenize(command: str) -> List[str]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars="();<>|&\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    try:
        return list(lexer)
    except ValueError:
        # Unbalanced quotes: fall back to a rough split rather than give up.
        return re.findall(r"&&|\|\||[;|&()\n]|>>|>|[^\s;|&()<>]+", command)


def split_segments(tokens: List[str]) -> List[List[str]]:
    segments: List[List[str]] = [[]]
    for token in tokens:
        if token in SHELL_OPERATORS:
            segments.append([])
        else:
            segments[-1].append(token)
    return [s for s in segments if s]


def resolve(token: str, cwd: str, env: Dict[str, str]) -> Optional[str]:
    expanded = os.path.expanduser(token)
    for name, value in env.items():
        expanded = expanded.replace("${" + name + "}", value).replace("$" + name, value)
    expanded = os.path.expandvars(expanded)
    if "$" in expanded or "`" in expanded:
        return None  # cannot know where this points
    return os.path.normpath(os.path.join(cwd, expanded))


def check_git(args: List[str], cwd: str, env: Dict[str, str], command_env: Dict[str, str]) -> None:
    directory = cwd
    git_dir = resolve(command_env["GIT_DIR"], cwd, env) if "GIT_DIR" in command_env else None
    work_tree = resolve(command_env["GIT_WORK_TREE"], cwd, env) if "GIT_WORK_TREE" in command_env else None
    i = 0
    while i < len(args) and args[i].startswith("-"):
        option, value = args[i], None
        if option.startswith("--") and "=" in option:
            option, value = option.split("=", 1)
        elif option in GIT_OPTS_WITH_VALUE and i + 1 < len(args):
            value = args[i + 1]
            i += 1
        i += 1
        if value is None:
            continue
        if option == "-C":
            directory = resolve(value, directory, env) or directory
        elif option == "--git-dir":
            git_dir = resolve(value, directory, env)
        elif option == "--work-tree":
            work_tree = resolve(value, directory, env)
    if i >= len(args):
        return
    subcommand = args[i]
    if subcommand not in GIT_WRITE_SUBCOMMANDS:
        return
    if subcommand == "stash" and i + 1 < len(args) and args[i + 1] in GIT_STASH_READ_ONLY:
        return
    # The repo (HEAD, index) and the work tree can each be the main checkout.
    for target in {git_dir or directory, work_tree or directory}:
        check_git_write(target, f"`git {subcommand}`")


def check_file_command(name: str, args: List[str], cwd: str, env: Dict[str, str]) -> None:
    operands = [a for a in args if not a.startswith("-")]
    if name == "sed":
        if not any(a.startswith("-i") or a == "--in-place" for a in args):
            return
        # The sed script is an operand too; only real files count.
        targets = [p for p in (resolve(a, cwd, env) for a in operands) if p and os.path.isfile(p)]
    elif name in FILE_COPY_COMMANDS:
        destination = operands[-1] if operands else None
        for j, arg in enumerate(args):
            if arg in {"-t", "--target-directory"} and j + 1 < len(args):
                destination = args[j + 1]
            elif arg.startswith("--target-directory="):
                destination = arg.split("=", 1)[1]
            elif arg.startswith("-t") and len(arg) > 2:
                destination = arg[2:]
        targets = [resolve(destination, cwd, env)] if destination else []
    else:
        targets = [resolve(a, cwd, env) for a in operands]
    for target in targets:
        if target:
            check_file_write(target, f"`{name}` on")


def is_redirect(token: str) -> bool:
    return ("<" in token or ">" in token) and not token.strip("<>&|")


def split_redirects(segment: List[str]) -> Tuple[List[str], List[str]]:
    """Separate a segment into its command words and the files it redirects into."""
    words: List[str] = []
    written: List[str] = []
    i = 0
    while i < len(segment):
        token = segment[i]
        if not is_redirect(token):
            words.append(token)
            i += 1
            continue
        # The tokenizer splits `2>file` into `2`, `>`, `file`.
        if words and words[-1].isdigit():
            words.pop()
        if i + 1 < len(segment) and ">" in token:
            target = segment[i + 1]
            duplicates_fd = token.endswith("&") and (target.isdigit() or target == "-")
            if not duplicates_fd:
                written.append(target)
        i += 2
    return words, written


def check_bash(command: str, cwd: str) -> None:
    env: Dict[str, str] = {}
    for segment in split_segments(tokenize(strip_heredocs(command))):
        words, written = split_redirects(segment)
        for token in written:
            target = resolve(token, cwd, env)
            if target and not target.startswith("/dev/"):
                check_file_write(target, "redirect to")

        if all(ASSIGNMENT.match(w) for w in words):
            for w in words:
                name, value = w.split("=", 1)
                env[name] = value
            continue
        command_env: Dict[str, str] = {}
        while words:
            if ASSIGNMENT.match(words[0]):
                name, value = words.pop(0).split("=", 1)
                command_env[name] = value
            elif os.path.basename(words[0]) in COMMAND_PREFIXES:
                opts_with_value = COMMAND_PREFIXES[os.path.basename(words.pop(0))]
                while words and words[0].startswith("-"):
                    if words.pop(0) in opts_with_value and words:
                        words.pop(0)
            else:
                break
        if not words:
            continue

        name, args = os.path.basename(words[0]), words[1:]
        if name in {"cd", "pushd"}:
            operands = [a for a in args if not a.startswith("-")]
            target = resolve(operands[0], cwd, env) if operands else os.path.expanduser("~")
            if target:
                cwd = target
        elif name == "git":
            check_git(args, cwd, env, command_env)
        elif name in FILE_WRITE_COMMANDS | FILE_COPY_COMMANDS | {"sed"}:
            check_file_command(name, args, cwd, env)


# --- entry point ------------------------------------------------------------

def main() -> int:
    payload = json.load(sys.stdin)
    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    cwd = payload.get("cwd") or os.getcwd()

    try:
        if tool in WRITE_TOOLS:
            path = tool_input.get(WRITE_TOOLS[tool])
            if path:
                check_file_write(resolve(path, cwd, {}) or path, f"{tool} of")
        elif tool == "Bash":
            check_bash(tool_input.get("command", ""), cwd)
    except Blocked as blocked:
        what, root = blocked.args
        parent = os.path.dirname(root)
        print(
            f"cms-worktree-guard: blocked {what} in the cms-platform-config main checkout ({root}).\n"
            "The main checkout is read-only for agents (AGENTS.md, \"Working agreements\"). "
            "Start a worktree and work there:\n"
            f"  git -C {root} worktree add {parent}/cms-wt/<task> -b <branch> origin/release/foundation\n"
            "If this task already has one, run the command inside it (cd into it, or git -C <worktree>).",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as error:  # fail closed
        print(
            f"cms-worktree-guard: internal error, blocking to be safe: {error!r}\n"
            "Fix ~/.claude/hooks/cms-worktree-guard.py, or remove the hook from "
            ".claude/settings.local.json to bypass it.",
            file=sys.stderr,
        )
        sys.exit(2)
