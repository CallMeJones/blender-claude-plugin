"""External asset catalog, cache, and preview import helpers."""

from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import time
import urllib.parse
import urllib.request
import zipfile

try:
    import bpy
except ImportError:  # Allows pure-Python smoke tests outside Blender.
    bpy = None

try:
    from . import live_preview
except ImportError:
    live_preview = None

try:
    from . import user_paths
except ImportError:
    user_paths = None


POLY_HAVEN_BASE_URL = "https://api.polyhaven.com"
POLY_HAVEN_SITE_URL = "https://polyhaven.com"
SKETCHFAB_BASE_URL = "https://api.sketchfab.com/v3"
USER_AGENT = "BlenderAgentBridge/0.1 (+https://github.com/CallMeJones/blender-agent-bridge)"
POLY_HAVEN_LICENSE = "CC0"
SKETCHFAB_TOKEN_ENV_VAR = "SKETCHFAB_API_TOKEN"
SKETCHFAB_BRIDGE_TOKEN_ENV_VAR = "BLENDER_AGENT_BRIDGE_SKETCHFAB_API_TOKEN"
SKETCHFAB_API_TOKEN_ENV_VARS = (SKETCHFAB_TOKEN_ENV_VAR, SKETCHFAB_BRIDGE_TOKEN_ENV_VAR)
SKETCHFAB_ALLOWED_TOKEN_ENV_VARS = frozenset(SKETCHFAB_API_TOKEN_ENV_VARS)


def _bounded_limit(value, default=20, *, maximum=50):
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = int(default)
    return max(1, min(int(maximum), result))


def _auth_env_candidates(preferred, *, defaults, allowed):
    preferred = str(preferred or "").strip()
    if preferred:
        if preferred not in allowed:
            return [], preferred
        candidates = [preferred]
        if preferred == defaults[0]:
            candidates.extend(name for name in defaults[1:] if name not in candidates)
        return candidates, ""
    return list(defaults), ""


def _first_env_token(preferred, *, defaults, allowed, environ=None):
    candidates, blocked = _auth_env_candidates(preferred, defaults=defaults, allowed=allowed)
    if blocked:
        return "", "", blocked, candidates
    source = environ if environ is not None else os.environ
    for name in candidates:
        value = str(source.get(name, "") or "").strip()
        if value:
            return value, name, "", candidates
    return "", "", "", candidates


def _present_auth_env_names(environ=None):
    source = environ if environ is not None else os.environ
    return [
        name
        for name in SKETCHFAB_API_TOKEN_ENV_VARS
        if str(source.get(name, "") or "").strip()
    ]


def sketchfab_auth_diagnostics(environ=None):
    """Report Sketchfab auth availability without exposing credential values."""

    configured = _present_auth_env_names(environ=environ)
    api_token_configured = any(name in configured for name in SKETCHFAB_API_TOKEN_ENV_VARS)
    return {
        "provider": "sketchfab",
        "auth_method": "api_token",
        "ready": bool(api_token_configured),
        "api_token_configured": bool(api_token_configured),
        "configured_env_vars": configured,
        "api_token_env_vars": list(SKETCHFAB_API_TOKEN_ENV_VARS),
        "message": (
            "Sketchfab API token is configured."
            if api_token_configured
            else "No Sketchfab API token env var is configured."
        ),
    }


def sketchfab_auth_arguments_from_env(arguments, *, environ=None):
    """Copy arguments and inject MCP-process env credentials for bridge calls."""

    result = dict(arguments or {})
    if str(result.get("api_token") or "").strip():
        return result
    api_token, _api_env, blocked, _candidates = _first_env_token(
        result.get("token_env_var") or SKETCHFAB_TOKEN_ENV_VAR,
        defaults=SKETCHFAB_API_TOKEN_ENV_VARS,
        allowed=SKETCHFAB_ALLOWED_TOKEN_ENV_VARS,
        environ=environ,
    )
    if blocked:
        return result
    if api_token:
        result["api_token"] = api_token
    return result


def _default_cache_dir():
    if user_paths is not None:
        return user_paths.user_data_path("assets")
    return os.path.join(os.path.expanduser("~"), ".claude_blender", "assets")


def _online_access_error(provider="external asset"):
    if bpy is None or bool(getattr(bpy.app, "online_access", True)):
        return None
    overridden = bool(getattr(bpy.app, "online_access_overriden", False))
    if overridden:
        message = f"{provider} download requires online access, but Blender was started in offline mode."
    else:
        message = f"{provider} download requires online access; enable Allow Online Access in Blender preferences."
    return {
        "ok": False,
        "message": message,
        "error_type": "online_access_disabled",
        "online_access": False,
        "online_access_overridden": overridden,
    }


def _fetch_json(url, *, timeout=15):
    offline_error = _online_access_error("External asset metadata")
    if offline_error:
        raise RuntimeError(offline_error["message"])
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=max(1, int(timeout or 15))) as response:
        data = response.read()
    return json.loads(data.decode("utf-8"))


def _fetch_json_with_headers(url, *, headers=None, timeout=15):
    offline_error = _online_access_error("External asset metadata")
    if offline_error:
        raise RuntimeError(offline_error["message"])
    merged = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    merged.update(headers or {})
    request = urllib.request.Request(url, headers=merged)
    with urllib.request.urlopen(request, timeout=max(1, int(timeout or 15))) as response:
        data = response.read()
    return json.loads(data.decode("utf-8"))


def _fetch_json_result(provider, url, *, timeout=15):
    try:
        return _fetch_json(url, timeout=timeout), None
    except Exception as exc:
        return None, {
            "ok": False,
            "message": f"{provider} request failed: {type(exc).__name__}: {exc}",
            "provider": provider,
            "source_url": url,
            "error_type": type(exc).__name__,
        }


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sanitize_slug(value, fallback="asset"):
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip()).strip("._-")
    return text[:120] or fallback


