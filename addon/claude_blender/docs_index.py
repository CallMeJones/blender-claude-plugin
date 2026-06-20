"""Version-aware Blender docs lookup with local API and Manual caches.

The MVP policy is local cache first, official Blender docs second. To keep the
Blender UI responsive, this module starts with curated local snippets and
official URL candidates instead of doing broad web scraping on the main thread.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import urllib.request
import zipfile
from html.parser import HTMLParser

import bpy

from . import context_budget, user_paths


OFFICIAL_DOC_HOSTS = (
    "https://docs.blender.org/api",
    "https://docs.blender.org/manual",
)

CACHE_SCHEMA_VERSION = 1
FULL_API_INDEX_SCHEMA_VERSION = 1
FULL_MANUAL_INDEX_SCHEMA_VERSION = 1
FULL_INDEX_SCHEMA_VERSION = FULL_API_INDEX_SCHEMA_VERSION
MAX_SNIPPET_CHARS = 500
DEFAULT_MAX_API_INDEX_PAGES = 2500
DEFAULT_MAX_INDEX_PAGES = DEFAULT_MAX_API_INDEX_PAGES
DEFAULT_MAX_MANUAL_INDEX_PAGES = 0
MAX_SEARCH_RESULTS = 8
MANUAL_ZIP_FILENAME = "blender_manual_html.zip"

SEED_ENTRIES = (
    {
        "id": "object-keyframe-insert",
        "title": "Object keyframe_insert",
        "keywords": ["animation", "animate", "keyframe", "keyframes", "object", "transform", "location", "rotation", "scale"],
        "url_path": "bpy.types.bpy_struct.html#bpy.types.bpy_struct.keyframe_insert",
        "snippet": "Use keyframe_insert(data_path='location', frame=frame) or similar RNA paths to add transform keyframes. In Blender 5.x, created actions may use layered Action data.",
    },
    {
        "id": "action-layered",
        "title": "Action data and layered animation",
        "keywords": ["action", "fcurve", "fcurves", "layer", "layers", "channelbag", "animation"],
        "url_path": "bpy.types.Action.html",
        "snippet": "Blender 5.x Actions can be layered. Do not assume action.fcurves exists; inspect action.layers, strips, and channelbags when summarizing generated keyframes.",
    },
    {
        "id": "object-transform",
        "title": "Object transforms",
        "keywords": ["object", "transform", "location", "rotation", "scale", "matrix", "dimensions"],
        "url_path": "bpy.types.Object.html",
        "snippet": "Object location, rotation_euler, scale, dimensions, constraints, modifiers, and animation_data are available through bpy.types.Object.",
    },
    {
        "id": "mesh-primitives",
        "title": "Mesh primitive operators",
        "keywords": ["mesh", "primitive", "cube", "sphere", "cylinder", "cone", "plane", "torus"],
        "url_path": "bpy.ops.mesh.html",
        "snippet": "Mesh primitive operators such as primitive_cube_add and primitive_uv_sphere_add create new mesh objects. Prefer direct data API for later edits after creation.",
    },
    {
        "id": "materials",
        "title": "Material data",
        "keywords": ["material", "materials", "shader", "nodes", "color", "principled", "bsdf"],
        "url_path": "bpy.types.Material.html",
        "snippet": "Materials expose diffuse_color, node_tree, use_nodes, and material slots on mesh data. Simple diffuse assignment can be done without generated Python.",
    },
    {
        "id": "camera",
        "title": "Camera data",
        "keywords": ["camera", "lens", "focal", "orbit", "view", "track", "constraint"],
        "url_path": "bpy.types.Camera.html",
        "snippet": "Camera data includes lens and depth-of-field settings. Camera objects can use constraints such as Track To to aim at a target object or empty.",
    },
    {
        "id": "constraints",
        "title": "Constraints and Track To",
        "keywords": ["constraint", "constraints", "track", "track_to", "camera", "target", "orbit"],
        "url_path": "bpy.types.Constraint.html",
        "snippet": "Constraints live on objects. A Track To constraint can make a camera face an empty or target object while a parent empty drives orbit animation.",
    },
    {
        "id": "lights",
        "title": "Light data",
        "keywords": ["light", "lights", "area", "point", "sun", "spot", "energy", "color"],
        "url_path": "bpy.types.Light.html",
        "snippet": "Light data-blocks expose type-specific settings plus common energy and color fields. New light objects are linked into scene collections.",
    },
    {
        "id": "scene-timeline",
        "title": "Scene timeline and render settings",
        "keywords": ["scene", "timeline", "frame", "fps", "frame_start", "frame_end", "render"],
        "url_path": "bpy.types.Scene.html",
        "snippet": "Scene frame_start, frame_end, frame_current, frame_set(), and render.fps control timeline and playback range.",
    },
    {
        "id": "extensions-manifest",
        "title": "Blender extension manifest",
        "keywords": ["extension", "manifest", "addon", "permissions", "network", "files", "packaging"],
        "manual_url": "https://docs.blender.org/manual/en/latest/advanced/extensions/getting_started.html",
        "snippet": "Blender extensions use blender_manifest.toml and declare permissions such as network and files access.",
    },
)


def blender_docs_version():
    version = bpy.app.version
    return f"{version[0]}.{version[1]}"


def docs_zip_name(version):
    return f"blender_python_reference_{version.replace('.', '_')}.zip"


def manual_zip_name(version):
    return MANUAL_ZIP_FILENAME


def docs_base_url(version):
    return f"https://docs.blender.org/api/{version}/"


def manual_base_url(version):
    return f"https://docs.blender.org/manual/en/{version}/"


def docs_zip_url(version):
    return f"{docs_base_url(version)}{docs_zip_name(version)}"


def manual_zip_url(version):
    return f"{manual_base_url(version)}{manual_zip_name(version)}"


def _default_cache_dir():
    return user_paths.user_data_path("docs_cache")


def _online_access_error():
    if bool(getattr(bpy.app, "online_access", True)):
        return ""
    overridden = bool(getattr(bpy.app, "online_access_overriden", False))
    if overridden:
        return "Online access is disabled by Blender command line policy; start Blender without --offline-mode to build docs caches."
    return "Online access is disabled in Blender preferences; enable Allow Online Access before building docs caches."


def _cache_file(cache_dir, version):
    return os.path.join(cache_dir or _default_cache_dir(), f"blender_docs_{version}.json")


def _version_dir(cache_dir, version):
    return os.path.join(cache_dir or _default_cache_dir(), version)


def _zip_file(cache_dir, version):
    return os.path.join(_version_dir(cache_dir, version), docs_zip_name(version))


def _manual_zip_file(cache_dir, version):
    return os.path.join(_version_dir(cache_dir, version), manual_zip_name(version))


def _html_dir(cache_dir, version):
    return os.path.join(_version_dir(cache_dir, version), "html")


def _manual_html_dir(cache_dir, version):
    return os.path.join(_version_dir(cache_dir, version), "manual_html")


def _full_index_file(cache_dir, version):
    return os.path.join(_version_dir(cache_dir, version), "full_index.json")


def _manual_index_file(cache_dir, version):
    return os.path.join(_version_dir(cache_dir, version), "manual_index.json")


def _api_url(version, entry):
    if entry.get("manual_url"):
        return entry["manual_url"]
    return f"https://docs.blender.org/api/{version}/{entry['url_path']}"


def _seed_entries(version):
    entries = []
    for entry in SEED_ENTRIES:
        seeded = dict(entry)
        seeded["url"] = _api_url(version, entry)
        seeded["source"] = "local_seed_cache"
        entries.append(seeded)
    return entries


def seed_docs_cache(*, cache_dir=None, version=None, force=False):
    version = version or blender_docs_version()
    filepath = _cache_file(cache_dir, version)
    if os.path.exists(filepath) and not force:
        return filepath
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    payload = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "blender_version": version,
        "entries": _seed_entries(version),
    }
    with open(filepath, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
    return filepath


def _load_entries(cache_dir, version):
    filepath = _cache_file(cache_dir, version)
    if not os.path.exists(filepath):
        seed_docs_cache(cache_dir=cache_dir, version=version)
    try:
        with open(filepath, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        seed_docs_cache(cache_dir=cache_dir, version=version, force=True)
        with open(filepath, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    return filepath, payload.get("entries", [])


class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.headings = []
        self.parts = []
        self._stack = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "svg", "nav", "footer"}:
            self._skip_depth += 1
        self._stack.append(tag)

    def handle_endtag(self, tag):
        if tag in {"script", "style", "svg", "nav", "footer"} and self._skip_depth > 0:
            self._skip_depth -= 1
        if self._stack:
            self._stack.pop()

    def handle_data(self, data):
        if self._skip_depth:
            return
        text = " ".join(data.split())
        if not text:
            return
        current = self._stack[-1] if self._stack else ""
        if current == "title" and not self.title:
            self.title = text
        elif current in {"h1", "h2", "h3"}:
            if text not in self.headings:
                self.headings.append(text)
            self.parts.append(text)
        elif current in {"p", "li", "dt", "dd", "code", "pre", "span"}:
            self.parts.append(text)


def _normalize_text(text):
    text = re.sub(r"\s+", " ", text or "").strip()
    return text


def _page_symbol(relative_path):
    name = os.path.basename(relative_path)
    if name.endswith(".html"):
        name = name[:-5]
    return name


def _relative_url(relative_path):
    return relative_path.replace(os.sep, "/")


def _parse_html_page(
    filepath,
    relative_path,
    version,
    *,
    base_url=None,
    source="full_api_index",
    id_prefix="api",
):
    with open(filepath, "r", encoding="utf-8", errors="replace") as handle:
        html = handle.read()
    parser = _HTMLTextExtractor()
    parser.feed(html)
    title = _normalize_text(parser.title or (parser.headings[0] if parser.headings else _page_symbol(relative_path)))
    text = _normalize_text(" ".join(parser.parts))
    if not text:
        return None
    symbol = _page_symbol(relative_path)
    url_path = _relative_url(relative_path)
    section = "/".join(url_path.split("/")[:-1])
    path_terms = url_path.replace("/", " ").replace("-", " ").replace("_", " ")
    keywords = sorted(set(_terms(f"{title} {symbol} {path_terms} {' '.join(parser.headings[:5])}")))
    return {
        "id": f"{id_prefix}:{url_path}",
        "title": title,
        "symbol": symbol,
        "keywords": keywords,
        "url": f"{base_url or docs_base_url(version)}{url_path}",
        "local_path": url_path,
        "section": section,
        "snippet": text[:MAX_SNIPPET_CHARS],
        "source": source,
    }


def _safe_extract_zip(zip_path, destination):
    destination_abs = os.path.abspath(destination)
    if os.path.exists(destination_abs):
        shutil.rmtree(destination_abs)
    os.makedirs(destination_abs, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as archive:
        for member in archive.infolist():
            member_name = member.filename.replace("\\", "/")
            if not member_name or member_name.startswith("/") or ".." in member_name.split("/"):
                continue
            target = os.path.abspath(os.path.join(destination_abs, *member_name.split("/")))
            if not target.startswith(destination_abs + os.sep) and target != destination_abs:
                continue
            if member.is_dir():
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with archive.open(member, "r") as source, open(target, "wb") as output:
                shutil.copyfileobj(source, output)


def _download_zip(url, destination):
    offline_error = _online_access_error()
    if offline_error:
        raise RuntimeError(offline_error)
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    temp_fd, temp_path = tempfile.mkstemp(prefix="docs-download-", suffix=".zip", dir=os.path.dirname(destination))
    os.close(temp_fd)
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "BlenderAgentBridge/0.1"})
        with urllib.request.urlopen(request, timeout=120) as response, open(temp_path, "wb") as output:
            shutil.copyfileobj(response, output)
        os.replace(temp_path, destination)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def _find_html_root(html_dir):
    for root, _, files in os.walk(html_dir):
        if "index.html" in files:
            return root
    return html_dir


def _index_html_docs(
    cache_dir,
    version,
    *,
    html_dir=None,
    base_url=None,
    source="full_api_index",
    id_prefix="api",
    max_pages=DEFAULT_MAX_INDEX_PAGES,
):
    html_root = _find_html_root(html_dir or _html_dir(cache_dir, version))
    page_limit = int(max_pages) if max_pages else None
    entries = []
    for root, dirs, files in os.walk(html_root):
        dirs.sort()
        for filename in sorted(files):
            if not filename.endswith(".html"):
                continue
            if filename.startswith("_"):
                continue
            filepath = os.path.join(root, filename)
            relative_path = os.path.relpath(filepath, html_root)
            entry = _parse_html_page(
                filepath,
                relative_path,
                version,
                base_url=base_url,
                source=source,
                id_prefix=id_prefix,
            )
            if entry:
                entries.append(entry)
            if page_limit and len(entries) >= page_limit:
                return entries
    return entries


def _write_index_payload(index_path, payload):
    os.makedirs(os.path.dirname(index_path), exist_ok=True)
    with open(index_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)


def _build_html_docs_cache(
    *,
    cache_dir,
    version,
    index_path,
    zip_path,
    html_path,
    source_url,
    base_url,
    source,
    id_prefix,
    schema_version,
    max_pages,
):
    os.makedirs(os.path.dirname(zip_path), exist_ok=True)
    _download_zip(source_url, zip_path)
    _safe_extract_zip(zip_path, html_path)
    entries = _index_html_docs(
        cache_dir,
        version,
        html_dir=html_path,
        base_url=base_url,
        source=source,
        id_prefix=id_prefix,
        max_pages=max_pages,
    )
    _write_index_payload(
        index_path,
        {
            "schema_version": schema_version,
            "blender_version": version,
            "source_url": source_url,
            "zip_file": zip_path,
            "html_dir": html_path,
            "entry_count": len(entries),
            "entries": entries,
        },
    )


def build_full_api_docs_cache(*, cache_dir=None, version=None, force=False, max_pages=DEFAULT_MAX_API_INDEX_PAGES):
    version = version or blender_docs_version()
    cache_dir = cache_dir or _default_cache_dir()
    index_path = _full_index_file(cache_dir, version)
    zip_path = _zip_file(cache_dir, version)
    html_path = _html_dir(cache_dir, version)
    if os.path.exists(index_path) and not force:
        return docs_cache_status(cache_dir=cache_dir, version=version)

    seed_docs_cache(cache_dir=cache_dir, version=version)
    _build_html_docs_cache(
        cache_dir=cache_dir,
        version=version,
        index_path=index_path,
        zip_path=zip_path,
        html_path=html_path,
        source_url=docs_zip_url(version),
        base_url=docs_base_url(version),
        source="full_api_index",
        id_prefix="api",
        schema_version=FULL_API_INDEX_SCHEMA_VERSION,
        max_pages=max_pages,
    )
    return docs_cache_status(cache_dir=cache_dir, version=version)


def build_full_manual_docs_cache(*, cache_dir=None, version=None, force=False, max_pages=DEFAULT_MAX_MANUAL_INDEX_PAGES):
    version = version or blender_docs_version()
    cache_dir = cache_dir or _default_cache_dir()
    index_path = _manual_index_file(cache_dir, version)
    zip_path = _manual_zip_file(cache_dir, version)
    html_path = _manual_html_dir(cache_dir, version)
    if os.path.exists(index_path) and not force:
        return docs_cache_status(cache_dir=cache_dir, version=version)

    seed_docs_cache(cache_dir=cache_dir, version=version)
    _build_html_docs_cache(
        cache_dir=cache_dir,
        version=version,
        index_path=index_path,
        zip_path=zip_path,
        html_path=html_path,
        source_url=manual_zip_url(version),
        base_url=manual_base_url(version),
        source="full_manual_index",
        id_prefix="manual",
        schema_version=FULL_MANUAL_INDEX_SCHEMA_VERSION,
        max_pages=max_pages,
    )
    return docs_cache_status(cache_dir=cache_dir, version=version)


def build_full_docs_cache(
    *,
    cache_dir=None,
    version=None,
    force=False,
    max_pages=DEFAULT_MAX_API_INDEX_PAGES,
    max_manual_pages=DEFAULT_MAX_MANUAL_INDEX_PAGES,
):
    version = version or blender_docs_version()
    cache_dir = cache_dir or _default_cache_dir()
    seed_docs_cache(cache_dir=cache_dir, version=version)
    build_errors = {}
    if force or not os.path.exists(_full_index_file(cache_dir, version)):
        try:
            build_full_api_docs_cache(cache_dir=cache_dir, version=version, force=force, max_pages=max_pages)
        except Exception as exc:
            build_errors["api"] = f"{type(exc).__name__}: {exc}"
    if force or not os.path.exists(_manual_index_file(cache_dir, version)):
        try:
            build_full_manual_docs_cache(
                cache_dir=cache_dir,
                version=version,
                force=force,
                max_pages=max_manual_pages,
            )
        except Exception as exc:
            build_errors["manual"] = f"{type(exc).__name__}: {exc}"
    status = docs_cache_status(cache_dir=cache_dir, version=version)
    status["build_errors"] = build_errors
    status["api_build_error"] = build_errors.get("api", "")
    status["manual_build_error"] = build_errors.get("manual", "")
    status["build_ok"] = not build_errors
    return status


def _load_index_entries(index_path):
    if not os.path.exists(index_path):
        return []
    try:
        with open(index_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return []
    return payload.get("entries", [])


def _load_full_entries(cache_dir, version):
    index_path = _full_index_file(cache_dir, version)
    return index_path, _load_index_entries(index_path)


def _load_manual_entries(cache_dir, version):
    index_path = _manual_index_file(cache_dir, version)
    return index_path, _load_index_entries(index_path)


def _index_entry_count(index_path):
    if not os.path.exists(index_path):
        return 0
    try:
        with open(index_path, "r", encoding="utf-8") as handle:
            return int((json.load(handle) or {}).get("entry_count", 0))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return 0


def _html_page_count(html_path):
    html_pages = 0
    if os.path.isdir(html_path):
        for _, _, files in os.walk(html_path):
            html_pages += sum(1 for filename in files if filename.endswith(".html"))
    return html_pages


def docs_cache_status(*, cache_dir=None, version=None):
    version = version or blender_docs_version()
    cache_dir = cache_dir or _default_cache_dir()
    seed_path = _cache_file(cache_dir, version)
    full_index_path = _full_index_file(cache_dir, version)
    html_path = _html_dir(cache_dir, version)
    zip_path = _zip_file(cache_dir, version)
    manual_index_path = _manual_index_file(cache_dir, version)
    manual_html_path = _manual_html_dir(cache_dir, version)
    manual_zip_path = _manual_zip_file(cache_dir, version)
    full_entries = _index_entry_count(full_index_path)
    manual_entries = _index_entry_count(manual_index_path)
    html_pages = _html_page_count(html_path)
    manual_html_pages = _html_page_count(manual_html_path)
    return {
        "version": version,
        "cache_dir": cache_dir,
        "seed_cache_file": seed_path,
        "seed_cache_exists": os.path.exists(seed_path),
        "full_docs_zip_url": docs_zip_url(version),
        "full_docs_zip_file": zip_path,
        "full_docs_zip_exists": os.path.exists(zip_path),
        "full_docs_html_dir": html_path,
        "full_docs_html_exists": os.path.isdir(html_path),
        "full_index_file": full_index_path,
        "full_index_exists": os.path.exists(full_index_path),
        "full_index_entries": full_entries,
        "html_pages": html_pages,
        "manual_docs_zip_url": manual_zip_url(version),
        "manual_docs_zip_file": manual_zip_path,
        "manual_docs_zip_exists": os.path.exists(manual_zip_path),
        "manual_docs_html_dir": manual_html_path,
        "manual_docs_html_exists": os.path.isdir(manual_html_path),
        "manual_index_file": manual_index_path,
        "manual_index_exists": os.path.exists(manual_index_path),
        "manual_index_entries": manual_entries,
        "manual_html_pages": manual_html_pages,
    }


def _terms(query):
    return [term for term in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]+", query.lower()) if len(term) > 1]


def _score(entry, terms):
    if not terms:
        return 0
    title = entry.get("title", "").lower()
    snippet = entry.get("snippet", "").lower()
    keywords = {keyword.lower() for keyword in entry.get("keywords", [])}
    score = 0
    for term in terms:
        if term in keywords:
            score += 5
        if term in title:
            score += 3
        if term in snippet:
            score += 1
    return score


def _search_entries(entries, query, max_results):
    terms = _terms(query)
    scored = []
    for entry in entries:
        score = _score(entry, terms)
        if score > 0:
            scored.append((score, entry))
    scored.sort(key=lambda item: (-item[0], item[1].get("title", "")))
    return [
        {
            "id": entry.get("id"),
            "title": entry.get("title"),
            "url": entry.get("url"),
            "snippet": entry.get("snippet"),
            "source": entry.get("source", "local_cache"),
            "local_path": entry.get("local_path", ""),
            "section": entry.get("section", ""),
            "score": score,
        }
        for score, entry in scored[:max_results]
    ]


def _fallback_results(version, query, max_results):
    query_slug = "+".join(_terms(query)) or "bpy"
    return [
        {
            "id": "official-api-index",
            "title": "Blender Python API Index",
            "url": f"https://docs.blender.org/api/{version}/index.html",
            "snippet": "Official Blender Python API index. Use when the local docs cache has no targeted result.",
            "source": "official_url_candidate",
            "score": 0,
        },
        {
            "id": "official-api-search",
            "title": "Blender Python API Search",
            "url": f"https://docs.blender.org/api/{version}/search.html?q={query_slug}",
            "snippet": "Official Blender API search URL for this query.",
            "source": "official_url_candidate",
            "score": 0,
        },
        {
            "id": "official-manual-search",
            "title": "Blender Manual Search",
            "url": f"{manual_base_url(version)}search.html?q={query_slug}",
            "snippet": "Official Blender Manual search URL for workflow and UI concepts that are not covered by Python API reference pages.",
            "source": "official_manual_url_candidate",
            "score": 0,
        },
    ][:max_results]


def _source_kind(source):
    source = str(source or "")
    if "official" in source:
        return "official"
    if "manual" in source:
        return "manual"
    if "api" in source or "seed" in source:
        return "api"
    return "unknown"


def _source_counts(items):
    counts = {}
    for item in items or []:
        source = str(item.get("source") or "unknown")
        counts[source] = counts.get(source, 0) + 1
    return counts


def _number_results(results):
    numbered = []
    for index, result in enumerate(results or [], start=1):
        item = dict(result)
        item["citation_ref"] = f"D{index}"
        numbered.append(item)
    return numbered


def _citation_records(results):
    citations = []
    for index, result in enumerate(results or [], start=1):
        url = result.get("url") or ""
        if not url:
            continue
        citations.append(
            {
                "ref": f"D{index}",
                "title": result.get("title") or "Blender docs",
                "url": url,
                "source": result.get("source", "unknown"),
                "kind": _source_kind(result.get("source")),
                "local_path": result.get("local_path", ""),
                "section": result.get("section", ""),
                "score": int(result.get("score") or 0),
            }
        )
    return citations


def _citation_report(citations):
    if not citations:
        return "No Blender docs citations available."
    parts = [
        f"[{item['ref']}] {item['title']} ({item['source']}, score {item['score']}) - {item['url']}"
        for item in citations[:5]
    ]
    return "Docs used: " + "; ".join(parts)


def _search_report(*, seed_count, api_count, manual_count, results, used_fallbacks):
    source_text = ", ".join(f"{source}:{count}" for source, count in sorted(_source_counts(results).items())) or "none"
    mode = "official fallback URLs" if used_fallbacks else "local indexed docs"
    return (
        f"Searched local docs seed:{seed_count}, api:{api_count}, manual:{manual_count}; "
        f"returned {len(results)} {mode} result(s) from {source_text}."
    )


def search_blender_docs(query, *, cache_dir=None, local_first=True, max_results=5):
    version = blender_docs_version()
    max_results = max(1, min(int(max_results), MAX_SEARCH_RESULTS))
    cache_path, entries = _load_entries(cache_dir, version)
    full_index_path, full_entries = _load_full_entries(cache_dir, version)
    manual_index_path, manual_entries = _load_manual_entries(cache_dir, version)
    all_entries = entries + full_entries + manual_entries
    results = _search_entries(all_entries, query, max_results)
    used_fallbacks = False
    if not results:
        results = _fallback_results(version, query, max_results)
        used_fallbacks = True
    results = _number_results(results)
    citations = _citation_records(results)
    payload = {
        "query": query,
        "version": version,
        "local_first": bool(local_first),
        "cache_file": cache_path,
        "full_index_file": full_index_path,
        "full_index_entries": len(full_entries),
        "manual_index_file": manual_index_path,
        "manual_index_entries": len(manual_entries),
        "searched_indexes": [
            {"name": "seed_cache", "path": cache_path, "entries": len(entries), "exists": os.path.exists(cache_path)},
            {"name": "api_full_index", "path": full_index_path, "entries": len(full_entries), "exists": os.path.exists(full_index_path)},
            {"name": "manual_full_index", "path": manual_index_path, "entries": len(manual_entries), "exists": os.path.exists(manual_index_path)},
        ],
        "results": results,
        "citations": citations,
        "citation_report": _citation_report(citations),
        "search_report": _search_report(
            seed_count=len(entries),
            api_count=len(full_entries),
            manual_count=len(manual_entries),
            results=results,
            used_fallbacks=used_fallbacks,
        ),
        "source_breakdown": _source_counts(results),
        "used_official_fallbacks": used_fallbacks,
        "source_policy": "local seed, full API, and full Manual indexes first; official Blender docs URLs second",
    }
    text = json.dumps(payload, sort_keys=True)
    if len(text) <= context_budget.MAX_DOC_RESULT_CHARS:
        return payload
    while len(payload["results"]) > 1 and len(json.dumps(payload, sort_keys=True)) > context_budget.MAX_DOC_RESULT_CHARS:
        payload["results"].pop()
        payload["citations"] = _citation_records(payload["results"])
        payload["citation_report"] = _citation_report(payload["citations"])
        payload["source_breakdown"] = _source_counts(payload["results"])
        payload["search_report"] = _search_report(
            seed_count=len(entries),
            api_count=len(full_entries),
            manual_count=len(manual_entries),
            results=payload["results"],
            used_fallbacks=used_fallbacks,
        )
    payload["truncated_for_context_budget"] = True
    return payload


def register():
    pass


def unregister():
    pass
