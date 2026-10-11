import re


def traceability(project, mapping):
    ids = set(re.findall(r"\bREQ-[A-Za-z0-9_-]+", project.specs()["spec.md"]))
    if not ids or not isinstance(mapping, list):
        raise ValueError("spec must declare requirement IDs and traceability mappings")
    seen = set()
    for entry in mapping:
        req = entry.get("requirement_id")
        if req not in ids or not entry.get("tests") or not entry.get("implementation"):
            raise ValueError("invalid requirement mapping")
        for key in ("tests", "implementation"):
            for relative in entry[key]:
                path = project.root / relative
                if not path.resolve().is_relative_to(project.root) or not path.is_file():
                    raise ValueError("traceability refers to missing/unsafe file")
        seen.add(req)
    if seen != ids:
        raise ValueError("uncovered requirements: " + ", ".join(sorted(ids - seen)))
    return mapping
