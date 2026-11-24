"""Report secret and private-material locations without printing their contents."""

import argparse
import json
import re
import subprocess
from pathlib import Path

PATTERNS = {
    "openrouter_credential": re.compile(rb"sk-or-v1-[A-Za-z0-9_-]{20,}"),
    "other_credential": re.compile(
        rb"(?:ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|AKIA[A-Z0-9]{16}|sk-proj-[A-Za-z0-9_-]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)"
    ),
    "personal_path": re.compile(
        rb"(?:/Us" + rb'ers/[^/\s"\x27]+/|/ho' + rb'me/[^/\s"\x27]+/|[A-Z]:\\Users\\)'
    ),
    "embedded_dialogue": re.compile(
        rb"(?:<\|im_start\|>|<external_"
        + rb"codex_apps|Companion Page "
        + rb"snapshot|(?m:^)(?:Human|Assistant|User):\s)"
    ),
    "session_checkpoint_metadata": re.compile(
        rb"(?:Agent host " + rb"session|baseline " + rb"checkpoint)"
    ),
}
PRIVATE_SUFFIXES = {".jpg", ".jpeg", ".png", ".xlsx", ".xls", ".pdf", ".docx", ".zip"}
PRIVATE_PARTS = {
    ".git",
    ".aws",
    ".agents",
    ".codex",
    "output",
    "study_audit",
    "private",
    ".venv",
    "__pycache__",
}


def scan_bytes(data):
    return [name for name, pattern in PATTERNS.items() if pattern.search(data)]


def scan_tree(root):
    issues = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path.is_symlink():
            issues.append({"path": relative.as_posix(), "categories": ["symlink"]})
            continue
        if not path.is_file():
            continue
        kinds = scan_bytes(path.read_bytes())
        if (
            path.suffix.lower() in PRIVATE_SUFFIXES
            or any(part in PRIVATE_PARTS for part in relative.parts)
            or path.name == ".env"
            or (path.name.startswith(".env.") and path.name != ".env.example")
        ):
            kinds.append("private_or_generated_file")
        if kinds:
            issues.append({"path": relative.as_posix(), "categories": kinds})
    return issues


def history_report(root):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args])

    refs = git("for-each-ref", "--format=%(refname) %(objectname)").decode().splitlines()
    commits = git("rev-list", "--all").decode().splitlines()
    cache = {}
    issues = []
    messages = []
    for commit in commits:
        kinds = scan_bytes(git("show", "-s", "--format=%B", commit))
        if kinds:
            messages.append({"commit": commit, "categories": kinds})
        for entry in git("ls-tree", "-rz", commit).split(b"\0"):
            if not entry:
                continue
            meta, path = entry.split(b"\t", 1)
            mode, typ, oid = meta.split()
            if typ != b"blob":
                continue
            name = path.decode(errors="replace")
            if oid not in cache:
                cache[oid] = scan_bytes(git("cat-file", "blob", oid.decode()))
            kinds = list(cache[oid])
            parts = Path(name).parts
            if (
                Path(name).suffix.lower() in PRIVATE_SUFFIXES
                or any(p in PRIVATE_PARTS for p in parts)
                or Path(name).name == ".env"
            ):
                kinds.append("private_or_generated_file")
            if kinds:
                issues.append({"commit": commit, "path": name, "categories": kinds})
    return {
        "refs": refs,
        "commits_scanned": len(commits),
        "blobs_scanned": len(cache),
        "file_findings": issues,
        "commit_message_findings": messages,
        "scope": "all refs available locally; remote-only refs and external caches are not inspected",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--history", action="store_true")
    args = parser.parse_args()
    result = history_report(args.root) if args.history else {"file_findings": scan_tree(args.root)}
    print(json.dumps(result, indent=2))
    return int(bool(result.get("file_findings") or result.get("commit_message_findings")))


if __name__ == "__main__":
    raise SystemExit(main())
