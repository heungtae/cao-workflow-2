"""Deterministic DAG tasks on detached worktrees; source/base is never changed."""

import hashlib
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from workflow_lib.issue_state import State


def layers(tasks):
    by_id = {task["id"]: task for task in tasks}
    if len(by_id) != len(tasks):
        raise ValueError("duplicate task ID")
    pending = set(by_id)
    completed = set()
    output = []
    while pending:
        ready = sorted(i for i in pending if set(by_id[i]["depends"]) <= completed)
        if not ready:
            raise ValueError("cyclic DAG or unknown dependency")
        owners = set()
        for identity in ready:
            for filename in by_id[identity]["files"]:
                if (
                    Path(filename).is_absolute()
                    or ".." in Path(filename).parts
                    or any(
                        filename == owner
                        or filename.startswith(owner + "/")
                        or owner.startswith(filename + "/")
                        for owner in owners
                    )
                ):
                    raise ValueError("parallel file ownership collision/escape")
                owners.add(filename)
        output.append(ready)
        completed.update(ready)
        pending.difference_update(ready)
    return output


def isolated_fanout(project, tasks, run_id, execute, root, *, max_workers=2):
    if not 1 <= max_workers <= 4:
        raise ValueError("concurrency cap exceeded")
    ordered = layers(tasks)
    by_id = {task["id"]: task for task in tasks}
    root = Path(root).resolve()
    if root.is_relative_to(project.root):
        raise ValueError("worktrees must be outside source project")
    root.mkdir(parents=True, exist_ok=True)

    def git(path, *args):
        return subprocess.run(
            [
                "git",
                "-C",
                str(path),
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "commit.gpgsign=false",
                "-c",
                "user.name=CAO Workflows",
                "-c",
                "user.email=cao-workflows@localhost",
                *args,
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    base = git(project.root, "rev-parse", "HEAD")
    results = {}
    commits = {}
    ancestors = {}
    for layer in ordered:
        paths = {}
        for identity in layer:
            suffix = hashlib.sha256((run_id + ":" + identity).encode()).hexdigest()[:16]
            path = root / suffix
            paths[identity] = path
            ancestors[identity] = set(by_id[identity]["depends"])
            for parent in by_id[identity]["depends"]:
                ancestors[identity].update(ancestors[parent])
            if not path.exists():
                git(project.root, "worktree", "add", "--detach", str(path), base)
            for prior in [i for previous in ordered for i in previous if i in ancestors[identity]]:
                # Per-worktree checkpoint prevents duplicate dependency application.
                with State(
                    root / "dag-state.db",
                    run_id + ":" + identity,
                    {"base": base, "task": by_id[identity]},
                ) as state:
                    state.once(
                        "dependency-" + prior,
                        lambda prior=prior, path=path: git(path, "cherry-pick", commits[prior]),
                    )

        def call(identity, paths=paths):
            path = paths[identity]
            with State(
                root / "dag-state.db",
                run_id + ":" + identity,
                {"base": base, "task": by_id[identity]},
            ) as state:

                def perform():
                    value = execute(
                        by_id[identity],
                        path,
                        f"task-{hashlib.sha256(identity.encode()).hexdigest()[:16]}",
                    )
                    if value.get("status") not in {"PASS", "COMPLETED"}:
                        raise ValueError("DAG task failed; dependent tasks blocked")
                    changed = git(path, "status", "--porcelain")
                    for line in changed.splitlines():
                        if line[3:] not in by_id[identity]["files"]:
                            raise ValueError("task wrote outside declared ownership")
                    if changed:
                        git(path, "add", "--", *by_id[identity]["files"])
                        git(path, "commit", "-m", "CAO task " + identity)
                    return {
                        **value,
                        "commit_sha": git(path, "rev-parse", "HEAD"),
                        "worktree": str(path),
                    }

                value = state.once("task-result", perform)
                if git(path, "rev-parse", "HEAD") != value["commit_sha"] or git(
                    path, "status", "--porcelain"
                ):
                    raise ValueError("completed worktree changed after checkpoint")
                return value

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            values = list(pool.map(call, layer))
        results.update(zip(layer, values, strict=True))
        commits.update(
            (identity, value["commit_sha"]) for identity, value in zip(layer, values, strict=True)
        )
    return results
