"""Smoke tests for read-only external asset catalog helpers."""

from __future__ import annotations

import os
import tempfile
import sys
import hashlib
import urllib.parse
import zipfile


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import agent_tools, bridge_protocol, external_assets, mcp_server  # noqa: E402


def _fake_fetch_json(url, *, timeout=15):
    parsed = urllib.parse.urlparse(url)
    path = parsed.path
    query = urllib.parse.parse_qs(parsed.query)
    if path == "/categories/hdris":
        return {"studio": 12, "outdoor": 3}
    if path == "/categories/textures":
        return {"wood": 2}
    if path == "/categories/models":
        return {"vehicles": 1}
    if path == "/assets":
        assert query.get("t") == ["models"], url
        return {
            "small_hangar_01": {
                "name": "Small Hangar 01",
                "categories": ["industrial"],
                "authors": ["Poly Artist"],
            },
            "forest_path": {
                "name": "Forest Path",
                "type": "hdris",
                "categories": ["outdoor"],
            },
        }
    if path == "/files/small_hangar_01":
        return {
            "gltf": {
                "2k": {
                    "gltf": {
                        "url": "https://cdn.example.invalid/small_hangar_01_2k.gltf",
                        "md5": "",
                        "size": 12,
                        "include": {
                            "textures/hangar_diff_2k.jpg": {
                                "url": "https://cdn.example.invalid/hangar_diff_2k.jpg",
                                "md5": "",
                                "size": 5,
                            }
                        },
                    }
                }
            }
        }
    if path == "/files/studio_hdri":
        return {
            "hdri": {
                "1k": {
                    "hdr": {
                        "url": "https://cdn.example.invalid/studio_hdri_1k.hdr",
                        "md5": "",
                        "size": 8,
                    }
                }
            }
        }
    if path == "/files/oak_floor":
        return {
            "diffuse": {
                "2k": {
                    "jpg": {
                        "url": "https://cdn.example.invalid/oak_floor_diff_2k.jpg",
                        "md5": "",
                        "size": 6,
                    }
                }
            },
            "normal": {
                "2k": {
                    "jpg": {
                        "url": "https://cdn.example.invalid/oak_floor_nor_2k.jpg",
                        "md5": "",
                        "size": 6,
                    }
                }
            },
        }
    if path == "/v3/search":
        assert query.get("type") == ["models"], url
        assert query.get("downloadable") == ["true"], url
        return {
            "results": [
                {
                    "uid": "abc123",
                    "name": "Repair Drone",
                    "viewerUrl": "https://sketchfab.com/3d-models/repair-drone-abc123",
                    "isDownloadable": True,
                    "user": {"displayName": "Sketch Artist"},
                    "license": {"label": "CC Attribution"},
                    "thumbnails": {
                        "images": [
                            {"width": 128, "url": "https://example.invalid/small.jpg"},
                            {"width": 512, "url": "https://example.invalid/large.jpg"},
                        ],
                    },
                    "likeCount": 5,
                    "viewCount": 200,
                }
            ]
        }
    raise AssertionError(f"Unexpected URL: {url}")


def _fake_fetch_json_with_headers(url, *, headers=None, timeout=15):
    parsed = urllib.parse.urlparse(url)
    if parsed.path == "/v3/models/abc123/download":
        assert headers and headers.get("Authorization") in {
            "Token test-token",
            "Token bridge-api-token",
        }, headers
        return {"gltf": {"url": "https://download.example.invalid/abc123.zip", "expires": 300}}
    raise AssertionError(f"Unexpected authenticated URL: {url}")


def _fake_download_file(url, destination, *, expected_md5="", expected_size=None, headers=None, timeout=60, progress_callback=None):
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    if progress_callback:
        progress_callback(
            {
                "phase": "download",
                "url": url,
                "path": destination,
                "bytes_downloaded": int(expected_size or 0),
                "expected_size": int(expected_size or 0),
            }
        )
    if str(destination).lower().endswith(".zip"):
        with zipfile.ZipFile(destination, "w") as archive:
            archive.writestr("scene.gltf", "{}")
            archive.writestr("textures/albedo.jpg", "jpg")
    else:
        with open(destination, "wb") as handle:
            handle.write(b"asset-bytes")
    return {
        "ok": True,
        "url": url,
        "path": destination,
        "cached": False,
        "size": os.path.getsize(destination),
        "md5": "",
        "sha256": "test-sha",
    }


