#!/usr/bin/env python3
"""Opt-in one-shot scheduling and authenticated localhost webhooks."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workflow_lib.github_pr import GitHub
from workflow_lib.issue_state import State
from workflow_lib.jira import Jira
from workflow_lib.project import Project
from workflow_lib.triggers import CaoLauncher, dispatch, pr_event, webhook_event


def checkout(project, repo, number, sha, root):
    root = Path(root).resolve()
    if root.is_relative_to(project.root):
        raise ValueError("trigger worktrees must be outside source")

    def git(*args):
        proc = subprocess.run(
            [
                "git",
                "-C",
                str(project.root),
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "protocol.ext.allow=never",
                *args,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return proc.stdout.strip()

    origin = git("remote", "get-url", "origin")
    if origin not in {
        f"https://github.com/{repo}",
        f"https://github.com/{repo}.git",
        f"git@github.com:{repo}.git",
    }:
        raise ValueError("trigger source origin mismatch")
    root.mkdir(parents=True, exist_ok=True)
    path = root / hashlib.sha256((repo + ":" + str(number) + ":" + sha).encode()).hexdigest()[:24]
    if not path.exists():
        reference = "refs/cao/pr-" + str(number) + "-" + sha
        git("fetch", "origin", f"refs/pull/{number}/head:{reference}")
        if git("rev-parse", reference) != sha:
            raise ValueError("PR moved during trigger fetch")
        git("worktree", "add", "--detach", str(path), sha)
    proc = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    )
    status = subprocess.run(
        ["git", "-C", str(path), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    )
    if proc.stdout.strip() != sha or status.stdout.strip():
        raise ValueError("trigger worktree changed after preparation")
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binding", required=True, help="operator-owned JSON binding/policy")
    parser.add_argument("--source", choices=["github-pr", "jira"], default="github-pr")
    parser.add_argument(
        "--execute", action="store_true", help="explicitly launch approved CAO workflows"
    )
    parser.add_argument("--authorize-publication", action="store_true")
    parser.add_argument("--events-file", help="offline fixture preflight only")
    parser.add_argument(
        "--serve", action="store_true", help="authenticated localhost GitHub webhook listener"
    )
    parser.add_argument("--port", type=int, default=19890)
    args = parser.parse_args()
    binding = json.loads(Path(args.binding).resolve(strict=True).read_text())
    policy = json.loads(Path(binding["policy"]).resolve(strict=True).read_text())
    project = Project(binding["project"], binding["feature"])
    binary = os.environ.get("CAO_BIN", str(ROOT / ".venv/bin/cao"))
    launcher = CaoLauncher(binary)
    state_path = Path(binding["state_file"]).resolve()
    if state_path.is_relative_to(project.root):
        raise ValueError("trigger state must be outside target")
    identity = (
        "trigger-"
        + hashlib.sha256(
            json.dumps({"binding": binding, "policy": policy}, sort_keys=True).encode()
        ).hexdigest()[:24]
    )

    def submit(event):
        target = dict(binding)
        if event["source"] == "github-pr":
            api = GitHub(event["repo"])
            if event["repo"] not in policy.get("repositories", []):
                raise PermissionError("repository not allowed")
            if not args.events_file:
                actual = api.pr(event["pr_number"])
                if actual["head_sha"] != event["head_sha"]:
                    raise ValueError("stale trigger SHA")
            if args.execute:
                path = checkout(
                    project,
                    event["repo"],
                    event["pr_number"],
                    event["head_sha"],
                    binding["worktree_root"],
                )
                target["project"] = str(path)
        with State(state_path, identity, {"binding": binding, "policy": policy}) as state:
            return dispatch(
                event,
                target,
                policy,
                state,
                launcher,
                execute=args.execute,
                authorize_publication=args.authorize_publication,
                reconcile=launcher.reconcile,
            )

    if args.events_file:
        if args.execute or args.serve:
            raise PermissionError("unsigned fixture events are dry-run only")
        events = json.loads(Path(args.events_file).read_text())
    elif args.serve:
        if args.source != "github-pr" or not 1024 <= args.port <= 65535:
            raise ValueError("webhook source/port invalid")
        secret = os.environ.get("CAO_WEBHOOK_SECRET")
        if not secret:
            raise PermissionError("CAO_WEBHOOK_SECRET required")

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.connection.settimeout(10)
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 1024 * 1024:
                        raise ValueError("invalid payload length")
                    raw = self.rfile.read(length)
                    event = webhook_event(
                        raw,
                        self.headers.get("X-Hub-Signature-256"),
                        secret,
                        self.headers.get("X-GitHub-Event"),
                    )
                    value = submit(event) if event else {"status": "IGNORED"}
                    code = 200
                except (
                    ValueError,
                    PermissionError,
                    RuntimeError,
                    OSError,
                    KeyError,
                    subprocess.CalledProcessError,
                ) as error:
                    value = {"status": "REJECTED", "error_type": type(error).__name__}
                    code = 403
                encoded = json.dumps(value).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, *unused):
                pass

        with HTTPServer(("127.0.0.1", args.port), Handler) as server:
            server.serve_forever()
        return 0
    elif args.source == "jira":
        keys = binding.get("jira_keys", [])
        if len(keys) > 100:
            raise ValueError("one-shot Jira batch cap is 100")
        jira = Jira(binding["jira_url"], policy)
        events = [jira.event(key) for key in keys]
    else:
        numbers = binding.get("pr_numbers", [])
        if len(numbers) > 100:
            raise ValueError("one-shot PR batch cap is 100")
        api = GitHub(policy["repo"])
        events = [
            pr_event(policy["repo"], number, api.pr(number)["head_sha"]) for number in numbers
        ]
    if len(events) > 100:
        raise ValueError("trigger batch cap is 100")
    print(json.dumps([submit(event) for event in events], indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (
        ValueError,
        PermissionError,
        RuntimeError,
        OSError,
        KeyError,
        subprocess.CalledProcessError,
    ) as error:
        print("trigger rejected: " + type(error).__name__, file=sys.stderr)
        sys.exit(1)
