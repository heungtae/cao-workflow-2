"""Exact owned branch pushes and idempotent draft PR creation."""

import hashlib
import re
import subprocess
from pathlib import Path

from workflow_lib.merge_guard import guard_argv


class Repository:
    def __init__(self, project, repo, branch, base):
        self.project = project
        self.repo = repo
        self.branch = branch
        self.base = base
        if not re.fullmatch(r"cao/[A-Za-z0-9_-]+", branch) or branch in {base, "main", "master"}:
            raise ValueError("owned non-base feature branch required")
        actual = self.git("branch", "--show-current").strip()
        if actual != branch:
            raise ValueError("working directory is not on owned feature branch")
        origin = self.git("remote", "get-url", "origin").strip()
        push_origins = self.git("remote", "get-url", "--all", "--push", "origin").splitlines()
        if push_origins != [origin]:
            raise ValueError("push URL must match the single approved origin")
        if origin not in {
            f"https://github.com/{repo}.git",
            f"https://github.com/{repo}",
            f"git@github.com:{repo}.git",
        }:
            raise ValueError("origin must exactly match approved GitHub repository")

    def git(self, *args):
        argv = guard_argv(["git", *args], branch=self.branch, base=self.base)
        process = subprocess.run(
            [
                "git",
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "commit.gpgsign=false",
                "-c",
                "protocol.ext.allow=never",
                "-c",
                "core.sshCommand=ssh -F /dev/null",
                "-c",
                "credential.helper=",
                "-c",
                "credential.helper=!gh auth git-credential",
                *argv[1:],
            ],
            cwd=self.project.root,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if process.returncode:
            raise ValueError("Git operation failed; no automatic force/retry")
        return process.stdout

    def remote_sha(self):
        output = self.git("ls-remote", "--heads", "origin", f"refs/heads/{self.branch}").strip()
        return output.split()[0] if output else None

    def commit_push(self, files, marker, *, expected_remote=None):
        for filename in files:
            if (
                Path(filename).is_absolute()
                or ".." in Path(filename).parts
                or filename.startswith(".git")
            ):
                raise ValueError("unsafe staging path")
        if self.remote_sha() != expected_remote:
            raise ValueError("remote branch changed before commit/push")
        if files:
            self.git("add", "--", *files)
        changed = self.git("diff", "--cached", "--name-only").splitlines()
        if set(changed) - set(files):
            raise ValueError("unrelated staged files; refusing commit")
        if changed:
            self.git("commit", "-m", f"CAO: {marker}")
        sha = self.git("rev-parse", "HEAD").strip()
        self.git("push", "origin", f"HEAD:refs/heads/{self.branch}")
        if self.remote_sha() != sha:
            raise ValueError("remote push verification failed")
        return sha


def create_pr(api, repository, state, title, body, files):
    branch = repository.branch
    marker = "cao-issue:" + state.key

    def existing():
        pages = api.call("list_prs", {"branch": branch})
        values = [p for page in pages for p in page]
        if len(values) > 1:
            raise ValueError("duplicate PRs for owned branch")
        if values:
            pr = api.pr(values[0]["number"])
            if (
                pr["branch"] != branch
                or pr["head_sha"] != repository.git("rev-parse", "HEAD").strip()
            ):
                raise ValueError("existing PR branch/SHA differs from local checkpoint")
            return {"pr_number": pr["number"], "head_sha": pr["head_sha"]}
        return None

    found = existing()
    if found:
        return found

    def reconcile_push():
        remote = repository.remote_sha()
        local = repository.git("rev-parse", "HEAD").strip()
        return local if remote == local else None

    sha = state.once(
        "initial-push",
        lambda: repository.commit_push(files, marker, expected_remote=repository.remote_sha()),
        reconcile=reconcile_push,
    )

    def perform():
        value = api.call(
            "create_pr",
            {
                "branch": branch,
                "base": repository.base,
                "title": title,
                "body": body + "\n<!-- " + marker + " -->",
            },
        )
        number = value["number"]
        pr = api.pr(number)
        if pr["head_sha"] != sha:
            raise ValueError("created PR SHA differs from pushed checkpoint")
        return {"pr_number": number, "head_sha": sha}

    return state.once("draft-pr", perform, reconcile=existing)


def issue_worktree(project, event, run_id, root):
    branch = (
        "cao/issue-"
        + str(event["issue_number"])
        + "-"
        + hashlib.sha256(event["repo"].encode()).hexdigest()[:8]
    )
    path = (
        Path(root).resolve()
        / hashlib.sha256((event["repo"] + ":" + str(event["issue_number"])).encode()).hexdigest()[
            :20
        ]
    )
    if path.is_relative_to(project.root):
        raise ValueError("issue worktree root must be separate from target")
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            "git",
            "-C",
            str(project.root),
            "worktree",
            "add",
            "-b",
            branch,
            str(path),
            "HEAD",
        ]
        subprocess.run(command, check=True, capture_output=True)
    current = subprocess.run(
        ["git", "-C", str(path), "branch", "--show-current"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if current != branch:
        raise ValueError("existing worktree not owned by issue")
    return path, branch