def _failing_fetch_json(url, *, timeout=15):
    raise TimeoutError(f"offline: {url}")


class _FakeOfflineApp:
    online_access = False
    online_access_overriden = True


class _FakeOfflineBpy:
    app = _FakeOfflineApp()


class _FakeDownloadResponse:
    def __init__(self, body, status):
        self._body = bytes(body)
        self._offset = 0
        self.status = int(status)

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        return False

    def getcode(self):
        return self.status

    def read(self, size=-1):
        if size is None or size < 0:
            size = len(self._body) - self._offset
        chunk = self._body[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk


def _md5_bytes(value):
    return hashlib.md5(value).hexdigest()


def _write_zip(path, entries):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, body in entries:
            archive.writestr(name, body)


def main():
    original_fetch_json = external_assets._fetch_json
    original_fetch_json_with_headers = external_assets._fetch_json_with_headers
    original_download_file = external_assets._download_file
    original_bpy = external_assets.bpy
    auth_env_names = external_assets.SKETCHFAB_API_TOKEN_ENV_VARS
    original_auth_env = {name: os.environ.get(name) for name in auth_env_names}
    for name in auth_env_names:
        os.environ.pop(name, None)
    external_assets._fetch_json = _fake_fetch_json
    external_assets._fetch_json_with_headers = _fake_fetch_json_with_headers
    external_assets._download_file = _fake_download_file
    cache_dir = tempfile.mkdtemp(prefix="bab-assets-")
    try:
        categories = external_assets.list_poly_haven_categories(asset_type="all")
        assert categories["ok"] is True, categories
        assert categories["provider"] == "poly_haven", categories
        assert [group["asset_type"] for group in categories["groups"]] == ["hdris", "textures", "models"], categories
        assert categories["groups"][0]["categories"][0]["slug"] == "outdoor", categories

        poly = external_assets.search_poly_haven_assets(query="hangar", asset_type="models", limit=5)
        assert poly["ok"] is True, poly
        assert poly["count"] == 1, poly
        assert poly["assets"][0]["id"] == "small_hangar_01", poly
        assert poly["assets"][0]["asset_type"] == "models", poly
        assert poly["assets"][0]["authors"] == ["Poly Artist"], poly
        assert poly["assets"][0]["license"] == "CC0", poly
        assert poly["assets"][0]["page_url"].endswith("/a/small_hangar_01"), poly
        assert poly["assets"][0]["api_files_url"].endswith("/files/small_hangar_01"), poly
        assert poly["download_import_status"] == "download_or_import_tools_available", poly

        file_tree = external_assets.inspect_poly_haven_asset_files(asset_id="small_hangar_01")
        assert file_tree["ok"] is True, file_tree
        assert file_tree["asset_type"] == "models", file_tree
        assert file_tree["file_count"] == 1, file_tree
        assert file_tree["files"][0]["logical_path"] == "gltf/2k/gltf", file_tree

        model_cache = external_assets.download_poly_haven_asset(
            asset_id="small_hangar_01",
            asset_type="models",
            resolution="2k",
            cache_dir=cache_dir,
        )
        assert model_cache["ok"] is True, model_cache
        assert model_cache["asset_type"] == "models", model_cache
        assert len(model_cache["downloaded_files"]) == 2, model_cache
        assert any(item.get("dependency") for item in model_cache["downloaded_files"]), model_cache
        assert os.path.exists(model_cache["manifest_path"]), model_cache

        hdri_cache = external_assets.download_poly_haven_asset(
            asset_id="studio_hdri",
            asset_type="hdris",
            resolution="1k",
            cache_dir=cache_dir,
        )
        assert hdri_cache["ok"] is True, hdri_cache
        assert hdri_cache["asset_type"] == "hdris", hdri_cache

        texture_cache = external_assets.download_poly_haven_asset(
            asset_id="oak_floor",
            asset_type="textures",
            resolution="2k",
            cache_dir=cache_dir,
        )
        assert texture_cache["ok"] is True, texture_cache
        assert len(texture_cache["downloaded_files"]) == 2, texture_cache

        sketchfab_missing = external_assets.search_sketchfab_models(query="")
        assert sketchfab_missing["ok"] is False, sketchfab_missing

        sketchfab = external_assets.search_sketchfab_models(query="repair drone", limit=3)
        assert sketchfab["ok"] is True, sketchfab
        assert sketchfab["provider"] == "sketchfab", sketchfab
        assert sketchfab["count"] == 1, sketchfab
        assert sketchfab["models"][0]["uid"] == "abc123", sketchfab
        assert sketchfab["models"][0]["is_downloadable"] is True, sketchfab
        assert sketchfab["models"][0]["thumbnail_url"].endswith("/large.jpg"), sketchfab
        assert sketchfab["download_import_status"] == "download_or_import_requires_auth", sketchfab

        no_token = external_assets.download_sketchfab_model(uid="abc123", cache_dir=cache_dir)
        assert no_token["ok"] is False, no_token
        assert no_token["auth_required"] is True, no_token
        assert no_token["auth_method"] == "api_token", no_token
        assert "SKETCHFAB_API_TOKEN" in no_token["allowed_api_token_env_vars"], no_token
        blocked_env = external_assets.download_sketchfab_model(
            uid="abc123",
            token_env_var="BLENDER_BRIDGE_TOKEN",
            cache_dir=cache_dir,
        )
        assert blocked_env["ok"] is False, blocked_env
        assert blocked_env["blocked_token_env_var"] == "BLENDER_BRIDGE_TOKEN", blocked_env
        assert "SKETCHFAB_API_TOKEN" in blocked_env["allowed_token_env_vars"], blocked_env

        os.environ[external_assets.SKETCHFAB_BRIDGE_TOKEN_ENV_VAR] = "bridge-api-token"
        injected = external_assets.sketchfab_auth_arguments_from_env({"uid": "abc123"})
        assert injected["api_token"] == "bridge-api-token", injected
        server = mcp_server.BlenderMCPServer(None)
        forwarded = server._bridge_tool_arguments("download_sketchfab_model", {"uid": "abc123"})
        assert forwarded["api_token"] == "bridge-api-token", forwarded
        sketchfab_env_api_cache = external_assets.download_sketchfab_model(uid="abc123", cache_dir=cache_dir)
        assert sketchfab_env_api_cache["ok"] is True, sketchfab_env_api_cache
        assert sketchfab_env_api_cache["auth_method"] == "api_token", sketchfab_env_api_cache
        assert sketchfab_env_api_cache["auth_source"] == f"env:{external_assets.SKETCHFAB_BRIDGE_TOKEN_ENV_VAR}", sketchfab_env_api_cache
        os.environ.pop(external_assets.SKETCHFAB_BRIDGE_TOKEN_ENV_VAR, None)

        sketchfab_cache = external_assets.download_sketchfab_model(
            uid="abc123",
            api_token="test-token",
            cache_dir=cache_dir,
        )
        assert sketchfab_cache["ok"] is True, sketchfab_cache
        assert sketchfab_cache["auth_source"] == "argument", sketchfab_cache
        assert sketchfab_cache["import_file"].endswith("scene.gltf"), sketchfab_cache
        assert os.path.exists(sketchfab_cache["import_file"]), sketchfab_cache

        diagnostics = external_assets.external_asset_cache_diagnostics(cache_dir=cache_dir)
        assert diagnostics["ok"] is True, diagnostics
        assert diagnostics["auth"]["sketchfab"]["auth_method"] == "api_token", diagnostics
        assert diagnostics["asset_count"] >= 4, diagnostics
        assert diagnostics["provider_counts"]["poly_haven"] >= 3, diagnostics
        assert diagnostics["provider_counts"]["sketchfab"] >= 1, diagnostics

        prune_dry_run = external_assets.prune_external_asset_cache(
            cache_dir=cache_dir,
            max_total_bytes=1,
            dry_run=True,
            include_imported=True,
        )
        assert prune_dry_run["ok"] is True, prune_dry_run
        assert prune_dry_run["dry_run"] is True, prune_dry_run
        assert prune_dry_run["candidate_count"] >= 1, prune_dry_run
        assert prune_dry_run["deleted_count"] == 0, prune_dry_run

        prune_actual = external_assets.prune_external_asset_cache(
            cache_dir=cache_dir,
            max_total_bytes=1,
            dry_run=False,
            include_imported=True,
        )
        assert prune_actual["ok"] is True, prune_actual
        assert prune_actual["dry_run"] is False, prune_actual
        assert prune_actual["deleted_count"] >= 1, prune_actual

        external_assets._download_file = original_download_file
        external_assets.bpy = _FakeOfflineBpy()
        offline_download = external_assets._download_file(
            "https://download.example.invalid/blocked.bin",
            os.path.join(cache_dir, "blocked.bin"),
        )
        assert offline_download["ok"] is False, offline_download
        assert offline_download["error_type"] == "online_access_disabled", offline_download
        assert offline_download["online_access_overridden"] is True, offline_download
        external_assets.bpy = original_bpy

        original_urlopen = external_assets.urllib.request.urlopen
        original_backoff = external_assets.DOWNLOAD_RETRY_BACKOFF_SECONDS
        try:
            external_assets.DOWNLOAD_RETRY_BACKOFF_SECONDS = 0
            resume_ranges = []

            def _resume_urlopen(request, *, timeout=60):
                resume_ranges.append(dict(request.header_items()).get("Range", ""))
                return _FakeDownloadResponse(b"world", 206)

            external_assets.urllib.request.urlopen = _resume_urlopen
            resume_path = os.path.join(cache_dir, "resume.bin")
            with open(f"{resume_path}.part", "wb") as handle:
                handle.write(b"hello ")
            resumed = external_assets._download_file(
                "https://download.example.invalid/resume.bin",
                resume_path,
                expected_md5=_md5_bytes(b"hello world"),
                expected_size=len(b"hello world"),
            )
            assert resumed["ok"] is True, resumed
            assert resumed["resumed"] is True, resumed
            assert resumed["attempts"] == 1, resumed
            assert resume_ranges == ["bytes=6-"], resume_ranges
            with open(resume_path, "rb") as handle:
                assert handle.read() == b"hello world", resumed

            restart_ranges = []

            def _restart_urlopen(request, *, timeout=60):
                restart_ranges.append(dict(request.header_items()).get("Range", ""))
                return _FakeDownloadResponse(b"fresh", 200)

            external_assets.urllib.request.urlopen = _restart_urlopen
            restart_path = os.path.join(cache_dir, "restart.bin")
            with open(f"{restart_path}.part", "wb") as handle:
                handle.write(b"stale")
            restarted = external_assets._download_file(
                "https://download.example.invalid/restart.bin",
                restart_path,
                expected_md5=_md5_bytes(b"fresh"),
                expected_size=len(b"fresh"),
            )
            assert restarted["ok"] is True, restarted
            assert restarted["resumed"] is False, restarted
            assert restart_ranges == ["bytes=5-"], restart_ranges
            with open(restart_path, "rb") as handle:
                assert handle.read() == b"fresh", restarted

            retry_calls = []

            def _retry_urlopen(request, *, timeout=60):
                retry_calls.append(dict(request.header_items()).get("Range", ""))
                if len(retry_calls) == 1:
                    raise TimeoutError("temporary smoke timeout")
                return _FakeDownloadResponse(b"retry", 200)

            external_assets.urllib.request.urlopen = _retry_urlopen
            retry_path = os.path.join(cache_dir, "retry.bin")
            retried = external_assets._download_file(
                "https://download.example.invalid/retry.bin",
                retry_path,
                expected_md5=_md5_bytes(b"retry"),
                expected_size=len(b"retry"),
            )
            assert retried["ok"] is True, retried
            assert retried["attempts"] == 2, retried
            assert retry_calls == ["", ""], retry_calls
        finally:
            external_assets.urllib.request.urlopen = original_urlopen
            external_assets.DOWNLOAD_RETRY_BACKOFF_SECONDS = original_backoff
            external_assets._download_file = _fake_download_file

        unsafe_zip = os.path.join(cache_dir, "unsafe.zip")
        _write_zip(unsafe_zip, [("../evil.gltf", "{}")])
        unsafe_extract = external_assets._safe_extract_zip(unsafe_zip, os.path.join(cache_dir, "unsafe-out"))
        assert unsafe_extract["ok"] is False, unsafe_extract
        assert "Unsafe archive member path" in unsafe_extract["message"], unsafe_extract

        original_zip_limits = {
            "MAX_ZIP_MEMBER_COUNT": external_assets.MAX_ZIP_MEMBER_COUNT,
            "MAX_ZIP_EXTRACTED_BYTES": external_assets.MAX_ZIP_EXTRACTED_BYTES,
            "MAX_ZIP_MEMBER_BYTES": external_assets.MAX_ZIP_MEMBER_BYTES,
            "MAX_ZIP_PATH_DEPTH": external_assets.MAX_ZIP_PATH_DEPTH,
            "MAX_ZIP_COMPRESSION_RATIO": external_assets.MAX_ZIP_COMPRESSION_RATIO,
            "MIN_ZIP_RATIO_CHECK_BYTES": external_assets.MIN_ZIP_RATIO_CHECK_BYTES,
        }
        try:
            member_count_zip = os.path.join(cache_dir, "too-many.zip")
            _write_zip(member_count_zip, [("a.txt", "a"), ("b.txt", "b")])
            external_assets.MAX_ZIP_MEMBER_COUNT = 1
            too_many = external_assets._safe_extract_zip(member_count_zip, os.path.join(cache_dir, "too-many-out"))
            assert too_many["ok"] is False, too_many
            assert too_many["member_count"] == 2, too_many

            total_size_zip = os.path.join(cache_dir, "too-large-total.zip")
            _write_zip(total_size_zip, [("scene.gltf", "12345")])
            external_assets.MAX_ZIP_MEMBER_COUNT = original_zip_limits["MAX_ZIP_MEMBER_COUNT"]
            external_assets.MAX_ZIP_EXTRACTED_BYTES = 4
            too_large_total = external_assets._safe_extract_zip(total_size_zip, os.path.join(cache_dir, "too-large-total-out"))
            assert too_large_total["ok"] is False, too_large_total
            assert too_large_total["total_uncompressed_size"] == 5, too_large_total

            deep_zip = os.path.join(cache_dir, "too-deep.zip")
            _write_zip(deep_zip, [("a/b/scene.gltf", "{}")])
            external_assets.MAX_ZIP_EXTRACTED_BYTES = original_zip_limits["MAX_ZIP_EXTRACTED_BYTES"]
            external_assets.MAX_ZIP_PATH_DEPTH = 2
            too_deep = external_assets._safe_extract_zip(deep_zip, os.path.join(cache_dir, "too-deep-out"))
            assert too_deep["ok"] is False, too_deep
            assert "too deep" in too_deep["message"], too_deep

            ratio_zip = os.path.join(cache_dir, "too-compressed.zip")
            _write_zip(ratio_zip, [("scene.gltf", "0" * 200)])
            external_assets.MAX_ZIP_PATH_DEPTH = original_zip_limits["MAX_ZIP_PATH_DEPTH"]
            external_assets.MIN_ZIP_RATIO_CHECK_BYTES = 1
            external_assets.MAX_ZIP_COMPRESSION_RATIO = 2
            too_compressed = external_assets._safe_extract_zip(ratio_zip, os.path.join(cache_dir, "too-compressed-out"))
            assert too_compressed["ok"] is False, too_compressed
            assert "compression ratio" in too_compressed["message"], too_compressed
        finally:
            for key, value in original_zip_limits.items():
                setattr(external_assets, key, value)

        tool_names = {tool["name"] for tool in agent_tools.blender_tool_definitions()}
        for name in (
            "list_poly_haven_categories",
            "search_poly_haven_assets",
            "inspect_poly_haven_asset_files",
            "download_poly_haven_asset",
            "import_poly_haven_asset",
            "search_sketchfab_models",
            "download_sketchfab_model",
            "import_sketchfab_model",
            "start_external_asset_download",
            "get_external_asset_job_status",
            "cancel_external_asset_job",
            "import_external_asset_job_result",
            "start_external_asset_import_job",
            "get_external_asset_import_job_status",
            "cancel_external_asset_import_job",
            "delete_external_asset_job",
            "get_external_asset_cache_diagnostics",
            "prune_external_asset_cache",
        ):
            assert name in tool_names, name
            assert name in bridge_protocol.TOOL_CONTRACTS, name
            annotations = bridge_protocol.mcp_annotations_for_tool(name)
            if name in {
                "list_poly_haven_categories",
                "search_poly_haven_assets",
                "inspect_poly_haven_asset_files",
                "download_poly_haven_asset",
                "import_poly_haven_asset",
                "search_sketchfab_models",
                "download_sketchfab_model",
                "import_sketchfab_model",
                "start_external_asset_download",
            }:
                assert "network" in annotations["permissions"], annotations
                assert annotations["openWorldHint"] is True, annotations
            if name in {"import_poly_haven_asset", "import_sketchfab_model", "import_external_asset_job_result", "start_external_asset_import_job"}:
                assert annotations["mutatesScene"] is True, annotations
                assert annotations["requiresLivePreview"] is True, annotations
            elif name in {"download_poly_haven_asset", "download_sketchfab_model", "start_external_asset_download", "cancel_external_asset_job", "cancel_external_asset_import_job", "delete_external_asset_job", "prune_external_asset_cache"}:
                assert annotations["mutatesScene"] is False, annotations
                assert annotations["hasSideEffects"] is True, annotations
            else:
                assert annotations["mutatesScene"] is False, annotations
                assert annotations["readOnlyHint"] is True, annotations
            assert mcp_server._tool_category({"name": name}) == "external_assets", name

        selected, metadata = agent_tools.select_blender_tool_definitions("find a Poly Haven studio hdri")
        selected_names = {tool["name"] for tool in selected}
        assert "search_poly_haven_assets" in selected_names, metadata
        assert "list_poly_haven_categories" in selected_names, metadata
        assert "external_assets" in metadata["matched_groups"], metadata

        external_assets._fetch_json = _failing_fetch_json
        failed_categories = external_assets.list_poly_haven_categories(asset_type="hdris")
        assert failed_categories["ok"] is False, failed_categories
        assert failed_categories["provider"] == "poly_haven", failed_categories
        assert failed_categories["failed_asset_type"] == "hdris", failed_categories
        assert failed_categories["groups"] == [], failed_categories
        assert failed_categories["error_type"] == "TimeoutError", failed_categories

        failed_poly = external_assets.search_poly_haven_assets(query="hangar", asset_type="models")
        assert failed_poly["ok"] is False, failed_poly
        assert failed_poly["assets"] == [], failed_poly
        assert failed_poly["count"] == 0, failed_poly
        assert failed_poly["download_import_status"] == "not_attempted", failed_poly

        failed_sketchfab = external_assets.search_sketchfab_models(query="repair drone")
        assert failed_sketchfab["ok"] is False, failed_sketchfab
        assert failed_sketchfab["models"] == [], failed_sketchfab
        assert failed_sketchfab["count"] == 0, failed_sketchfab
        assert failed_sketchfab["download_import_status"] == "not_attempted", failed_sketchfab
    finally:
        external_assets._fetch_json = original_fetch_json
        external_assets._fetch_json_with_headers = original_fetch_json_with_headers
        external_assets._download_file = original_download_file
        external_assets.bpy = original_bpy
        for name, value in original_auth_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


if __name__ == "__main__":
    main()
