#!/usr/bin/env python3
"""Prepare this repository for a new lib3mf Go SDK release.

This script updates:
- lib3mf.go
- lib3mf_dynamic.c
- lib3mf_dynamic.h
- lib3mf_types.h
- binaries/lib3mf.so
- binaries/lib3mf.dylib
- binaries/lib3mf.dll
- README.md version references

By default it downloads the SDK artifact zip for the given version from:
https://github.com/3MFConsortium/lib3mf/releases

You can override the source with --source for local/offline workflows.
"""

from __future__ import annotations

import argparse
import io
import pathlib
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile


REPO_ROOT = pathlib.Path(__file__).resolve().parent


REQUIRED_FILES = {
    "Bindings/Go/lib3mf.go": REPO_ROOT / "lib3mf.go",
    "Bindings/Go/lib3mf_dynamic.c": REPO_ROOT / "lib3mf_dynamic.c",
    "Bindings/Go/lib3mf_dynamic.h": REPO_ROOT / "lib3mf_dynamic.h",
    "Bindings/Go/lib3mf_types.h": REPO_ROOT / "lib3mf_types.h",
    "Bin/lib3mf.so": REPO_ROOT / "binaries" / "lib3mf.so",
    "Bin/lib3mf.dylib": REPO_ROOT / "binaries" / "lib3mf.dylib",
    "Bin/lib3mf.dll": REPO_ROOT / "binaries" / "lib3mf.dll",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "version",
        help="SDK version (for example: 2.5.0).",
    )
    parser.add_argument(
        "--source",
        help=(
            "Optional override source: unpacked SDK directory, local .zip, or URL to .zip. "
            "If omitted, source is built from --artifact-url-template and version."
        ),
    )
    parser.add_argument(
        "--artifact-url-template",
        default=(
            "https://github.com/3MFConsortium/lib3mf/releases/download/"
            "v{version}/lib3mf_sdk_v{version}.zip"
        ),
        help=(
            "Artifact URL template containing {version}. "
            "Default: GitHub release SDK zip."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned operations without writing files.",
    )
    parser.add_argument(
        "--skip-readme-update",
        action="store_true",
        help="Do not update README.md version strings.",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Create a git commit after updating files.",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Push after commit (requires --commit).",
    )
    return parser.parse_args()


def is_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def find_sdk_root(start: pathlib.Path) -> pathlib.Path:
    start = start.resolve()
    if (start / "Bin").is_dir() and (start / "Bindings" / "Go").is_dir():
        return start

    for candidate in sorted(p for p in start.rglob("*") if p.is_dir()):
        if (candidate / "Bin").is_dir() and (candidate / "Bindings" / "Go").is_dir():
            return candidate

    raise FileNotFoundError(
        f"Could not find SDK root under {start} (expected Bin/ and Bindings/Go/)."
    )


def extract_interface_version(go_wrapper_bytes: bytes) -> str:
    text = go_wrapper_bytes.decode("utf-8", errors="replace")
    match = re.search(r"Interface version:\s*([0-9]+\.[0-9]+\.[0-9]+)", text)
    if not match:
        raise ValueError("Could not parse 'Interface version' from extracted lib3mf.go")
    return match.group(1)


def update_readme_version(readme_path: pathlib.Path, version: str, dry_run: bool) -> None:
    original = readme_path.read_text(encoding="utf-8")
    updated = original
    updated = re.sub(
        r"(Official lib3mf Go Bindings \[)v[0-9]+\.[0-9]+\.[0-9]+(\])",
        rf"\1v{version}\2",
        updated,
    )
    updated = re.sub(
        r"(github\.com/3MFConsortium/lib3mf\.go/v2@)v[0-9]+\.[0-9]+\.[0-9]+",
        rf"\1v{version}",
        updated,
    )

    if updated == original:
        print("README.md version strings already up to date.")
        return

    if dry_run:
        print(f"[dry-run] Would update README.md to v{version}")
    else:
        readme_path.write_text(updated, encoding="utf-8")
        print(f"Updated README.md to v{version}")


def copy_from_directory(sdk_root: pathlib.Path, dry_run: bool) -> bytes:
    go_bytes = b""
    for sdk_rel_path, dst in REQUIRED_FILES.items():
        src = sdk_root / pathlib.Path(sdk_rel_path)
        if not src.exists():
            raise FileNotFoundError(f"Missing required SDK file: {src}")
        if src.name == "lib3mf.go":
            go_bytes = src.read_bytes()
        if dry_run:
            print(f"[dry-run] Would copy {src} -> {dst}")
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            print(f"Copied {src} -> {dst}")
    return go_bytes


def find_zip_member(names: list[str], suffix: str) -> str:
    matches = [name for name in names if name.endswith(suffix)]
    if not matches:
        raise FileNotFoundError(f"Could not find '{suffix}' in zip archive.")
    matches.sort(key=len)
    return matches[0]


def copy_from_zip_bytes(zip_bytes: bytes, dry_run: bool) -> bytes:
    go_bytes = b""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        for sdk_rel_path, dst in REQUIRED_FILES.items():
            member_name = find_zip_member(names, sdk_rel_path)
            data = zf.read(member_name)
            if pathlib.Path(sdk_rel_path).name == "lib3mf.go":
                go_bytes = data
            if dry_run:
                print(f"[dry-run] Would extract {member_name} -> {dst}")
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(data)
                print(f"Extracted {member_name} -> {dst}")
    return go_bytes


def load_zip_bytes(source: str) -> bytes:
    if is_url(source):
        print(f"Downloading SDK zip from {source}")
        with urllib.request.urlopen(source, timeout=30) as response:
            return response.read()
    return pathlib.Path(source).read_bytes()


def maybe_commit_and_push(version: str, do_commit: bool, do_push: bool, dry_run: bool) -> None:
    if not do_commit and not do_push:
        return
    if do_push and not do_commit:
        raise ValueError("--push requires --commit")

    if dry_run:
        print("[dry-run] Would run git add/commit/push")
        return

    commit_message = f"Release version {version}"
    subprocess.run(["git", "add", "."], cwd=REPO_ROOT, check=True)
    subprocess.run(["git", "commit", "-m", commit_message], cwd=REPO_ROOT, check=True)
    print(f"Created commit: {commit_message}")
    if do_push:
        subprocess.run(["git", "push"], cwd=REPO_ROOT, check=True)
        print("Pushed commit.")


def main() -> int:
    args = parse_args()
    source = args.source or args.artifact_url_template.format(version=args.version)
    source_path = pathlib.Path(source)

    if source_path.exists() and source_path.is_dir():
        sdk_root = find_sdk_root(source_path)
        print(f"Using unpacked SDK directory: {sdk_root}")
        go_bytes = copy_from_directory(sdk_root, args.dry_run)
    elif source_path.exists() and source_path.is_file():
        print(f"Using local SDK zip: {source_path}")
        go_bytes = copy_from_zip_bytes(source_path.read_bytes(), args.dry_run)
    elif is_url(source):
        zip_bytes = load_zip_bytes(source)
        go_bytes = copy_from_zip_bytes(zip_bytes, args.dry_run)
    else:
        raise FileNotFoundError(f"Source path does not exist: {source}")

    interface_version = extract_interface_version(go_bytes)
    print(f"Detected interface version: {interface_version}")

    if args.version != interface_version:
        raise ValueError(
            f"--version {args.version} does not match extracted interface version {interface_version}"
        )

    if not args.skip_readme_update:
        update_readme_version(REPO_ROOT / "README.md", interface_version, args.dry_run)

    maybe_commit_and_push(
        interface_version, args.commit, args.push, args.dry_run
    )
    print("Release preparation complete.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
