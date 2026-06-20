"""Release metadata and documentation consistency checks."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tomllib
import urllib.parse
import urllib.request


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon", "claude_blender"))

import build_info  # noqa: E402


MANIFEST_PATH = os.path.join(ROOT, "addon", "claude_blender", "blender_manifest.toml")
CHANGELOG_PATH = os.path.join(ROOT, "CHANGELOG.md")
PAGES_INDEX_URL = "https://callmejones.github.io/blender-agent-bridge/index.json"
LIVE_PAGES_ENV = "BLENDER_AGENT_BRIDGE_LIVE_PAGES_SMOKE"
MAX_LIVE_ARCHIVE_BYTES = 100 * 1024 * 1024


def _read_text(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _read_manifest():
    with open(MANIFEST_PATH, "rb") as handle:
        return tomllib.load(handle)


def _enabled(name):
    return str(os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _download_sha256(url, *, max_bytes=MAX_LIVE_ARCHIVE_BYTES):
    digest = hashlib.sha256()
    total = 0
    with urllib.request.urlopen(url, timeout=30) as response:
        for chunk in iter(lambda: response.read(1024 * 1024), b""):
            total += len(chunk)
            assert total <= max_bytes, f"Live archive exceeds {max_bytes} bytes: {url}"
            digest.update(chunk)
    return digest.hexdigest(), total


def _assert_no_hardcoded_release_examples(version):
    docs = [
        "README.md",
        os.path.join("docs", "EXTERNAL_BRIDGE_MCP.md"),
        os.path.join("docs", "INSTALL_FROM_GITHUB.md"),
        os.path.join("docs", "RELEASE.md"),
        os.path.join("docs", "TESTING_GUIDE.md"),
    ]
    versioned_zip = re.compile(r"claude_blender-\d+\.\d+\.\d+\.zip")
    versioned_tag = re.compile(r"v\d+\.\d+\.\d+")
    offenders = []
    for relative in docs:
        text = _read_text(os.path.join(ROOT, relative))
        for pattern in (versioned_zip, versioned_tag):
            for match in pattern.finditer(text):
                value = match.group(0)
                if version in value:
                    offenders.append(f"{relative}: hard-coded current release example {value!r}; use <version> or generated $Version")
                else:
                    offenders.append(f"{relative}: stale release example {value!r}")
    assert not offenders, "\n".join(offenders)


def _assert_local_release_metadata():
    manifest = _read_manifest()
    version = str(manifest.get("version") or "")
    assert version, manifest
    assert manifest.get("id") == build_info.ADDON_ID, manifest
    assert version == build_info.ADDON_VERSION, (version, build_info.ADDON_VERSION)
    assert tuple(int(part) for part in version.split(".")) == build_info.ADDON_VERSION_TUPLE, build_info.ADDON_VERSION_TUPLE
    assert build_info.MCP_SERVER_VERSION == build_info.ADDON_VERSION, build_info.MCP_SERVER_VERSION

    changelog = _read_text(CHANGELOG_PATH)
    assert "## Unreleased" in changelog, "CHANGELOG.md is missing an Unreleased section"
    assert f"## {version}" in changelog, f"CHANGELOG.md is missing ## {version}"

    _assert_no_hardcoded_release_examples(version)
    return version


def _assert_live_pages_index(version):
    with urllib.request.urlopen(PAGES_INDEX_URL, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    entries = payload.get("data") if isinstance(payload.get("data"), list) else []
    matches = [entry for entry in entries if entry.get("id") == build_info.ADDON_ID]
    assert matches, payload
    entry = matches[0]
    expected_zip = f"{build_info.ADDON_ID}-{version}.zip"
    assert entry.get("version") == version, entry
    archive_url = str(entry.get("archive_url") or "")
    assert archive_url.endswith(expected_zip), entry
    archive_hash = str(entry.get("archive_hash") or "")
    expected_hash = archive_hash.removeprefix("sha256:")
    assert archive_hash.startswith("sha256:") and re.fullmatch(r"[0-9a-fA-F]{64}", expected_hash), entry

    resolved_archive_url = urllib.parse.urljoin(PAGES_INDEX_URL, archive_url)
    actual_hash, actual_size = _download_sha256(resolved_archive_url)
    assert actual_hash == expected_hash.lower(), (resolved_archive_url, actual_hash, archive_hash)
    if entry.get("archive_size") is not None:
        assert int(entry["archive_size"]) == actual_size, (resolved_archive_url, actual_size, entry)


def main():
    version = _assert_local_release_metadata()
    if _enabled(LIVE_PAGES_ENV):
        _assert_live_pages_index(version)
        print(f"smoke_release_consistency: live Pages index and archive verified for {version}")
    else:
        print(f"smoke_release_consistency: local metadata ok for {version}; set {LIVE_PAGES_ENV}=1 for live Pages smoke")


if __name__ == "__main__":
    main()
