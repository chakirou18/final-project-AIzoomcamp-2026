"""Deterministic secret pattern scan over tracked files. No network, no third-party action.

Usage: python scripts/ci/secret_scan.py [paths...]   (defaults to `git ls-files`)
Exit 1 when a credential-shaped string is found outside the documented synthetic placeholders.
"""

import re
import subprocess
import sys
from pathlib import Path

PATTERNS = {
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "github_token": re.compile(
        r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b|github_pat_[A-Za-z0-9_]{20,}"
    ),
    "slack_token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    "openai_style_key": re.compile(r"\bsk-[A-Za-z0-9]{32,}\b"),
    "anthropic_key": re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),
    "basic_auth_url": re.compile(r"[a-z][a-z0-9+.-]*://[^/\s:]+:[^@\s]{6,}@"),
    "assigned_secret": re.compile(
        r"(?i)\b(password|passwd|secret|api[_-]?key|token)\s*[:=]\s*['\"][^'\"\s]{12,}['\"]"
    ),
}
ALLOWED = (
    "synthetic",
    "example",
    "REPLACE_WITH",
    "placeholder",
    "test-only",
    "test_only",
    "invalid",
    "fieldops-t",
    "secret_scan.py",
)
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".pyc", ".dump"}


def tracked_files() -> list[Path]:
    output = subprocess.check_output(["git", "ls-files", "-z"], text=True)
    return [Path(item) for item in output.split("\0") if item]


def findings(paths: list[Path]) -> list[tuple[str, int, str]]:
    found = []
    for path in paths:
        if path.suffix.lower() in SKIP_SUFFIXES or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            for name, pattern in PATTERNS.items():
                if pattern.search(line) and not any(marker in line for marker in ALLOWED):
                    found.append((str(path), number, name))
    return found


def main() -> int:
    paths = [Path(item) for item in sys.argv[1:]] or tracked_files()
    found = findings(paths)
    for path, number, name in found:
        print(f"{path}:{number}: {name}")
    print(f"scanned {len(paths)} files, {len(found)} findings")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
