#!/usr/bin/env python3
"""Fail when the Git index contains files unsuitable for the GitHub repository."""

from __future__ import annotations

from collections import Counter
from pathlib import Path, PurePosixPath
import subprocess
import sys


MAX_GIT_BLOB_SIZE = 95 * 1024 * 1024
GENERATED_BINARY_SUFFIXES = {".glb", ".png", ".wav"}
IGNORED_PARTS = {".godot", ".venv", "__pycache__", "dist", "node_modules"}
REQUIRED_FILES = {
    ".gitattributes",
    ".github/workflows/ci.yml",
    ".github/workflows/windows-client.yml",
    ".gitignore",
    ".godot-version",
    "README.md",
    "client/project.godot",
    "docker-compose.yml",
    "server/pyproject.toml",
}


def git(*args: str, input_text: str | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        check=check,
        input=input_text,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def tracked_index() -> dict[str, str]:
    result = git("ls-files", "--stage", "-z")
    entries: dict[str, str] = {}
    for record in result.stdout.split("\0"):
        if not record:
            continue
        metadata, path = record.split("\t", 1)
        _mode, object_id, stage = metadata.split()
        if stage == "0":
            entries[path] = object_id
    return entries


def object_sizes(object_ids: set[str]) -> dict[str, int]:
    if not object_ids:
        return {}
    result = git(
        "cat-file",
        "--batch-check=%(objectname) %(objecttype) %(objectsize)",
        input_text="\n".join(sorted(object_ids)) + "\n",
    )
    sizes: dict[str, int] = {}
    for line in result.stdout.splitlines():
        object_id, object_type, size = line.split()
        if object_type != "blob":
            raise RuntimeError(f"Unexpected Git object type for {object_id}: {object_type}")
        sizes[object_id] = int(size)
    return sizes


def unresolved_conflicts() -> list[str]:
    result = git(
        "grep",
        "--cached",
        "-n",
        "-I",
        "-E",
        r"^(<{7}|={7}|>{7})( |$)",
        check=False,
    )
    if result.returncode not in {0, 1}:
        raise RuntimeError(result.stderr.strip() or "git grep failed")
    return result.stdout.splitlines()


def is_forbidden(path: str) -> bool:
    pure_path = PurePosixPath(path)
    if any(part in IGNORED_PARTS for part in pure_path.parts):
        return True
    if any(part.endswith(".egg-info") for part in pure_path.parts):
        return True
    if pure_path.name == ".env":
        return True
    if pure_path.name.startswith(".env.") and pure_path.name != ".env.example":
        return True
    return pure_path.suffix.lower() in {".pyc", ".pyo"}


def main() -> int:
    try:
        repository_root = Path(git("rev-parse", "--show-toplevel").stdout.strip()).resolve()
    except subprocess.CalledProcessError:
        print("ERROR: Run this check inside an initialized Git repository.", file=sys.stderr)
        return 2

    if Path.cwd().resolve() != repository_root:
        print(f"ERROR: Run this check from the repository root: {repository_root}", file=sys.stderr)
        return 2

    entries = tracked_index()
    errors: list[str] = []
    if not entries:
        errors.append("The Git index is empty. Run 'git add .' before this check.")

    missing = sorted(REQUIRED_FILES - entries.keys())
    if missing:
        errors.append("Required files are not staged/tracked: " + ", ".join(missing))

    forbidden = sorted(path for path in entries if is_forbidden(path))
    if forbidden:
        errors.append("Generated or local files are staged/tracked: " + ", ".join(forbidden))

    conflicts = unresolved_conflicts()
    if conflicts:
        errors.append("Unresolved VCS conflict markers:\n  " + "\n  ".join(conflicts))

    sizes = object_sizes(set(entries.values()))
    oversized = sorted(
        (path, sizes[object_id])
        for path, object_id in entries.items()
        if sizes[object_id] > MAX_GIT_BLOB_SIZE
    )
    for path, size in oversized:
        errors.append(f"Git blob exceeds 95 MiB: {path} ({size / 1024 / 1024:.1f} MiB)")

    generated_binaries = sorted(
        path for path in entries
        if path.startswith("client/assets/")
        and PurePosixPath(path).suffix.lower() in GENERATED_BINARY_SUFFIXES
    )
    if generated_binaries:
        errors.append(
            "Generated runtime binaries must not be tracked; run `make content` after checkout: "
            + ", ".join(generated_binaries[:8])
            + (f" (+{len(generated_binaries) - 8} more)" if len(generated_binaries) > 8 else "")
        )

    if errors:
        print("Repository check failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    suffixes = Counter(PurePosixPath(path).suffix.lower() or "[none]" for path in entries)
    largest_blob = max(sizes.values(), default=0)
    print(
        f"Repository check passed: {len(entries)} tracked files, "
        f"no generated runtime binaries, largest Git blob {largest_blob / 1024:.1f} KiB."
    )
    print("Tracked file groups: " + ", ".join(f"{key}={value}" for key, value in sorted(suffixes.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
