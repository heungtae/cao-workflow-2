"""Linux execution isolation for untrusted target tests, with no host home/network."""

from pathlib import Path


def isolated_argv(project, argv, *, readonly_roots=()):
    args = [
        "bwrap",
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--clearenv",
        "--setenv",
        "PATH",
        "/usr/local/bin:/usr/bin:/bin",
        "--setenv",
        "HOME",
        "/tmp",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
    ]
    for directory in ("/usr", "/bin", "/sbin", "/lib", "/lib64"):
        if Path(directory).exists():
            args.extend(["--ro-bind", directory, directory])
    for directory in readonly_roots:
        path = Path(directory).resolve(strict=True)
        if str(path) in {"/", "/home", str(Path.home()), "/etc"} or not path.is_dir():
            raise ValueError("unsafe isolation mount")
        args.extend(["--ro-bind", str(path), str(path)])
    root = str(project.root)
    args.extend(["--bind", root, root])
    git = project.root / ".git"
    if git.exists():
        args.extend(["--ro-bind", str(git), str(git)])
    args.extend(["--chdir", root, "--", *argv])
    return args


def codex_profiles_safe(config_path):
    import tomllib

    config = tomllib.loads(Path(config_path).read_text())
    if config.get("mcp_servers") or config.get("sandbox_workspace_write", {}).get("writable_roots"):
        raise ValueError("dedicated Codex home must not expose MCP servers or extra writable roots")
    values = config.get("profiles", {})
    for name, mode in [
        ("cao-workflows-readonly", "read-only"),
        ("cao-workflows-write", "workspace-write"),
    ]:
        profile = values.get(name, {})
        if profile.get("sandbox_mode") != mode or profile.get("approval_policy") != "never":
            raise ValueError("dedicated Codex sandbox profiles are missing or unsafe")
        if profile.get("mcp_servers") or profile.get("sandbox_workspace_write", {}).get(
            "writable_roots"
        ):
            raise ValueError("unsafe profile MCP server or filesystem extension")
        if profile.get("sandbox_workspace_write", {}).get("network_access", False):
            raise ValueError("agent network access must be disabled")
    return True
