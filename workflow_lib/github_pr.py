"""Enumerated GitHub operations only; no generic URL or query supplied by agents."""

import copy
import json
import re
import subprocess

READS = {"get_pr", "list_prs", "threads", "checks", "diff", "issue"}
WRITES = {"create_pr", "create_review", "reply", "resolve"}

THREAD_QUERY = """query($owner:String!,$name:String!,$pr:Int!,$cursor:String){repository(owner:$owner,name:$name){pullRequest(number:$pr){reviewThreads(first:100,after:$cursor){pageInfo{hasNextPage endCursor} nodes{id isResolved isOutdated path line comments(first:100){nodes{databaseId body originalCommit{oid}} pageInfo{hasNextPage}}}}}}}"""
REPLY_QUERY = """mutation($thread:ID!,$body:String!){addPullRequestReviewThreadReply(input:{pullRequestReviewThreadId:$thread,body:$body}){comment{databaseId}}}"""
RESOLVE_QUERY = """mutation($thread:ID!){resolveReviewThread(input:{threadId:$thread}){thread{id isResolved}}}"""


class GitHub:
    def __init__(self, repo, *, dry_run=True, authorized=False, policy=None, transport=None):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
            raise ValueError("invalid repository")
        self.repo = repo
        self.dry_run = dry_run
        self.authorized = authorized
        self.policy = policy or {}
        self.transport = transport or self._transport
        self.audit = []

    def call(self, operation, payload):
        if operation not in READS | WRITES:
            raise ValueError("operation not allowlisted")
        if operation in WRITES and (
            self.dry_run
            or not self.authorized
            or self.repo not in self.policy.get("repositories", [])
            or operation not in self.policy.get("github_operations", [])
        ):
            raise PermissionError(
                "external write needs explicit authorization and operation policy"
            )
        self.audit.append({"operation": operation, "write": operation in WRITES})
        return self.transport(operation, payload)

    def _check_endpoint(self, method, endpoint, body):
        prefix = "repos/" + re.escape(self.repo)
        operation = None
        reads = [
            prefix + r"/pulls/\d+",
            prefix + r"/pulls/\d+/files(?:\?per_page=100)?",
            prefix + r"/issues/\d+",
            prefix + r"/commits/[0-9a-f]{40}/(?:check-runs|statuses)(?:\?per_page=100)?",
            prefix + r"/pulls\?state=open&head=[A-Za-z0-9_.-]+:cao/[A-Za-z0-9_-]+",
        ]
        if method == "GET" and any(re.fullmatch(p, endpoint) for p in reads):
            return
        if method == "POST" and re.fullmatch(prefix + r"/pulls", endpoint):
            operation = "create_pr"
        elif method == "POST" and re.fullmatch(prefix + r"/pulls/\d+/reviews", endpoint):
            operation = "create_review"
        elif method == "POST" and endpoint == "graphql" and isinstance(body, dict):
            query = body.get("query")
            if query == THREAD_QUERY:
                return
            operation = (
                "reply" if query == REPLY_QUERY else "resolve" if query == RESOLVE_QUERY else None
            )
        if operation is None:
            raise ValueError("HTTP route/method not allowlisted")
        if (
            self.dry_run
            or not self.authorized
            or self.repo not in self.policy.get("repositories", [])
            or operation not in self.policy.get("github_operations", [])
        ):
            raise PermissionError("raw write denied by authorization policy")

    def _gh(self, args):
        if not args or args[0] != "api":
            raise ValueError("only fixed GitHub API reads allowed")
        endpoints = [a for a in args[1:] if a.startswith("repos/")]
        if len(endpoints) != 1:
            raise ValueError("one validated endpoint required")
        self._check_endpoint("GET", endpoints[0], None)
        proc = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=60)
        if proc.returncode:
            raise PermissionError(
                "GitHub request failed; inspect authentication/permissions (no secret output logged)"
            )
        try:
            if "--paginate" in args:
                decoder = json.JSONDecoder()
                remaining = proc.stdout.strip()
                value = []
                while remaining:
                    page, end = decoder.raw_decode(remaining)
                    if not isinstance(page, (list, dict)):
                        raise ValueError("invalid paginated GitHub response")
                    value.append(page)
                    remaining = remaining[end:].lstrip()
                if not value:
                    raise ValueError("empty paginated GitHub response")
            else:
                value = json.loads(proc.stdout)
        except ValueError as error:
            raise ValueError("invalid GitHub response") from error
        if isinstance(value, dict) and value.get("errors"):
            raise PermissionError("GraphQL returned errors; reconcile before retry")
        return value

    def _rest(self, method, endpoint, body=None):
        self._check_endpoint(method, endpoint, body)
        args = ["api", "--method", method, endpoint]
        # Send structured JSON over stdin; never put untrusted text into shell commands.
        if body is not None:
            proc = subprocess.run(
                ["gh", *args, "--input", "-"],
                input=json.dumps(body),
                capture_output=True,
                text=True,
                timeout=60,
            )
            if proc.returncode:
                raise PermissionError("GitHub write failed; reconcile state before retry")
            value = json.loads(proc.stdout)
            if isinstance(value, dict) and value.get("errors"):
                raise PermissionError("GitHub mutation failed")
            return value
        return self._gh(args)

    def _graphql(self, query, **variables):
        if query not in {THREAD_QUERY, REPLY_QUERY, RESOLVE_QUERY}:
            raise ValueError("query not allowlisted")
        return self._rest("POST", "graphql", {"query": query, "variables": variables})["data"]

    def _transport(self, operation, p):
        prefix = f"repos/{self.repo}"
        if operation in {"get_pr", "diff", "checks", "threads", "create_review"}:
            number = p.get("pr")
            if not isinstance(number, int) or number < 1:
                raise ValueError("positive PR number required")
        if operation == "get_pr":
            raw = self._rest("GET", f"{prefix}/pulls/{number}")
            return {
                "number": number,
                "state": raw["state"].upper(),
                "head_sha": raw["head"]["sha"],
                "branch": raw["head"]["ref"],
                "base": raw["base"]["ref"],
                "head_repo": raw["head"]["repo"]["full_name"] if raw["head"]["repo"] else None,
                "base_repo": raw["base"]["repo"]["full_name"],
            }
        if operation == "list_prs":
            return self._gh(
                [
                    "api",
                    f"{prefix}/pulls?state=open&head={self.repo.split('/')[0]}:{p['branch']}",
                    "--paginate",
                ]
            )
        if operation == "issue":
            return self._rest("GET", f"{prefix}/issues/{int(p['number'])}")
        if operation == "diff":
            pages = self._gh(["api", f"{prefix}/pulls/{number}/files?per_page=100", "--paginate"])
            return [item for page in pages for item in page]
        if operation == "checks":
            sha = p["sha"]
            if not re.fullmatch(r"[0-9a-f]{40}", sha):
                raise ValueError("invalid commit SHA")
            pages = self._gh(
                ["api", f"{prefix}/commits/{sha}/check-runs?per_page=100", "--paginate"]
            )
            values = {
                c["name"]: c.get("conclusion") if c["status"] == "completed" else "pending"
                for page in pages
                for c in page["check_runs"]
            }
            statuses = self._gh(
                ["api", f"{prefix}/commits/{sha}/statuses?per_page=100", "--paginate"]
            )
            # API returns newest first. Preserve the newest result for each context.
            for page in statuses:
                for item in page:
                    values.setdefault(item["context"], item["state"])
            return values
        if operation == "threads":
            owner, name = self.repo.split("/")
            cursor = None
            values = []
            while True:
                data = self._graphql(THREAD_QUERY, owner=owner, name=name, pr=number, cursor=cursor)
                connection = data["repository"]["pullRequest"]["reviewThreads"]
                for node in connection["nodes"]:
                    if node["comments"]["pageInfo"]["hasNextPage"]:
                        raise ValueError("oversized thread: complete comments required")
                    comments = node["comments"]["nodes"]
                    values.append(
                        {
                            "thread_id": node["id"],
                            "is_resolved": node["isResolved"],
                            "outdated": node["isOutdated"],
                            "file": node["path"],
                            "line": node["line"],
                            "comments": comments,
                            "head_sha": comments[0]["originalCommit"]["oid"] if comments else None,
                        }
                    )
                if not connection["pageInfo"]["hasNextPage"]:
                    return values
                cursor = connection["pageInfo"]["endCursor"]
        if operation == "create_pr":
            return self._rest(
                "POST",
                f"{prefix}/pulls",
                {
                    "title": p["title"],
                    "body": p["body"],
                    "head": p["branch"],
                    "base": p["base"],
                    "draft": True,
                },
            )
        if operation == "create_review":
            return self._rest(
                "POST",
                f"{prefix}/pulls/{number}/reviews",
                {"commit_id": p["sha"], "event": "COMMENT", "comments": p["comments"]},
            )
        if operation == "reply":
            data = self._graphql(REPLY_QUERY, thread=p["thread_id"], body=p["body"])
            return data["addPullRequestReviewThreadReply"]["comment"]["databaseId"]
        if operation == "resolve":
            data = self._graphql(RESOLVE_QUERY, thread=p["thread_id"])
            return data["resolveReviewThread"]["thread"]["isResolved"]
        raise ValueError("unimplemented allowed operation")

    def pr(self, number):
        value = self.call("get_pr", {"pr": number})
        if (
            value["state"] != "OPEN"
            or value.get("head_repo") != self.repo
            or value.get("base_repo") != self.repo
        ):
            raise ValueError("PR must be open and belong to approved repository, not a fork")
        return value

    def threads(self, number):
        return self.call("threads", {"pr": number})

    def ci(self, number, sha, required):
        if not required:
            raise ValueError("explicit required CI contexts required")
        if self.pr(number)["head_sha"] != sha:
            raise ValueError("SHA race")
        values = self.call("checks", {"pr": number, "sha": sha})
        return all(values.get(name) in {"success"} for name in required)


