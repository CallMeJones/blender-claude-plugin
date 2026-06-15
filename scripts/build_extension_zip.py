"""Build a reproducible Blender extension zip from addon/claude_blender."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_SOURCE = os.path.join(ROOT, "addon", "claude_blender")
DEFAULT_DIST = os.path.join(ROOT, "dist")
DEFAULT_LICENSE = os.path.join(ROOT, "LICENSE")
EXCLUDED_DIRS = {"__pycache__", ".git", ".mypy_cache", ".pytest_cache", ".ruff_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".blend", ".blend1", ".blend2", ".zip", ".sha256"}
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def _read_manifest(source_dir):
    manifest_path = os.path.join(source_dir, "blender_manifest.toml")
    if not os.path.exists(manifest_path):
        raise FileNotFoundError(f"Missing blender_manifest.toml in {source_dir}")
    with open(manifest_path, "rb") as handle:
        manifest = tomllib.load(handle)
    extension_id = str(manifest.get("id") or "").strip()
    version = str(manifest.get("version") or "").strip()
    if not extension_id or not version:
        raise ValueError("blender_manifest.toml must define id and version")
    return manifest, manifest_path


def _iter_files(source_dir):
    for root, dirs, files in os.walk(source_dir):
        dirs[:] = sorted(name for name in dirs if name not in EXCLUDED_DIRS)
        for filename in sorted(files):
            if filename.lower().endswith(tuple(EXCLUDED_SUFFIXES)):
                continue
            path = os.path.join(root, filename)
            relative = os.path.relpath(path, source_dir).replace(os.sep, "/")
            yield path, relative


def _default_extra_files():
    if os.path.exists(DEFAULT_LICENSE):
        return [(DEFAULT_LICENSE, "LICENSE")]
    return []


def _write_reproducible_zip(source_dir, output_path, extra_files=None):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        written = set()
        for path, relative in _iter_files(source_dir):
            with open(path, "rb") as handle:
                data = handle.read()
            info = zipfile.ZipInfo(relative, date_time=ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
            written.add(relative)
        for path, relative in sorted(extra_files or [], key=lambda item: item[1]):
            if relative in written:
                continue
            with open(path, "rb") as handle:
                data = handle.read()
            info = zipfile.ZipInfo(relative, date_time=ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
            written.add(relative)


def _copy_filtered_source(source_dir, destination_dir, extra_files=None):
    copied = set()
    for path, relative in _iter_files(source_dir):
        destination = os.path.join(destination_dir, *relative.split("/"))
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.copy2(path, destination)
        copied.add(relative)
    for path, relative in sorted(extra_files or [], key=lambda item: item[1]):
        if relative in copied:
            continue
        destination = os.path.join(destination_dir, *relative.split("/"))
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.copy2(path, destination)
        copied.add(relative)


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_blender_build(blender, source_dir, output_path):
    command = [
        blender,
        "--command",
        "extension",
        "build",
        "--source-dir",
        source_dir,
        "--output-filepath",
        output_path,
    ]
    subprocess.run(command, check=True)


def build_extension(*, source_dir=DEFAULT_SOURCE, dist_dir=DEFAULT_DIST, output=None, blender=""):
    source_dir = os.path.abspath(source_dir)
    dist_dir = os.path.abspath(dist_dir)
    manifest, _manifest_path = _read_manifest(source_dir)
    output_path = output or os.path.join(dist_dir, f"{manifest['id']}-{manifest['version']}.zip")
    output_path = os.path.abspath(output_path)
    extra_files = _default_extra_files()
    if blender:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="claude-blender-build-") as temp_dir:
            filtered_source = os.path.join(temp_dir, os.path.basename(source_dir.rstrip(os.sep)) or "source")
            os.makedirs(filtered_source, exist_ok=True)
            _copy_filtered_source(source_dir, filtered_source, extra_files=extra_files)
            _run_blender_build(blender, filtered_source, output_path)
    else:
        _write_reproducible_zip(source_dir, output_path, extra_files=extra_files)
    digest = _sha256_file(output_path)
    digest_path = f"{output_path}.sha256"
    with open(digest_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"{digest}  {os.path.basename(output_path)}\n")
    return {
        "ok": True,
        "id": manifest["id"],
        "version": manifest["version"],
        "path": output_path,
        "sha256": digest,
        "sha256_path": digest_path,
        "builder": "blender" if blender else "python-zip",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build the Blender Agent Bridge extension zip")
    parser.add_argument("--source-dir", default=DEFAULT_SOURCE)
    parser.add_argument("--dist-dir", default=DEFAULT_DIST)
    parser.add_argument("--output")
    parser.add_argument("--blender", default="", help="Optional Blender executable for official extension build")
    args = parser.parse_args(argv)
    result = build_extension(
        source_dir=args.source_dir,
        dist_dir=args.dist_dir,
        output=args.output,
        blender=args.blender,
    )
    print(f"Built {result['path']}")
    print(f"SHA-256 {result['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
