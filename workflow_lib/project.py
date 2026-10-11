import hashlib
import re
import subprocess
from pathlib import Path

SPEC_FILES = ("spec.md", "plan.md", "tasks.md")


class Project:
    def __init__(self, path, feature):
        self.root = Path(path).expanduser().resolve(strict=True)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,100}", feature):
            raise ValueError("feature must be a single safe path component")
        result = subprocess.run(
            ["git", "-C", str(self.root), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
        )
        if result.returncode or Path(result.stdout.strip()).resolve() != self.root:
            raise ValueError("project must be an existing Git root")
        self.feature = feature
        self.spec_dir = self.root / "specs" / feature
        if not self.spec_dir.resolve().is_relative_to(self.root):
            raise ValueError("spec path escapes project")

    def specs(self):
        result = {}
        for name in SPEC_FILES:
            path = self.spec_dir / name
            if not path.is_file() or not path.resolve().is_relative_to(self.root):
                raise ValueError(f"missing or unsafe Spec Kit artifact: {name}")
            result[name] = path.read_text()
            if not result[name].strip():
                raise ValueError("empty spec artifact")
        return result

    def spec_hash(self):
        values = self.specs()
        return hashlib.sha256(
            "".join(name + "\0" + values[name] for name in SPEC_FILES).encode()
        ).hexdigest()

    def skills(self):
        if not (self.root / ".specify").is_dir():
            raise ValueError("Spec Kit not initialized; explicit human initialization required")
        result = {}
        for name in ("specify", "clarify", "plan", "tasks", "analyze"):
            matches = [
                self.root / directory / f"speckit-{name}/SKILL.md"
                for directory in (".agents/skills", ".claude/skills")
            ]
            path = next(
                (p for p in matches if p.is_file() and p.resolve().is_relative_to(self.root)), None
            )
            if path is None:
                raise ValueError(f"missing installed Spec Kit skill: {name}")
            result[name] = str(path)
        return result

    def snapshot(self):
        output = (
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.root),
                    "ls-files",
                    "-z",
                    "--cached",
                    "--others",
                    "--exclude-standard",
                ],
                check=True,
                capture_output=True,
            )
            .stdout.decode()
            .split("\0")
        )
        result = {}
        for relative in sorted(set(output)):
            if not relative or any(
                part in {".cao-runs", ".venv", "__pycache__"} for part in Path(relative).parts
            ):
                continue
            path = self.root / relative
            if path.is_file():
                if not path.resolve().is_relative_to(self.root):
                    raise ValueError("source symlink escapes project")
                result[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        return result