class MockGitHub(GitHub):
    """Stateful fixture adapter; writes never leave this process."""

    def __init__(self, head="a" * 40):
        self.current = {
            "number": 1,
            "state": "OPEN",
            "head_sha": head,
            "branch": "cao/issue-1",
            "base": "main",
            "head_repo": "owner/repo",
            "base_repo": "owner/repo",
        }
        self.thread_values = []
        self.writes = []
        self.check_values = {"test": "success"}
        self.fail_resolve = False
        self.fail_permission = False
        self.changed_lines = [{"filename": "app.py", "patch": "@@ -1,1 +1,2 @@\n context\n+new"}]
        super().__init__(
            "owner/repo",
            dry_run=False,
            authorized=True,
            policy={"repositories": ["owner/repo"], "github_operations": sorted(WRITES)},
            transport=self._mock,
        )

    def _mock(self, op, p):
        if self.fail_permission:
            raise PermissionError("fixture permission denied")
        if op in WRITES:
            self.writes.append(op)
        if op == "get_pr":
            return copy.deepcopy(self.current)
        if op == "list_prs":
            return [[{"number": 1, "head": {"ref": self.current["branch"]}}]]
        if op == "threads":
            return copy.deepcopy(self.thread_values)
        if op == "checks":
            return dict(self.check_values)
        if op == "diff":
            return copy.deepcopy(self.changed_lines)
        if op == "create_pr":
            return {"number": 1}
        if op == "create_review":
            for comment in p["comments"]:
                self.thread_values.append(
                    {
                        "thread_id": f"T{len(self.thread_values) + 1}",
                        "is_resolved": False,
                        "outdated": False,
                        "file": comment["path"],
                        "line": comment["line"],
                        "head_sha": p["sha"],
                        "comments": [
                            {
                                "databaseId": len(self.thread_values) + 1,
                                "body": comment["body"],
                                "originalCommit": {"oid": p["sha"]},
                            }
                        ],
                    }
                )
            return {"id": 1}
        if op == "reply":
            thread = next(t for t in self.thread_values if t["thread_id"] == p["thread_id"])
            identity = 100 + len(thread["comments"])
            thread["comments"].append(
                {
                    "databaseId": identity,
                    "body": p["body"],
                    "originalCommit": {"oid": self.current["head_sha"]},
                }
            )
            return identity
        if op == "resolve":
            if not self.fail_resolve:
                next(t for t in self.thread_values if t["thread_id"] == p["thread_id"])[
                    "is_resolved"
                ] = True
            return not self.fail_resolve
        raise ValueError("fixture operation unsupported")
