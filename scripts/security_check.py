from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "env"}
TEXT_EXTENSIONS = {
    ".py",
    ".md",
    ".txt",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
    ".env",
    ".example",
}
SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*['\"][^'\"]{8,}['\"]"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bhf_[A-Za-z0-9]{20,}\b"),
]
FORBIDDEN_FILES = [
    ROOT / ".env",
    ROOT / "database" / "nutriseeker_users.db",
]


def is_text_candidate(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXTENSIONS or path.name.endswith(".env.example")


def iter_files() -> list[Path]:
    paths: list[Path] = []
    for path in ROOT.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file() and is_text_candidate(path):
            paths.append(path)
    return paths


def main() -> int:
    findings: list[str] = []

    for forbidden in FORBIDDEN_FILES:
        if forbidden.exists():
            findings.append(f"Local-sensitive file present: {forbidden.relative_to(ROOT)}")

    for path in iter_files():
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(content):
                findings.append(f"Possible secret in {path.relative_to(ROOT)}")
                break

    if findings:
        print("Security check failed:")
        for item in findings:
            print(f"- {item}")
        return 1

    print("Security check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
