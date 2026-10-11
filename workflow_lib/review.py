import hashlib
import json
import re

from workflow_lib.contracts import validate


def changed_lines(files):
    values = {}
    for item in files:
        filename = item["filename"]
        if filename.startswith("/") or ".." in filename.split("/"):
            raise ValueError("unsafe diff path")
        lines = {"LEFT": set(), "RIGHT": set()}
        old = new = None
        for line in item.get("patch", "").splitlines():
            match = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
            if match:
                old, new = int(match[1]), int(match[2])
            elif new is not None and line.startswith("+"):
                lines["RIGHT"].add(new)
                new += 1
            elif old is not None and line.startswith("-"):
                lines["LEFT"].add(old)
                old += 1
            elif new is not None and line.startswith(" "):
                old += 1
                new += 1
        values[filename] = lines
    return values


def marker(finding):
    value = json.dumps(
        {
            **{
                k: finding[k]
                for k in ("finding_id", "file", "line", "expected_behavior", "head_sha")
            },
            "side": finding.get("side", "RIGHT"),
        },
        sort_keys=True,
    )
    return "cao-finding:" + hashlib.sha256(value.encode()).hexdigest()


def inline_review(api, number, value, *, publish=True):
    validate(value, "review-result.schema.json")
    pr = api.pr(number)
    if pr["head_sha"] != value["head_sha"]:
        raise ValueError("review does not match latest SHA")
    if value["status"] == "PASS" and value["findings"]:
        raise ValueError("PASS cannot contain findings")
    if value["status"] == "CHANGES_REQUIRED" and not value["findings"]:
        raise ValueError("changes required needs findings")
    lines = changed_lines(api.call("diff", {"pr": number}))
    threads = api.threads(number)
    existing = {c["body"] for t in threads for c in t["comments"]}
    comments = []
    seen = set()
    for f in value["findings"]:
        if f["head_sha"] != pr["head_sha"] or f["line"] not in lines.get(f["file"], {}).get(
            f.get("side", "RIGHT"), set()
        ):
            raise ValueError("stale finding or line outside latest changed diff")
        key = marker(f)
        if key in seen:
            raise ValueError("duplicate finding in result")
        seen.add(key)
        if any(key in body for body in existing):
            continue
        comments.append(
            {
                "path": f["file"],
                "line": f["line"],
                "side": f.get("side", "RIGHT"),
                "body": f"<!-- {key} -->\n{f['priority']}: {f['expected_behavior']}\n{f['suggested_fix']}",
            }
        )
    if comments and publish:
        if api.pr(number)["head_sha"] != pr["head_sha"]:
            raise ValueError("SHA changed before publication")
        api.call("create_review", {"pr": number, "sha": pr["head_sha"], "comments": comments})
        actual = api.threads(number)
        for comment in comments:
            match = next(
                (t for t in actual if any(comment["body"] == c["body"] for c in t["comments"])),
                None,
            )
            if match is None:
                raise ValueError("published inline thread not confirmed")
            for finding in value["findings"]:
                if marker(finding) in comment["body"]:
                    finding["thread_id"] = match["thread_id"]
                    finding["comment_id"] = match["comments"][0]["databaseId"]
    return value
