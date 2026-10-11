"""Manifest-owned transactional deployment; never changes CAO configuration."""

import base64
import fcntl
import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

MANIFEST = "cao-workflows-manifest.json"
TRANSACTION = ".cao-workflows-transaction.json"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe(home, relative):
    path = home / relative
    if path.is_symlink() or not path.resolve().is_relative_to(home.resolve()):
        raise ValueError(f"unsafe installation path: {relative}")
    if ".." in Path(relative).parts or Path(relative).is_absolute():
        raise ValueError("invalid manifest path")
    return path


def atomic(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@contextmanager
def lock(home):
    home.mkdir(parents=True, exist_ok=True)
    with safe(home, ".cao-workflows-install.lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def inventory(source, home=None):
    bundle = {}
    for directory in ("workflow_lib", "harness", "contracts", "prompts"):
        for path in sorted((source / directory).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                bundle[str(Path(directory) / path.relative_to(source / directory))] = (
                    path.read_bytes()
                )
    entries = {name: hashlib.sha256(data).hexdigest() for name, data in bundle.items()}
    version = hashlib.sha256(
        json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    files = {
        str(Path("workflows/.cao-workflows-bundles") / version / name): data
        for name, data in bundle.items()
    }
    for path in sorted((source / "workflows").glob("*.py")):
        text = path.read_text()
        if "RUNTIME_HOME = None" in text:
            if home is None:
                raise ValueError("deployment requires an explicit runtime home")
            text = text.replace("RUNTIME_HOME = None", "RUNTIME_HOME = " + repr(str(home)))
            text = text.replace("BUNDLE_DIGEST = None", "BUNDLE_DIGEST = " + repr(version))
        files["workflows/" + path.name] = text.encode()
    for path in sorted((source / "profiles").glob("*.md")):
        files["agent-store/" + path.name] = path.read_bytes()
    return files


def _install_locked(source, home, *, dry_run=False, force=False, profile_mode="copy", check):
    if profile_mode != "copy":
        raise ValueError("link mode unsupported: immutable deployed snapshot required")
    files = inventory(source, home)
    manifest_path = safe(home, MANIFEST)
    old = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"files": {}}
    new = {"version": 1, "release": "1.0.0", "cao_compatibility": "2.5.0", "files": {}}
    before = {}
    for relative, data in files.items():
        path = safe(home, relative)
        prior = old["files"].get(relative)
        current = path.read_bytes() if path.exists() else None
        if current is not None and (prior is None or digest(path) != prior["sha256"]) and not force:
            raise ValueError(f"file collision or user modification: {relative}")
        before[relative] = current
        backup = (
            prior.get("backup")
            if prior
            else (base64.b64encode(current).decode() if current is not None else None)
        )
        new["files"][relative] = {"sha256": hashlib.sha256(data).hexdigest(), "backup": backup}
    # Retain immutable dependency versions for CAO's frozen resume snapshots.
    for relative, entry in old["files"].items():
        if relative not in files and relative.startswith("workflows/.cao-workflows-bundles/"):
            path = safe(home, relative)
            if not path.is_file() or digest(path) != entry["sha256"]:
                raise ValueError("retained resume bundle modified/missing")
            files[relative] = path.read_bytes()
            before[relative] = path.read_bytes()
            new["files"][relative] = entry
    # Refuse upgrades that silently orphan non-bundle owned files.
    if set(old["files"]) - set(files):
        raise ValueError("uninstall old version before removing installed resources")
    if dry_run:
        return new
    # Recheck after acquiring the lock, rejecting racing installers/user edits.
    for relative, content in before.items():
        path = safe(home, relative)
        if (path.read_bytes() if path.exists() else None) != content:
            raise ValueError("installation changed during preflight")
    old_manifest = manifest_path.read_bytes() if manifest_path.exists() else None
    prepared = {**before, MANIFEST: old_manifest}
    after = {**files, MANIFEST: json.dumps(new, sort_keys=True, indent=2).encode()}
    begin(home, prepared, after)
    try:
        for relative, data in files.items():
            atomic(safe(home, relative), data)
        check()
        atomic(manifest_path, json.dumps(new, sort_keys=True, indent=2).encode())
    except BaseException:
        for relative, content in before.items():
            path = safe(home, relative)
            if content is None:
                path.unlink(missing_ok=True)
            else:
                atomic(path, content)
        if old_manifest is None:
            manifest_path.unlink(missing_ok=True)
        else:
            atomic(manifest_path, old_manifest)
        safe(home, TRANSACTION).unlink(missing_ok=True)
        raise
    safe(home, TRANSACTION).unlink(missing_ok=True)
    return new


def _uninstall_locked(home, *, dry_run=False, force=False):
    manifest_path = safe(home, MANIFEST)
    if not manifest_path.exists():
        return []
    data = json.loads(manifest_path.read_text())
    paths = []
    for relative, entry in data["files"].items():
        path = safe(home, relative)
        if path.exists() and digest(path) != entry["sha256"] and not force:
            raise ValueError(f"user modified: {relative}")
        paths.append((path, entry))
    if not dry_run:
        before = {
            str(path.relative_to(home)): path.read_bytes() if path.exists() else None
            for path, _ in paths
        }
        after = {
            str(path.relative_to(home)): base64.b64decode(entry["backup"], validate=True)
            if entry["backup"] is not None
            else None
            for path, entry in paths
        }
        before[MANIFEST] = manifest_path.read_bytes()
        after[MANIFEST] = None
        begin(home, before, after)
        for path, entry in paths:
            if entry["backup"] is not None:
                atomic(path, base64.b64decode(entry["backup"], validate=True))
            else:
                path.unlink(missing_ok=True)
        manifest_path.unlink()
        safe(home, TRANSACTION).unlink(missing_ok=True)
    return [str(path) for path, _ in paths]


def begin(home, before, after):
    records = {
        relative: {
            "before": base64.b64encode(content).decode() if content is not None else None,
            "after": hashlib.sha256(after[relative]).hexdigest()
            if after[relative] is not None
            else None,
        }
        for relative, content in before.items()
    }
    atomic(safe(home, TRANSACTION), json.dumps(records, sort_keys=True).encode())


def recover(home):
    journal = safe(home, TRANSACTION)
    if not journal.exists():
        return
    records = json.loads(journal.read_text())
    restored = {}
    for relative, entry in records.items():
        path = safe(home, relative)
        before = (
            base64.b64decode(entry["before"], validate=True)
            if entry["before"] is not None
            else None
        )
        current = path.read_bytes() if path.exists() else None
        current_hash = hashlib.sha256(current).hexdigest() if current is not None else None
        if current != before and current_hash != entry["after"]:
            raise ValueError("user edited interrupted transaction; manual recovery required")
        restored[relative] = before
    for relative, content in restored.items():
        path = safe(home, relative)
        if content is None:
            path.unlink(missing_ok=True)
        else:
            atomic(path, content)
    journal.unlink()


def install(source, home, *, dry_run=False, force=False, profile_mode="copy", check):
    if dry_run:
        if safe(home, TRANSACTION).exists():
            raise ValueError("incomplete transaction needs non-dry-run recovery")
        return _install_locked(
            source, home, dry_run=True, force=force, profile_mode=profile_mode, check=check
        )
    with lock(home):
        recover(home)
        return _install_locked(source, home, force=force, profile_mode=profile_mode, check=check)


def uninstall(home, *, dry_run=False, force=False):
    if not home.exists():
        return []
    if dry_run:
        if safe(home, TRANSACTION).exists():
            raise ValueError("incomplete transaction needs non-dry-run recovery")
        return _uninstall_locked(home, dry_run=True, force=force)
    with lock(home):
        recover(home)
        return _uninstall_locked(home, force=force)
