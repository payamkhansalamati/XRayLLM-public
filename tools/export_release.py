"""Create a scanned, allowlisted source export without copying Git history."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from audit_release import scan_tree

ROOT = Path(__file__).resolve().parents[1]


def export(destination):
    destination = destination.resolve()
    if destination.exists():
        raise ValueError("Destination already exists; choose a new export directory.")
    paths = []
    for line in (ROOT / "release-files.txt").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        relative = Path(line)
        source = ROOT / relative
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or source.is_symlink()
            or not source.is_file()
        ):
            raise ValueError("Release allowlist contains an invalid or missing file.")
        paths.append(relative)
    destination.mkdir(parents=True)
    hashes = {}
    for relative in paths:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
        hashes[relative.as_posix()] = hashlib.sha256(target.read_bytes()).hexdigest()
    (destination / "RELEASE_SHA256.json").write_text(json.dumps(hashes, indent=2) + "\n")
    findings = scan_tree(destination)
    if findings:
        # The rejected export remains local for inspection; it must not be published.
        raise ValueError(
            "Export scan failed; inspect with tools/audit_release.py before publication."
        )
    if (destination / ".git").exists():
        raise ValueError("Export unexpectedly contains Git metadata.")
    return {"files": len(hashes) + 1, "history_copied": False, "scan": "passed"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(export(args.destination), indent=2))
        return 0
    except (OSError, ValueError) as error:
        print("Export failed: " + str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
