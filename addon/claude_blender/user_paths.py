"""User-data paths for Blender extension runtime artifacts."""

from __future__ import annotations

import os

try:
    import bpy
except ImportError:  # Allows MCP/server-side imports outside Blender.
    bpy = None


LEGACY_BASE_DIR = os.path.join(os.path.expanduser("~"), ".claude_blender")


def _extension_user_root():
    if bpy is None:
        return ""
    extension_path_user = getattr(getattr(bpy, "utils", None), "extension_path_user", None)
    if not extension_path_user:
        return ""
    try:
        return extension_path_user(__package__, path="", create=True)
    except Exception:
        return ""


def user_data_dir(*parts, create=True):
    root = _extension_user_root() or LEGACY_BASE_DIR
    path = os.path.join(root, *[str(part) for part in parts if str(part)])
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def user_data_path(*parts):
    return user_data_dir(*parts, create=False)


def legacy_user_data_path(*parts):
    return os.path.join(LEGACY_BASE_DIR, *[str(part) for part in parts if str(part)])


def register():
    pass


def unregister():
    pass
