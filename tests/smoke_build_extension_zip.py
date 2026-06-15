"""Smoke test for the extension zip builder."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import zipfile


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "addon", "claude_blender"))

import build_extension_zip  # noqa: E402
import build_info  # noqa: E402


EXCLUDED_SUFFIXES = (".pyc", ".pyo", ".blend", ".blend1", ".blend2", ".zip", ".sha256")


def _find_blender():
    candidates = [
        os.environ.get("BLENDER_EXE", ""),
        shutil.which("blender") or "",
        r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 5.0\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.3\blender.exe",
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return ""


def _write_generated_artifacts(source_dir):
    for filename in (
        "generated.zip",
        "generated.zip.sha256",
        "private.blend",
        "private.blend1",
        "private.blend2",
        "bytecode.pyc",
        "optimized.pyo",
        "GENERATED.ZIP",
        "GENERATED.ZIP.SHA256",
        "PRIVATE.BLEND",
        "PRIVATE.BLEND1",
        "PRIVATE.BLEND2",
        "BYTECODE.PYC",
        "OPTIMIZED.PYO",
    ):
        with open(os.path.join(source_dir, filename), "wb") as handle:
            handle.write(b"generated artifact")


def _assert_package_clean(path):
    with zipfile.ZipFile(path, "r") as archive:
        names = set(archive.namelist())
    assert "blender_manifest.toml" in names, sorted(names)[:20]
    assert "__init__.py" in names, sorted(names)[:20]
    assert "build_info.py" in names, sorted(names)[:20]
    assert "LICENSE" in names, sorted(names)[:20]
    assert not any(name.lower().endswith(EXCLUDED_SUFFIXES) for name in names), sorted(names)
    return names


def main():
    source_root = tempfile.mkdtemp(prefix="claude-blender-source-")
    dist_dir = tempfile.mkdtemp(prefix="claude-blender-dist-")
    blender_dist_dir = tempfile.mkdtemp(prefix="claude-blender-blender-dist-")
    try:
        source_dir = os.path.join(source_root, "claude_blender")
        shutil.copytree(build_extension_zip.DEFAULT_SOURCE, source_dir)
        _write_generated_artifacts(source_dir)

        result = build_extension_zip.build_extension(source_dir=source_dir, dist_dir=dist_dir)
        assert result["ok"], result
        assert result["version"] == build_info.ADDON_VERSION, result
        assert os.path.exists(result["path"]), result
        assert os.path.exists(result["sha256_path"]), result
        _assert_package_clean(result["path"])
        with open(result["sha256_path"], "r", encoding="utf-8") as handle:
            digest_line = handle.read().strip()
        assert result["sha256"] in digest_line, digest_line

        blender = _find_blender()
        if blender:
            blender_result = build_extension_zip.build_extension(
                source_dir=source_dir,
                dist_dir=blender_dist_dir,
                blender=blender,
            )
            assert blender_result["ok"], blender_result
            assert blender_result["builder"] == "blender", blender_result
            _assert_package_clean(blender_result["path"])
        else:
            print("smoke_build_extension_zip: blender builder skipped")
        print("smoke_build_extension_zip: ok")
    finally:
        shutil.rmtree(source_root, ignore_errors=True)
        shutil.rmtree(dist_dir, ignore_errors=True)
        shutil.rmtree(blender_dist_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
