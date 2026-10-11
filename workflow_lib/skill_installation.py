"""Codex skills deployment using the existing owned transaction/backup machinery."""

import hashlib
import json
from pathlib import Path

from workflow_lib.codex_skills import SKILLS, validate_skills
from workflow_lib.installation import digest, install, safe, uninstall

MANIFEST = "cao-codex-skills-manifest.json"
TRANSACTION = ".cao-codex-skills-transaction.json"


def layout(source, destination):
    validate_skills(source / "codex-skills")
    bundle = {}
    for directory in ("workflow_lib", "harness", "contracts"):
        for path in sorted((source / directory).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                bundle[str(path.relative_to(source))] = path.read_bytes()
    entries = {name: hashlib.sha256(data).hexdigest() for name, data in bundle.items()}
    version = hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()
    runtime = destination / ".cao-codex-runtime" / version
    files = {str(runtime.relative_to(destination) / name): data for name, data in bundle.items()}
    files[str(runtime.relative_to(destination) / "bundle.json")] = json.dumps(
        entries, sort_keys=True
    ).encode()
    for skill in SKILLS:
        for path in sorted((source / "codex-skills" / skill).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                relative = str(path.relative_to(source / "codex-skills"))
                data = path.read_bytes()
                if path.name == "run.py":
                    text = data.decode().replace(
                        "RUNTIME = None", "RUNTIME = " + repr(str(runtime))
                    )
                    # Verify the installed bundle before any imports/actions.
                    verification = """
if RUNTIME:
    import hashlib
    import json
    runtime = Path(RUNTIME)
    expected = json.loads((runtime / "bundle.json").read_text())
    actual = {str(p.relative_to(runtime)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in runtime.rglob("*") if p.is_file() and p.name != "bundle.json"
              and "__pycache__" not in p.parts and p.suffix != ".pyc"}
    version = hashlib.sha256(json.dumps(expected, sort_keys=True).encode()).hexdigest()
    if version != runtime.name or expected != actual or any(not (runtime / p).resolve().is_relative_to(runtime) for p in expected):
        raise RuntimeError("Installed skill runtime changed; reinstall before execution")
"""
                    data = text.replace(
                        "sys.path.insert(0,", verification + "\nsys.path.insert(0,"
                    ).encode()
                files[relative] = data
    return files


def validate_installed(destination):
    validate_skills(destination)


def install_skills(source, destination, *, dry_run=False, force=False):
    source, destination = Path(source).resolve(), Path(destination).absolute()
    # Reject symlink parents before resolving destination; don't deploy into a redirected root.
    if any(path.is_symlink() for path in (destination, *destination.parents)):
        raise ValueError("symlink installation scope forbidden")
    files = layout(source, destination)
    old_path = safe(destination, MANIFEST)
    old = json.loads(old_path.read_text()) if old_path.exists() else {"files": {}}
    for skill in SKILLS:
        folder = safe(destination, skill)
        if (
            folder.exists()
            and not force
            and not any(p.startswith(skill + "/") for p in old["files"])
        ):
            raise ValueError("existing unmanaged skill directory: " + skill)

    def check():
        validate_installed(destination)
        for relative, data in files.items():
            if safe(destination, relative).read_bytes() != data:
                raise ValueError("installed file verification failed")

    try:
        return install(
            source,
            destination,
            dry_run=dry_run,
            force=force,
            check=check,
            layout=files,
            manifest_name=MANIFEST,
            transaction_name=TRANSACTION,
            retained_prefixes=(".cao-codex-runtime/",),
        )
    except BaseException:
        prune_empty(destination, [str(destination / name) for name in files])
        raise


def uninstall_skills(destination, *, dry_run=False, force=False):
    destination = Path(destination).absolute()
    if any(path.is_symlink() for path in (destination, *destination.parents)):
        raise ValueError("symlink installation scope forbidden")
    paths = uninstall(
        destination,
        dry_run=dry_run,
        force=force,
        manifest_name=MANIFEST,
        transaction_name=TRANSACTION,
    )
    if not dry_run:
        # Remove only now-empty directories of owned files. Extra user files survive.
        prune_empty(destination, paths)
    return paths


def prune_empty(destination, paths):
    parents = {
        parent
        for name in paths
        for parent in Path(name).parents
        if parent != destination and parent.is_relative_to(destination)
    }
    for parent in sorted(parents, key=lambda p: len(p.parts), reverse=True):
        try:
            parent.rmdir()
        except OSError:
            pass


def verify_installation(destination):
    value = json.loads(safe(destination, MANIFEST).read_text())
    for relative, entry in value["files"].items():
        if digest(safe(destination, relative)) != entry["sha256"]:
            raise ValueError("installed file modified: " + relative)
    validate_installed(destination)
    return {"skills": list(SKILLS), "owned_files": len(value["files"])}
