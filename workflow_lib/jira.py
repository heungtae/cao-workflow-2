"""Jira Cloud v3 read-only input adapter. Jira never enters the auto-Issue path."""

import base64
import json
import os
import re
import urllib.parse
import urllib.request

from harness.quality_gate import redact


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise PermissionError("Jira credential redirects are forbidden")


class Jira:
    def __init__(self, base_url, policy, *, transport=None):
        parsed = urllib.parse.urlsplit(base_url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in policy.get("jira_hosts", [])
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
            or parsed.port not in {None, 443}
        ):
            raise PermissionError("Jira host/scheme not approved")
        self.base_url = base_url.rstrip("/")
        self.policy = policy
        self.transport = transport or self._read

    def _read(self, key):
        email = os.environ.get("JIRA_EMAIL")
        token = os.environ.get("JIRA_API_TOKEN")
        if not email or not token:
            raise PermissionError("Jira read credentials required in environment")
        encoded = base64.b64encode((email + ":" + token).encode()).decode()
        request = urllib.request.Request(
            self.base_url + "/rest/api/3/issue/" + key + "?fields=summary,description,project",
            headers={"Accept": "application/json", "Authorization": "Basic " + encoded},
            method="GET",
        )
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
            data = response.read(2 * 1024 * 1024 + 1)
        if len(data) > 2 * 1024 * 1024:
            raise ValueError("Jira response too large")
        return json.loads(data)

    def event(self, key):
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,30}-[1-9][0-9]{0,12}", key):
            raise ValueError("invalid Jira key")
        if key.split("-")[0] not in self.policy.get("jira_projects", []):
            raise PermissionError("Jira project not approved")
        value = self.transport(key)
        fields = value["fields"]
        if (
            value["key"] != key
            or fields["project"]["key"] != key.split("-")[0]
            or not isinstance(fields.get("summary"), str)
        ):
            raise ValueError("Jira result does not match approved issue")
        description = fields.get("description")
        texts = []
        pending = [description]
        inspected = 0
        while pending:
            inspected += 1
            if inspected > 10000:
                raise ValueError("Jira description too complex")
            node = pending.pop()
            if isinstance(node, str):
                texts.append(node)
            elif isinstance(node, dict):
                if isinstance(node.get("text"), str):
                    texts.append(node["text"])
                pending.extend(reversed(node.get("content", [])))
        requirement = fields["summary"] + "\n" + "\n".join(texts)
        if len(requirement.encode()) > 16000 or redact(requirement) != requirement:
            raise ValueError("Jira requirement too large or contains possible secret")
        return {
            "source": "jira",
            "workflow": "spec-planner",
            "jira_key": key,
            "requirement": requirement,
            "repo": None,
            "pr_number": None,
            "head_sha": None,
        }
