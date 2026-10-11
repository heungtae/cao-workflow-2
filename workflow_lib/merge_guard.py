"""Runtime argv fencing and AST inspection of executable source."""

import ast
import re
from pathlib import Path

DENIED = re.compile(
    r"(?i)(auto.?merge|merge.?queue|mergePullRequest|enablePullRequestAutoMerge|enqueuePullRequest|/merge(?:\b|/)|bypass|closeIssue)"
)


def guard_argv(argv, *, branch=None, base=None):
    if not isinstance(argv, (list, tuple)) or not argv or not all(isinstance(x, str) for x in argv):
        raise ValueError("commands must be nonempty argv arrays")
    if any(DENIED.search(x) for x in argv):
        raise ValueError("forbidden operation")
    name = Path(argv[0]).name
    if name in {"bash", "sh", "zsh", "eval", "curl", "wget"}:
        raise ValueError("shell or raw HTTP commands forbidden")
    if name == "gh":
        raise ValueError("GitHub operations must use allowlisted adapter")
    if name == "git":
        if len(argv) < 2 or argv[1] not in {
            "rev-parse",
            "status",
            "diff",
            "branch",
            "remote",
            "ls-remote",
            "add",
            "commit",
            "push",
        }:
            raise ValueError("Git subcommand/options not allowlisted")
        if "merge" in argv or "push" in argv and (not branch or not base):
            raise ValueError("merge or unspecified push forbidden")
        if "push" in argv:
            expected = ["git", "push", "origin", f"HEAD:refs/heads/{branch}"]
            if (
                list(argv) != expected
                or branch in {base, "main", "master"}
                or not branch.startswith("cao/")
            ):
                raise ValueError("only exact owned feature branch pushes allowed")
    return list(argv)


def inspect_source(root):
    violations = []
    for directory in ("workflow_lib", "workflows", "harness", "scripts", "codex-skills"):
        for path in (Path(root) / directory).rglob("*.py"):
            if path.name == "merge_guard.py":
                continue
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    for argument in node.args:
                        if isinstance(argument, (ast.List, ast.Tuple)):
                            literal = [
                                item.value
                                for item in argument.elts
                                if isinstance(item, ast.Constant) and isinstance(item.value, str)
                            ]
                            if literal and literal[0] in {
                                "git",
                                "gh",
                                "curl",
                                "wget",
                                "bash",
                                "sh",
                            }:
                                try:
                                    # Dynamic guarded pushes have starred arguments, so
                                    # only wholly literal argv calls are inspected here.
                                    if len(literal) == len(argument.elts):
                                        guard_argv(literal)
                                except ValueError:
                                    violations.append(f"{path}:{node.lineno}")
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    if DENIED.search(node.value) or re.search(
                        r"\b(?:gh pr merge|git merge|git push origin (?:main|master)|issues/\S+/close)\b",
                        node.value,
                    ):
                        violations.append(f"{path}:{node.lineno}")
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if node.func.attr in {"system", "eval", "exec"}:
                        violations.append(f"{path}:{node.lineno}")
    for path in (Path(root) / "scripts").glob("*.sh"):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if DENIED.search(line) or re.search(
                r"\b(?:gh\s+pr\s+merge|git\s+merge|git\s+push)\b", line
            ):
                violations.append(f"{path}:{number}")
    return violations