def _cache_root(cache_dir=""):
    root = os.path.abspath(os.path.expanduser(str(cache_dir or _default_cache_dir())))
    os.makedirs(root, exist_ok=True)
    return root


def _asset_cache_dir(provider, asset_id, cache_dir=""):
    root = _cache_root(cache_dir)
    directory = os.path.join(root, _sanitize_slug(provider, "provider"), _sanitize_slug(asset_id))
    os.makedirs(directory, exist_ok=True)
    return directory


def _manifest_path(asset_dir):
    return os.path.join(asset_dir, "asset_manifest.json")


def _write_manifest(asset_dir, manifest):
    manifest = dict(manifest)
    manifest.setdefault("created_at", _now())
    manifest["updated_at"] = _now()
    manifest["cache_dir"] = asset_dir
    path = _manifest_path(asset_dir)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")
    manifest["manifest_path"] = path
    return manifest


def _read_manifest(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        data["manifest_path"] = path
        return data
    except Exception as exc:
        return {"ok": False, "manifest_path": path, "message": f"Manifest read failed: {type(exc).__name__}: {exc}"}


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _md5_file(path):
    digest = hashlib.md5()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _filename_from_url(url, fallback):
    parsed = urllib.parse.urlparse(str(url or ""))
    name = os.path.basename(parsed.path)
    return _sanitize_slug(urllib.parse.unquote(name), fallback=fallback)


def _download_file(url, destination, *, expected_md5="", expected_size=None, headers=None, timeout=60):
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    cached = os.path.exists(destination)
    if cached and expected_size and os.path.getsize(destination) != int(expected_size):
        cached = False
    if cached and expected_md5 and _md5_file(destination).lower() != str(expected_md5).lower():
        cached = False
    if not cached:
        offline_error = _online_access_error("External asset file")
        if offline_error:
            offline_error["url"] = str(url)
            offline_error["path"] = destination
            return offline_error
        request = urllib.request.Request(str(url), headers={"User-Agent": USER_AGENT, **(headers or {})})
        with urllib.request.urlopen(request, timeout=max(1, int(timeout or 60))) as response:
            with open(destination, "wb") as handle:
                shutil.copyfileobj(response, handle)
    size = os.path.getsize(destination)
    md5 = _md5_file(destination) if os.path.exists(destination) else ""
    if expected_size and size != int(expected_size):
        return {
            "ok": False,
            "message": f"Downloaded size mismatch for {destination}",
            "path": destination,
            "expected_size": int(expected_size),
            "size": size,
        }
    if expected_md5 and md5.lower() != str(expected_md5).lower():
        return {
            "ok": False,
            "message": f"Downloaded MD5 mismatch for {destination}",
            "path": destination,
            "expected_md5": str(expected_md5),
            "md5": md5,
        }
    return {
        "ok": True,
        "url": str(url),
        "path": destination,
        "cached": cached,
        "size": size,
        "md5": md5,
        "sha256": _sha256_file(destination),
    }


def _poly_haven_type(asset_type):
    value = str(asset_type or "all").strip().lower()
    aliases = {
        "all": "all",
        "hdri": "hdris",
        "hdris": "hdris",
        "texture": "textures",
        "textures": "textures",
        "model": "models",
        "models": "models",
    }
    return aliases.get(value, "all")


def _poly_haven_category_items(payload):
    if isinstance(payload, dict):
        return [
            {
                "slug": str(key),
                "name": str(key).replace("_", " ").title(),
                "count": int(value or 0) if isinstance(value, int) else None,
            }
            for key, value in sorted(payload.items())
        ]
    if isinstance(payload, list):
        items = []
        for item in payload:
            if isinstance(item, dict):
                slug = str(item.get("slug") or item.get("name") or "")
                items.append({"slug": slug, "name": str(item.get("name") or slug), "count": item.get("count")})
            else:
                slug = str(item)
                items.append({"slug": slug, "name": slug.replace("_", " ").title(), "count": None})
        return items
    return []


def _string_list(value):
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def list_poly_haven_categories(*, asset_type="all", timeout=15):
    asset_type = _poly_haven_type(asset_type)
    asset_types = ["hdris", "textures", "models"] if asset_type == "all" else [asset_type]
    groups = []
    for current_type in asset_types:
        url = f"{POLY_HAVEN_BASE_URL}/categories/{urllib.parse.quote(current_type)}"
        payload, error = _fetch_json_result("poly_haven", url, timeout=timeout)
        if error:
            error["groups"] = groups
            error["failed_asset_type"] = current_type
            return error
        groups.append({"asset_type": current_type, "categories": _poly_haven_category_items(payload)})
    return {
        "ok": True,
        "message": "Poly Haven categories fetched",
        "provider": "poly_haven",
        "source_url": POLY_HAVEN_BASE_URL,
        "groups": groups,
    }


def _poly_haven_assets(payload):
    if isinstance(payload, dict):
        iterable = payload.items()
    elif isinstance(payload, list):
        iterable = (
            ((item.get("id") or item.get("slug") or item.get("name") or ""), item)
            for item in payload
            if isinstance(item, dict)
        )
    else:
        iterable = []
    assets = []
    for asset_id, item in iterable:
        info = item if isinstance(item, dict) else {}
        asset_id = str(asset_id or info.get("id") or info.get("slug") or "").strip()
        if not asset_id:
            continue
        title = str(info.get("name") or info.get("title") or asset_id).strip()
        asset_type = _poly_haven_type(info.get("type") or info.get("asset_type") or "")
        categories = info.get("categories") if isinstance(info.get("categories"), list) else []
        assets.append(
            {
                "id": asset_id,
                "name": title,
                "asset_type": "" if asset_type == "all" else asset_type,
                "categories": [str(item) for item in categories],
                "authors": _string_list(info.get("authors") or info.get("author")),
                "license": info.get("license") or "CC0",
                "page_url": f"{POLY_HAVEN_SITE_URL}/a/{urllib.parse.quote(asset_id)}",
                "api_files_url": f"{POLY_HAVEN_BASE_URL}/files/{urllib.parse.quote(asset_id)}",
                "thumbnail_url": info.get("thumbnail_url") or info.get("thumb") or "",
            }
        )
    return assets


def search_poly_haven_assets(*, query="", asset_type="all", category="", limit=20, timeout=15):
    asset_type = _poly_haven_type(asset_type)
    params = {}
    if asset_type != "all":
        params["t"] = asset_type
    category = str(category or "").strip()
    if category and category.lower() != "all":
        params["c"] = category
    url = f"{POLY_HAVEN_BASE_URL}/assets"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    payload, error = _fetch_json_result("poly_haven", url, timeout=timeout)
    if error:
        error.update(
            {
                "query": query,
                "asset_type": asset_type,
                "category": category,
                "assets": [],
                "count": 0,
                "download_import_status": "not_attempted",
            }
        )
        return error
    assets = _poly_haven_assets(payload)
    if asset_type != "all":
        for asset in assets:
            if not asset.get("asset_type"):
                asset["asset_type"] = asset_type
    query_text = str(query or "").strip().lower()
    if query_text:
        assets = [
            asset
            for asset in assets
            if query_text in " ".join([asset["id"], asset["name"], " ".join(asset["categories"])]).lower()
        ]
    limit = _bounded_limit(limit)
    return {
        "ok": True,
        "message": "Poly Haven assets searched",
        "provider": "poly_haven",
        "source_url": url,
        "query": query,
        "asset_type": asset_type,
        "category": category,
        "count": min(len(assets), limit),
        "total_considered": len(assets),
        "assets": assets[:limit],
        "download_import_status": "download_or_import_tools_available",
    }


def _poly_haven_files_url(asset_id):
    return f"{POLY_HAVEN_BASE_URL}/files/{urllib.parse.quote(str(asset_id or '').strip())}"


def _flatten_poly_haven_files(payload, prefix=()):
    entries = []
    if not isinstance(payload, dict):
        return entries
    if isinstance(payload.get("url"), str):
        include = payload.get("include") if isinstance(payload.get("include"), dict) else {}
        entries.append(
            {
                "logical_path": "/".join(str(item) for item in prefix),
                "path_parts": [str(item) for item in prefix],
                "url": str(payload.get("url") or ""),
                "md5": str(payload.get("md5") or ""),
                "size": int(payload.get("size") or 0),
                "include": include,
            }
        )
        return entries
    for key, value in payload.items():
        if key == "include":
            continue
        if value is None:
            continue
        entries.extend(_flatten_poly_haven_files(value, (*prefix, key)))
    return entries


def _infer_poly_haven_asset_type(payload):
    keys = set(payload.keys()) if isinstance(payload, dict) else set()
    if "hdri" in keys:
        return "hdris"
    texture_roots = {
        "ao",
        "arm",
        "bump",
        "diff",
        "diffuse",
        "disp",
        "displacement",
        "metal",
        "metallic",
        "nor",
        "normal",
        "rough",
        "roughness",
    }
    if texture_roots & keys or "mtlx" in keys:
        return "textures"
    if {"blend", "gltf", "fbx", "usd"} & keys:
        return "models"
    return ""


def inspect_poly_haven_asset_files(*, asset_id, timeout=15):
    asset_id = str(asset_id or "").strip()
    if not asset_id:
        return {"ok": False, "message": "asset_id is required"}
    url = _poly_haven_files_url(asset_id)
    payload, error = _fetch_json_result("poly_haven", url, timeout=timeout)
    if error:
        error["asset_id"] = asset_id
        return error
    entries = _flatten_poly_haven_files(payload)
    return {
        "ok": True,
        "message": "Poly Haven file tree fetched",
        "provider": "poly_haven",
        "asset_id": asset_id,
        "asset_type": _infer_poly_haven_asset_type(payload),
        "source_url": url,
        "file_count": len(entries),
        "files": entries,
        "raw_file_tree": payload,
    }


def _path_score(entry, resolution, preferred_formats):
    parts = [part.lower() for part in entry.get("path_parts", [])]
    resolution = str(resolution or "").lower()
    score = 0
    if resolution and resolution in parts:
        score += 100
    for index, file_format in enumerate(preferred_formats):
        if str(file_format).lower() in parts:
            score += max(1, 50 - index)
            break
    return score


def _select_poly_haven_hdri(entries, *, resolution, file_format):
    preferred = [file_format] if file_format else ["hdr", "exr", "jpg", "png"]
    candidates = [entry for entry in entries if (entry.get("path_parts") or [""])[0].lower() == "hdri"]
    candidates.sort(key=lambda item: _path_score(item, resolution, preferred), reverse=True)
    return candidates[:1]


def _select_poly_haven_model(entries, *, resolution, file_format):
    preferred = [file_format] if file_format else ["gltf", "glb", "fbx", "usd", "blend"]
    candidates = []
    for entry in entries:
        parts = [part.lower() for part in entry.get("path_parts", [])]
        if parts and parts[0] in {"gltf", "glb", "fbx", "usd", "blend"}:
            candidates.append(entry)
    candidates.sort(key=lambda item: _path_score(item, resolution, preferred), reverse=True)
    return candidates[:1]


def _select_poly_haven_texture_maps(entries, *, resolution, file_format, map_types=None):
    preferred = [file_format] if file_format else ["jpg", "png", "exr", "tif"]
    requested_maps = {str(item).strip().lower() for item in map_types or [] if str(item).strip()}
    excluded_roots = {"blend", "gltf", "fbx", "usd", "mtlx", "hdri", "backplates", "tonemapped", "colorchart"}
    grouped = {}
    for entry in entries:
        parts = [part.lower() for part in entry.get("path_parts", [])]
        if not parts or parts[0] in excluded_roots:
            continue
        if requested_maps and parts[0] not in requested_maps:
            continue
        grouped.setdefault(parts[0], []).append(entry)
    selected = []
    for items in grouped.values():
        items.sort(key=lambda item: _path_score(item, resolution, preferred), reverse=True)
        if items:
            selected.append(items[0])
    selected.sort(key=lambda item: item.get("logical_path", ""))
    return selected


def _included_poly_haven_entries(entry):
    include = entry.get("include") if isinstance(entry.get("include"), dict) else {}
    entries = []
    for include_path, file_info in include.items():
        if not isinstance(file_info, dict) or not file_info.get("url"):
            continue
        entries.append(
            {
                "logical_path": str(include_path).replace("\\", "/"),
                "path_parts": [part for part in str(include_path).replace("\\", "/").split("/") if part],
                "url": str(file_info.get("url") or ""),
                "md5": str(file_info.get("md5") or ""),
                "size": int(file_info.get("size") or 0),
                "include": {},
                "dependency": True,
            }
        )
    return entries


def _local_poly_haven_path(asset_dir, entry):
    logical = entry.get("logical_path") or _filename_from_url(entry.get("url"), "asset-file")
    logical = logical.replace("\\", "/").strip("/")
    if "." not in os.path.basename(logical):
        logical = os.path.join(logical, _filename_from_url(entry.get("url"), "asset-file"))
    parts = [_sanitize_slug(part, "part") for part in logical.split("/") if part]
    return os.path.join(asset_dir, "files", *parts)


def download_poly_haven_asset(
    *,
    asset_id,
    asset_type="",
    resolution="2k",
    file_format="",
    map_types=None,
    include_dependencies=True,
    cache_dir="",
    timeout=60,
):
    files = inspect_poly_haven_asset_files(asset_id=asset_id, timeout=timeout)
    if not files.get("ok"):
        return files
    asset_type = _poly_haven_type(asset_type or files.get("asset_type") or "all")
    entries = files.get("files") or []
    if asset_type == "hdris":
        selected = _select_poly_haven_hdri(entries, resolution=resolution, file_format=file_format)
    elif asset_type == "textures":
        selected = _select_poly_haven_texture_maps(entries, resolution=resolution, file_format=file_format, map_types=map_types)
    elif asset_type == "models":
        selected = _select_poly_haven_model(entries, resolution=resolution, file_format=file_format)
    else:
        selected = _select_poly_haven_model(entries, resolution=resolution, file_format=file_format) or _select_poly_haven_hdri(
            entries,
            resolution=resolution,
            file_format=file_format,
        )
    if not selected:
        return {
            "ok": False,
            "message": "No matching Poly Haven files found for the requested type/resolution/format",
            "provider": "poly_haven",
            "asset_id": asset_id,
            "asset_type": asset_type,
            "available_files": entries[:50],
        }
    if include_dependencies:
        for entry in list(selected):
            selected.extend(_included_poly_haven_entries(entry))
    asset_dir = _asset_cache_dir("poly_haven", asset_id, cache_dir)
    downloads = []
    for entry in selected:
        destination = _local_poly_haven_path(asset_dir, entry)
        result = _download_file(
            entry["url"],
            destination,
            expected_md5=entry.get("md5", ""),
            expected_size=entry.get("size") or None,
            timeout=timeout,
        )
        result["logical_path"] = entry.get("logical_path", "")
        result["dependency"] = bool(entry.get("dependency", False))
        downloads.append(result)
        if not result.get("ok"):
            manifest = _write_manifest(
                asset_dir,
                {
                    "ok": False,
                    "provider": "poly_haven",
                    "asset_id": asset_id,
                    "asset_type": asset_type,
                    "license": POLY_HAVEN_LICENSE,
                    "source_url": _poly_haven_files_url(asset_id),
                    "downloaded_files": downloads,
                    "message": result.get("message", "Download failed"),
                },
            )
            return manifest
    manifest = _write_manifest(
        asset_dir,
        {
            "ok": True,
            "message": "Poly Haven asset cached",
            "provider": "poly_haven",
            "asset_id": asset_id,
            "asset_type": asset_type,
            "license": POLY_HAVEN_LICENSE,
            "source_url": _poly_haven_files_url(asset_id),
            "resolution": resolution,
            "file_format": file_format,
            "downloaded_files": downloads,
            "import_status": "not_imported",
        },
    )
    return manifest


def _thumbnail_url(result):
    thumbnails = result.get("thumbnails") if isinstance(result.get("thumbnails"), dict) else {}
    images = thumbnails.get("images") if isinstance(thumbnails.get("images"), list) else []
    if not images:
        return ""
    images = sorted(images, key=lambda item: int(item.get("width", 0) or 0), reverse=True)
    return str(images[0].get("url") or "")


def search_sketchfab_models(*, query, downloadable=True, staffpicked=None, animated=None, limit=20, timeout=15):
    query = str(query or "").strip()
    if not query:
        return {"ok": False, "message": "query is required for Sketchfab model search"}
    limit = _bounded_limit(limit)
    params = {
        "type": "models",
        "q": query,
        "count": limit,
        "downloadable": "true" if bool(downloadable) else "false",
    }
    if staffpicked is not None:
        params["staffpicked"] = "true" if bool(staffpicked) else "false"
    if animated is not None:
        params["animated"] = "true" if bool(animated) else "false"
    url = f"{SKETCHFAB_BASE_URL}/search?{urllib.parse.urlencode(params)}"
    payload, error = _fetch_json_result("sketchfab", url, timeout=timeout)
    if error:
        error.update(
            {
                "query": query,
                "models": [],
                "count": 0,
                "download_import_status": "not_attempted",
            }
        )
        return error
    results = payload.get("results") if isinstance(payload, dict) else []
    models = []
    for result in results or []:
        if not isinstance(result, dict):
            continue
        user = result.get("user") if isinstance(result.get("user"), dict) else {}
        license_info = result.get("license") if isinstance(result.get("license"), dict) else {}
        models.append(
            {
                "uid": str(result.get("uid") or ""),
                "name": str(result.get("name") or ""),
                "viewer_url": str(result.get("viewerUrl") or result.get("viewer_url") or ""),
                "is_downloadable": bool(result.get("isDownloadable", result.get("downloadable", False))),
                "user": str(user.get("displayName") or user.get("username") or ""),
                "license": str(license_info.get("label") or license_info.get("name") or ""),
                "thumbnail_url": _thumbnail_url(result),
                "like_count": int(result.get("likeCount") or 0),
                "view_count": int(result.get("viewCount") or 0),
            }
        )
    return {
        "ok": True,
        "message": "Sketchfab models searched",
        "provider": "sketchfab",
        "source_url": url,
        "query": query,
        "count": len(models),
        "models": models,
        "download_import_status": "download_or_import_requires_auth",
    }


def _require_blender():
    if bpy is None or live_preview is None:
        return {"ok": False, "message": "This import helper requires Blender runtime"}
    return None


def _record_created_image(image):
    if live_preview is None or image is None:
        return
    live_preview._record_created_id("image", image.name)


def _record_created_data_for_object(obj):
    if live_preview is None or obj is None:
        return
    live_preview._record_created_id("object", obj.name)
    data = getattr(obj, "data", None)
    if data is None:
        return
    if obj.type == "MESH":
        live_preview._record_created_id("mesh", data.name)
    elif obj.type in {"CURVE", "FONT"}:
        live_preview._record_created_id("curve", data.name)
    elif obj.type == "CAMERA":
        live_preview._record_created_id("camera", data.name)
    elif obj.type == "LIGHT":
        live_preview._record_created_id("light", data.name)
    elif obj.type == "ARMATURE":
        live_preview._record_created_id("armature", data.name)


def _existing_names(collection):
    return {item.name for item in collection} if collection is not None else set()


def _new_names(collection, before):
    return sorted(item.name for item in collection if item.name not in before) if collection is not None else []


def _first_downloaded_file(manifest, *, extensions=()):
    lowered = tuple(ext.lower() for ext in extensions)
    for item in manifest.get("downloaded_files") or []:
        path = item.get("path", "")
        if path and (not lowered or path.lower().endswith(lowered)):
            return path
    return ""


def _texture_map_files(manifest):
    result = {}
    for item in manifest.get("downloaded_files") or []:
        if item.get("dependency"):
            continue
        path = item.get("path", "")
        if not path:
            continue
        logical = str(item.get("logical_path") or path).replace("\\", "/").lower()
        key = logical.split("/", 1)[0]
        result[key] = path
    return result


def _ensure_principled(material):
    material.use_nodes = True
    nodes = material.node_tree.nodes
    principled = next((node for node in nodes if node.type == "BSDF_PRINCIPLED"), None)
    if principled is None:
        principled = nodes.new("ShaderNodeBsdfPrincipled")
    output = next((node for node in nodes if node.type == "OUTPUT_MATERIAL"), None)
    if output is None:
        output = nodes.new("ShaderNodeOutputMaterial")
    if not output.inputs["Surface"].links:
        material.node_tree.links.new(principled.outputs["BSDF"], output.inputs["Surface"])
    return principled


def _socket(principled, *names):
    for name in names:
        socket = principled.inputs.get(name)
        if socket:
            return socket
    return None


def _load_image(path, *, colorspace="sRGB"):
    image = bpy.data.images.load(path, check_existing=True)
    _record_created_image(image)
    try:
        image.colorspace_settings.name = colorspace
    except Exception:
        pass
    return image


def _link_image_to_socket(material, image, socket, *, normal_map=False):
    if socket is None:
        return None
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    image_node = nodes.new("ShaderNodeTexImage")
    image_node.image = image
    if normal_map:
        normal_node = nodes.new("ShaderNodeNormalMap")
        links.new(image_node.outputs["Color"], normal_node.inputs["Color"])
        links.new(normal_node.outputs["Normal"], socket)
        return normal_node
    output_name = "Alpha" if socket.name == "Alpha" and "Alpha" in image_node.outputs else "Color"
    links.new(image_node.outputs[output_name], socket)
    return image_node


def _apply_hdri_world(context, manifest, *, label="Import Poly Haven HDRI"):
    error = _require_blender()
    if error:
        return error
    path = _first_downloaded_file(manifest, extensions=(".hdr", ".exr", ".jpg", ".jpeg", ".png"))
    if not path:
        return {"ok": False, "message": "No HDRI/image file was cached", "manifest": manifest}
    transaction = live_preview.begin(label, context)
    scene = context.scene
    key = f"scene:{scene.name}:world"
    if key not in transaction["before_state"]:
        transaction["before_state"][key] = {
            "kind": "scene_world",
            "scene_name": scene.name,
            "world_name": scene.world.name if scene.world else None,
        }
    world = bpy.data.worlds.new(f"Poly Haven {manifest.get('asset_id', 'HDRI')} World")
    live_preview._record_created_id("world", world.name)
    scene.world = world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputWorld")
    background = nodes.new("ShaderNodeBackground")
    environment = nodes.new("ShaderNodeTexEnvironment")
    image = _load_image(path, colorspace="Linear")
    environment.image = image
    links.new(environment.outputs["Color"], background.inputs["Color"])
    links.new(background.outputs["Background"], output.inputs["Surface"])
    transaction["applied_steps"].append(
        {
            "type": "import_external_asset",
            "label": label,
            "provider": manifest.get("provider"),
            "asset_id": manifest.get("asset_id"),
            "world": world.name,
            "image": image.name,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    manifest["import_status"] = "imported"
    manifest["imported_world"] = world.name
    manifest["imported_images"] = [image.name]
    manifest["transaction_id"] = transaction["id"]
    _write_manifest(manifest["cache_dir"], manifest)
    return {
        "ok": True,
        "message": f"Imported HDRI world from {manifest.get('asset_id')}",
        "world": world.name,
        "image": image.name,
        "manifest": manifest,
        "transaction_id": transaction["id"],
    }


def _apply_texture_material(context, manifest, *, target_object_name="", label="Import Poly Haven texture material"):
    error = _require_blender()
    if error:
        return error
    maps = _texture_map_files(manifest)
    if not maps:
        return {"ok": False, "message": "No texture map files were cached", "manifest": manifest}
    transaction = live_preview.begin(label, context)
    material = bpy.data.materials.new(f"Poly Haven {manifest.get('asset_id', 'Texture')}")
    live_preview._record_created_id("material", material.name)
    material.diffuse_color = (1.0, 1.0, 1.0, 1.0)
    principled = _ensure_principled(material)
    imported_images = []
    for key, path in maps.items():
        lowered = key.lower()
        colorspace = "sRGB" if any(term in lowered for term in ("diff", "albedo", "color", "base")) else "Non-Color"
        image = _load_image(path, colorspace=colorspace)
        imported_images.append(image.name)
        if any(term in lowered for term in ("diff", "albedo", "color", "base")):
            _link_image_to_socket(material, image, _socket(principled, "Base Color"))
        elif any(term in lowered for term in ("normal", "nor")):
            _link_image_to_socket(material, image, _socket(principled, "Normal"), normal_map=True)
        elif "rough" in lowered:
            _link_image_to_socket(material, image, _socket(principled, "Roughness"))
        elif "metal" in lowered:
            _link_image_to_socket(material, image, _socket(principled, "Metallic"))
        elif any(term in lowered for term in ("alpha", "opacity")):
            _link_image_to_socket(material, image, _socket(principled, "Alpha"))
    assigned_object = ""
    target = bpy.data.objects.get(target_object_name) if target_object_name else context.active_object
    if target and getattr(target, "type", "") == "MESH":
        live_preview._record_object_materials(target)
        if target.material_slots:
            target.material_slots[0].material = material
        else:
            target.data.materials.append(material)
        assigned_object = target.name
    transaction["applied_steps"].append(
        {
            "type": "import_external_asset",
            "label": label,
            "provider": manifest.get("provider"),
            "asset_id": manifest.get("asset_id"),
            "material": material.name,
            "assigned_object": assigned_object,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    manifest["import_status"] = "imported"
    manifest["imported_materials"] = [material.name]
    manifest["imported_images"] = imported_images
    manifest["assigned_object"] = assigned_object
    manifest["transaction_id"] = transaction["id"]
    _write_manifest(manifest["cache_dir"], manifest)
    return {
        "ok": True,
        "message": f"Created texture material from {manifest.get('asset_id')}",
        "material": material.name,
        "assigned_object": assigned_object,
        "images": imported_images,
        "manifest": manifest,
        "transaction_id": transaction["id"],
    }


def _import_model_file(filepath):
    format_error = _unsupported_model_import_error(filepath)
    if format_error:
        return format_error
    lower = str(filepath).lower()
    if lower.endswith((".gltf", ".glb")):
        bpy.ops.import_scene.gltf(filepath=filepath)
    elif lower.endswith(".fbx"):
        bpy.ops.import_scene.fbx(filepath=filepath)
    elif lower.endswith((".usd", ".usda", ".usdc")):
        bpy.ops.wm.usd_import(filepath=filepath)
    return {"ok": True}


def _unsupported_model_import_error(filepath):
    lower = str(filepath).lower()
    if lower.endswith((".gltf", ".glb", ".fbx", ".usd", ".usda", ".usdc")):
        return None
    if lower.endswith(".blend"):
        return {"ok": False, "message": "Direct .blend append is not implemented for external asset imports yet"}
    return {"ok": False, "message": f"Unsupported model import format: {os.path.basename(filepath)}"}


def _apply_model_import(context, manifest, *, label="Import external model"):
    error = _require_blender()
    if error:
        return error
    path = _first_downloaded_file(manifest, extensions=(".gltf", ".glb", ".fbx", ".usd", ".usda", ".usdc", ".blend"))
    if not path:
        return {"ok": False, "message": "No importable model file was cached", "manifest": manifest}
    format_error = _unsupported_model_import_error(path)
    if format_error:
        format_error["manifest"] = manifest
        return format_error
    transaction = live_preview.begin(label, context)
    before_objects = _existing_names(bpy.data.objects)
    before_meshes = _existing_names(bpy.data.meshes)
    before_materials = _existing_names(bpy.data.materials)
    before_images = _existing_names(bpy.data.images)
    import_result = _import_model_file(path)
    if not import_result.get("ok"):
        return import_result
    context.view_layer.update()
    imported_objects = _new_names(bpy.data.objects, before_objects)
    imported_meshes = _new_names(bpy.data.meshes, before_meshes)
    imported_materials = _new_names(bpy.data.materials, before_materials)
    imported_images = _new_names(bpy.data.images, before_images)
    for name in imported_objects:
        _record_created_data_for_object(bpy.data.objects.get(name))
    for name in imported_meshes:
        live_preview._record_created_id("mesh", name)
    for name in imported_materials:
        live_preview._record_created_id("material", name)
    for name in imported_images:
        live_preview._record_created_id("image", name)
    transaction["applied_steps"].append(
        {
            "type": "import_external_asset",
            "label": label,
            "provider": manifest.get("provider"),
            "asset_id": manifest.get("asset_id") or manifest.get("uid"),
            "source_file": path,
            "created_objects": imported_objects,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    manifest["import_status"] = "imported"
    manifest["imported_objects"] = imported_objects
    manifest["imported_meshes"] = imported_meshes
    manifest["imported_materials"] = imported_materials
    manifest["imported_images"] = imported_images
    manifest["transaction_id"] = transaction["id"]
    _write_manifest(manifest["cache_dir"], manifest)
    return {
        "ok": True,
        "message": f"Imported model from {os.path.basename(path)}",
        "source_file": path,
        "imported_objects": imported_objects,
        "manifest": manifest,
        "transaction_id": transaction["id"],
    }


def import_poly_haven_asset(
    context,
    *,
    asset_id,
    asset_type="",
    resolution="2k",
    file_format="",
    map_types=None,
    target_object_name="",
    cache_dir="",
    timeout=60,
    label="Import Poly Haven asset",
):
    manifest = download_poly_haven_asset(
        asset_id=asset_id,
        asset_type=asset_type,
        resolution=resolution,
        file_format=file_format,
        map_types=map_types,
        include_dependencies=True,
        cache_dir=cache_dir,
        timeout=timeout,
    )
    if not manifest.get("ok"):
        return manifest
    resolved_type = manifest.get("asset_type") or _poly_haven_type(asset_type)
    if resolved_type == "hdris":
        return _apply_hdri_world(context, manifest, label=label)
    if resolved_type == "textures":
        return _apply_texture_material(context, manifest, target_object_name=target_object_name, label=label)
    if resolved_type == "models":
        return _apply_model_import(context, manifest, label=label)
    return {"ok": False, "message": f"Unsupported Poly Haven import type: {resolved_type}", "manifest": manifest}


def _api_token_authorization_header(token):
    token = str(token or "").strip()
    lowered = token.lower()
    if lowered.startswith("token ") or lowered.startswith("bearer "):
        return token
    return f"Token {token}"


def _auth_header_from_token(
    api_token="",
    *,
    token_env_var=SKETCHFAB_TOKEN_ENV_VAR,
):
    token = str(api_token or "").strip()
    if token:
        return _api_token_authorization_header(token), "argument"

    token, env_name, blocked, _candidates = _first_env_token(
        token_env_var,
        defaults=SKETCHFAB_API_TOKEN_ENV_VARS,
        allowed=SKETCHFAB_ALLOWED_TOKEN_ENV_VARS,
    )
    if blocked:
        return "", f"blocked_env:{blocked}"
    if token:
        return _api_token_authorization_header(token), f"env:{env_name}"
    return "", ""


def get_sketchfab_model_download_info(
    *,
    uid,
    api_token="",
    token_env_var=SKETCHFAB_TOKEN_ENV_VAR,
    model_password="",
    timeout=15,
):
    uid = str(uid or "").strip()
    if not uid:
        return {"ok": False, "message": "uid is required"}
    authorization, auth_source = _auth_header_from_token(
        api_token,
        token_env_var=token_env_var,
    )
    if auth_source.startswith("blocked_env:"):
        return {
            "ok": False,
            "message": "Sketchfab token_env_var must be a Sketchfab-specific environment variable",
            "provider": "sketchfab",
            "uid": uid,
            "auth_required": True,
            "blocked_token_env_var": auth_source.replace("blocked_env:", "", 1),
            "allowed_token_env_vars": sorted(SKETCHFAB_ALLOWED_TOKEN_ENV_VARS),
            "allowed_api_token_env_vars": sorted(SKETCHFAB_ALLOWED_TOKEN_ENV_VARS),
            "auth_method": "api_token",
            "configured_auth_env_vars": _present_auth_env_names(),
        }
    if not authorization:
        return {
            "ok": False,
            "message": (
                "Sketchfab download requires an API token via api_token, SKETCHFAB_API_TOKEN, "
                "or BLENDER_AGENT_BRIDGE_SKETCHFAB_API_TOKEN."
            ),
            "provider": "sketchfab",
            "uid": uid,
            "auth_required": True,
            "auth_method": "api_token",
            "allowed_api_token_env_vars": sorted(SKETCHFAB_ALLOWED_TOKEN_ENV_VARS),
            "allowed_token_env_vars": sorted(SKETCHFAB_ALLOWED_TOKEN_ENV_VARS),
            "configured_auth_env_vars": _present_auth_env_names(),
        }
    headers = {"Authorization": authorization}
    if model_password:
        headers["x-skfb-model-pwd"] = str(model_password)
    url = f"{SKETCHFAB_BASE_URL}/models/{urllib.parse.quote(uid)}/download"
    try:
        payload = _fetch_json_with_headers(url, headers=headers, timeout=timeout)
    except Exception as exc:
        return {
            "ok": False,
            "message": f"Sketchfab download info failed: {type(exc).__name__}: {exc}",
            "provider": "sketchfab",
            "uid": uid,
            "source_url": url,
            "error_type": type(exc).__name__,
            "auth_source": auth_source,
            "auth_method": "api_token",
        }
    gltf = payload.get("gltf") if isinstance(payload, dict) else {}
    download_url = str((gltf or {}).get("url") or "")
    if not download_url:
        return {
            "ok": False,
            "message": "Sketchfab download response did not include a gltf.url",
            "provider": "sketchfab",
            "uid": uid,
            "source_url": url,
            "auth_source": auth_source,
            "auth_method": "api_token",
            "raw_response_keys": sorted(payload.keys()) if isinstance(payload, dict) else [],
        }
    return {
        "ok": True,
        "message": "Sketchfab download info fetched",
        "provider": "sketchfab",
        "uid": uid,
        "source_url": url,
        "download_url": download_url,
        "expires": int((gltf or {}).get("expires") or 0),
        "auth_source": auth_source,
        "auth_method": "api_token",
    }


def _safe_extract_zip(zip_path, destination):
    os.makedirs(destination, exist_ok=True)
    extracted = []
    destination_abs = os.path.abspath(destination)
    with zipfile.ZipFile(zip_path, "r") as archive:
        for member in archive.infolist():
            target = os.path.abspath(os.path.join(destination_abs, member.filename))
            if not (target == destination_abs or target.startswith(destination_abs + os.sep)):
                return {"ok": False, "message": f"Unsafe archive member path: {member.filename}"}
            archive.extract(member, destination_abs)
            if not member.is_dir():
                extracted.append(target)
    return {"ok": True, "extracted_files": extracted}


def _find_importable_model_file(directory):
    preferred = (".gltf", ".glb", ".fbx", ".usd", ".usda", ".usdc")
    candidates = []
    for root, _dirs, files in os.walk(directory):
        for filename in files:
            path = os.path.join(root, filename)
            if filename.lower().endswith(preferred):
                candidates.append(path)
    candidates.sort(key=lambda path: (0 if path.lower().endswith((".gltf", ".glb")) else 1, len(path), path.lower()))
    return candidates[0] if candidates else ""


def download_sketchfab_model(
    *,
    uid,
    api_token="",
    token_env_var=SKETCHFAB_TOKEN_ENV_VAR,
    model_password="",
    cache_dir="",
    timeout=120,
):
    info = get_sketchfab_model_download_info(
        uid=uid,
        api_token=api_token,
        token_env_var=token_env_var,
        model_password=model_password,
        timeout=timeout,
    )
    if not info.get("ok"):
        return info
    asset_dir = _asset_cache_dir("sketchfab", uid, cache_dir)
    archive_path = os.path.join(asset_dir, "download", "gltf.zip")
    download = _download_file(info["download_url"], archive_path, timeout=timeout)
    if not download.get("ok"):
        manifest = _write_manifest(
            asset_dir,
            {
                "ok": False,
                "provider": "sketchfab",
                "uid": uid,
                "source_url": info.get("source_url", ""),
                "downloaded_files": [download],
                "message": download.get("message", "Sketchfab archive download failed"),
                "auth_source": info.get("auth_source", ""),
                "auth_method": info.get("auth_method", ""),
            },
        )
        return manifest
    extract_dir = os.path.join(asset_dir, "extracted")
    extract = _safe_extract_zip(archive_path, extract_dir)
    if not extract.get("ok"):
        manifest = _write_manifest(
            asset_dir,
            {
                "ok": False,
                "provider": "sketchfab",
                "uid": uid,
                "source_url": info.get("source_url", ""),
                "downloaded_files": [download],
                "message": extract.get("message", "Sketchfab archive extraction failed"),
                "auth_source": info.get("auth_source", ""),
                "auth_method": info.get("auth_method", ""),
            },
        )
        return manifest
    import_file = _find_importable_model_file(extract_dir)
    manifest = _write_manifest(
        asset_dir,
        {
            "ok": bool(import_file),
            "message": "Sketchfab model cached" if import_file else "Sketchfab archive did not contain an importable model file",
            "provider": "sketchfab",
            "uid": uid,
            "source_url": info.get("source_url", ""),
            "downloaded_files": [download],
            "extracted_files": extract.get("extracted_files", []),
            "import_file": import_file,
            "license": "see_sketchfab_model_page",
            "auth_source": info.get("auth_source", ""),
            "auth_method": info.get("auth_method", ""),
            "import_status": "not_imported",
        },
    )
    return manifest


def import_sketchfab_model(
    context,
    *,
    uid,
    api_token="",
    token_env_var=SKETCHFAB_TOKEN_ENV_VAR,
    model_password="",
    cache_dir="",
    timeout=120,
    label="Import Sketchfab model",
):
    manifest = download_sketchfab_model(
        uid=uid,
        api_token=api_token,
        token_env_var=token_env_var,
        model_password=model_password,
        cache_dir=cache_dir,
        timeout=timeout,
    )
    if not manifest.get("ok"):
        return manifest
    import_file = manifest.get("import_file", "")
    if import_file:
        manifest.setdefault("downloaded_files", []).insert(
            0,
            {
                "ok": True,
                "path": import_file,
                "cached": True,
                "logical_path": os.path.relpath(import_file, manifest.get("cache_dir", os.path.dirname(import_file))),
            },
        )
    return _apply_model_import(context, manifest, label=label)


def external_asset_cache_diagnostics(*, cache_dir="", max_assets=50):
    root = _cache_root(cache_dir)
    manifests = []
    for current_root, _dirs, files in os.walk(root):
        if "asset_manifest.json" not in files:
            continue
        manifests.append(_read_manifest(os.path.join(current_root, "asset_manifest.json")))
    manifests.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
    max_assets = _bounded_limit(max_assets, default=50, maximum=500)
    assets = []
    provider_counts = {}
    total_bytes = 0
    imported_count = 0
    for manifest in manifests[:max_assets]:
        provider = str(manifest.get("provider") or "unknown")
        provider_counts[provider] = provider_counts.get(provider, 0) + 1
        files = manifest.get("downloaded_files") or []
        size = sum(int(item.get("size") or 0) for item in files if isinstance(item, dict))
        total_bytes += size
        if manifest.get("import_status") == "imported":
            imported_count += 1
        assets.append(
            {
                "provider": provider,
                "asset_id": manifest.get("asset_id") or manifest.get("uid") or "",
                "asset_type": manifest.get("asset_type", ""),
                "license": manifest.get("license", ""),
                "source_url": manifest.get("source_url", ""),
                "cache_dir": manifest.get("cache_dir", ""),
                "manifest_path": manifest.get("manifest_path", ""),
                "file_count": len(files),
                "total_bytes": size,
                "import_status": manifest.get("import_status", ""),
                "imported_objects": manifest.get("imported_objects", []),
                "imported_materials": manifest.get("imported_materials", []),
                "imported_world": manifest.get("imported_world", ""),
                "updated_at": manifest.get("updated_at", ""),
            }
        )
    return {
        "ok": True,
        "message": "External asset cache diagnostics collected",
        "cache_dir": root,
        "auth": {
            "sketchfab": sketchfab_auth_diagnostics(),
        },
        "asset_count": len(manifests),
        "returned_asset_count": len(assets),
        "imported_asset_count": imported_count,
        "provider_counts": provider_counts,
        "total_cached_bytes": total_bytes,
        "assets": assets,
    }
