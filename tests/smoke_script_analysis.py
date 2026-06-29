"""Smoke test for pure static script analysis."""

from __future__ import annotations

import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon", "claude_blender"))

import script_analysis  # noqa: E402


def main():
    blocked = script_analysis.analyze_script("import os\nos.remove('scene.blend')")
    assert blocked["blocked"], blocked
    assert blocked["risk_level"] == "blocked", blocked
    assert blocked["checkpoint_recommended"], blocked

    aliased_builtin = script_analysis.analyze_script("from builtins import open as o\no('x', 'w')")
    assert aliased_builtin["blocked"], aliased_builtin

    builtin_module = script_analysis.analyze_script("import builtins as b\nb.open('x', 'w')")
    assert builtin_module["blocked"], builtin_module

    reflected_builtin = script_analysis.analyze_script("getattr(__builtins__, 'open')('x', 'w')")
    assert reflected_builtin["blocked"], reflected_builtin

    subscript_builtin = script_analysis.analyze_script("__builtins__['open']('x', 'w')")
    assert subscript_builtin["blocked"], subscript_builtin

    vars_builtin = script_analysis.analyze_script("vars(__builtins__)['open']('x', 'w')")
    assert vars_builtin["blocked"], vars_builtin

    assigned_builtin = script_analysis.analyze_script("o = open\no('x', 'w')")
    assert assigned_builtin["blocked"], assigned_builtin

    dict_builtin = script_analysis.analyze_script("import builtins\nbuiltins.__dict__['open']('x', 'w')")
    assert dict_builtin["blocked"], dict_builtin

    dict_get_builtin = script_analysis.analyze_script("import builtins\nbuiltins.__dict__.get('open')('x', 'w')")
    assert dict_get_builtin["blocked"], dict_get_builtin

    dict_get_alias = script_analysis.analyze_script("import builtins\no = builtins.__dict__.get('open')\no('x', 'w')")
    assert dict_get_alias["blocked"], dict_get_alias

    getattribute_builtin = script_analysis.analyze_script("import builtins\nbuiltins.__getattribute__('open')('x', 'w')")
    assert getattribute_builtin["blocked"], getattribute_builtin

    constant_reflection = script_analysis.analyze_script("name = 'open'\ngetattr(__builtins__, name)('x', 'w')")
    assert constant_reflection["blocked"], constant_reflection

    import_alias = script_analysis.analyze_script("i = __import__\ni('os').remove('x')")
    assert import_alias["blocked"], import_alias

    importlib_module = script_analysis.analyze_script(
        "import importlib\n"
        "os = importlib.import_module('os')\n"
        "os.remove('x')"
    )
    assert importlib_module["blocked"], importlib_module

    importlib_alias = script_analysis.analyze_script(
        "from importlib import import_module as im\n"
        "os = im('os')\n"
        "os.remove('x')"
    )
    assert importlib_alias["blocked"], importlib_alias

    io_buffer = script_analysis.analyze_script("import io\nbuf = io.StringIO()\nbuf.write('x')")
    assert io_buffer["ok"], io_buffer

    io_open = script_analysis.analyze_script("import io\nio.open('x', 'w')")
    assert io_open["blocked"], io_open

    io_module_alias_open = script_analysis.analyze_script("import io as i\ni.open('x', 'w')")
    assert io_module_alias_open["blocked"], io_module_alias_open

    io_assigned_open = script_analysis.analyze_script("import io\no = io.open\no('x', 'w')")
    assert io_assigned_open["blocked"], io_assigned_open

    io_reflected_open = script_analysis.analyze_script("import io\ngetattr(io, 'open')('x', 'w')")
    assert io_reflected_open["blocked"], io_reflected_open

    io_dict_open = script_analysis.analyze_script("import io\nio.__dict__.get('open')('x', 'w')")
    assert io_dict_open["blocked"], io_dict_open

    io_dict_alias_open = script_analysis.analyze_script("import io\nd = io.__dict__\nd['open']('x', 'w')")
    assert io_dict_alias_open["blocked"], io_dict_alias_open

    io_open_alias = script_analysis.analyze_script("from io import open as io_open\nio_open('x', 'w')")
    assert io_open_alias["blocked"], io_open_alias

    io_module_assigned_open = script_analysis.analyze_script("import io\ni = io\ni.open('x', 'w')")
    assert io_module_assigned_open["blocked"], io_module_assigned_open

    io_fileio = script_analysis.analyze_script("import io\nio.FileIO('x', 'w')")
    assert io_fileio["blocked"], io_fileio

    io_fileio_alias = script_analysis.analyze_script("from io import FileIO\nFileIO('x', 'w')")
    assert io_fileio_alias["blocked"], io_fileio_alias

    io_open_code = script_analysis.analyze_script("import io\nio.open_code('x')")
    assert io_open_code["blocked"], io_open_code

    io_star = script_analysis.analyze_script("from io import *\nStringIO()")
    assert io_star["blocked"], io_star

    builtins_dict_alias_open = script_analysis.analyze_script(
        "import builtins as b\nd = b.__dict__\nd['open']('x', 'w')"
    )
    assert builtins_dict_alias_open["blocked"], builtins_dict_alias_open

    codecs_open = script_analysis.analyze_script("import codecs\ncodecs.open('x', 'w')")
    assert codecs_open["blocked"], codecs_open

    privileged_open = script_analysis.analyze_script("open('x', 'w').write('ok')", privileged_capabilities=["filesystem"])
    assert privileged_open["ok"], privileged_open
    assert not privileged_open["trust_window_allowed"], privileged_open

    privileged_io_open = script_analysis.analyze_script("import io\nio.open('x', 'w')", privileged_capabilities=["filesystem"])
    assert privileged_io_open["ok"], privileged_io_open

    privileged_pathlib = script_analysis.analyze_script("from pathlib import Path\nPath('x').write_text('ok')", privileged_capabilities=["filesystem"])
    assert privileged_pathlib["ok"], privileged_pathlib

    privileged_requests = script_analysis.analyze_script("import requests\nrequests.get('https://example.com')", privileged_capabilities=["network"])
    assert privileged_requests["ok"], privileged_requests

    privileged_save = script_analysis.analyze_script(
        "import bpy\nbpy.ops.wm.save_as_mainfile(filepath='C:/tmp/custom.blend')",
        privileged_capabilities=["project_file"],
    )
    assert privileged_save["ok"], privileged_save

    aliased_project_save = script_analysis.analyze_script(
        "import bpy\nops = bpy.ops\nops.wm.save_as_mainfile(filepath='C:/tmp/custom.blend')"
    )
    assert aliased_project_save["blocked"], aliased_project_save

    aliased_project_open = script_analysis.analyze_script(
        "import bpy\nwm = bpy.ops.wm\nwm.open_mainfile(filepath='C:/tmp/custom.blend')"
    )
    assert aliased_project_open["blocked"], aliased_project_open

    assigned_project_save = script_analysis.analyze_script(
        "import bpy\nsave = bpy.ops.wm.save_as_mainfile\nsave(filepath='C:/tmp/custom.blend')"
    )
    assert assigned_project_save["blocked"], assigned_project_save

    import_alias_project_save = script_analysis.analyze_script(
        "import bpy as b\nops = b.ops\nops.wm.save_as_mainfile(filepath='C:/tmp/custom.blend')"
    )
    assert import_alias_project_save["blocked"], import_alias_project_save

    getattr_project_save = script_analysis.analyze_script(
        "import bpy\nsave = getattr(getattr(bpy.ops, 'wm'), 'save_as_mainfile')\nsave(filepath='C:/tmp/custom.blend')"
    )
    assert getattr_project_save["blocked"], getattr_project_save

    getattr_alias_project_save = script_analysis.analyze_script(
        "import bpy\ng = getattr\nsave = g(bpy.ops.wm, 'save_as_mainfile')\nsave(filepath='C:/tmp/custom.blend')"
    )
    assert getattr_alias_project_save["blocked"], getattr_alias_project_save

    getattr_alias_project_open = script_analysis.analyze_script(
        "import bpy\ng = getattr\nwm = g(bpy.ops, 'wm')\nwm.open_mainfile(filepath='C:/tmp/custom.blend')"
    )
    assert getattr_alias_project_open["blocked"], getattr_alias_project_open

    imported_getattr_alias_project_save = script_analysis.analyze_script(
        "import bpy\nfrom builtins import getattr as g\nsave = g(bpy.ops.wm, 'save_as_mainfile')\nsave(filepath='C:/tmp/custom.blend')"
    )
    assert imported_getattr_alias_project_save["blocked"], imported_getattr_alias_project_save

    builtins_getattr_alias_project_save = script_analysis.analyze_script(
        "import bpy\nimport builtins as b\ng = b.getattr\nsave = g(bpy.ops.wm, 'save_as_mainfile')\nsave(filepath='C:/tmp/custom.blend')"
    )
    assert builtins_getattr_alias_project_save["blocked"], builtins_getattr_alias_project_save

    aliased_quit = script_analysis.analyze_script("import bpy\nops = bpy.ops\nops.wm.quit_blender()")
    assert aliased_quit["blocked"], aliased_quit

    privileged_aliased_save = script_analysis.analyze_script(
        "import bpy\nwm = bpy.ops.wm\nwm.save_as_mainfile(filepath='C:/tmp/custom.blend')",
        privileged_capabilities=["project_file"],
    )
    assert privileged_aliased_save["ok"], privileged_aliased_save

    privileged_aliased_quit_still_blocked = script_analysis.analyze_script(
        "import bpy\nwm = bpy.ops.wm\nwm.quit_blender()",
        privileged_capabilities=["project_file"],
    )
    assert privileged_aliased_quit_still_blocked["blocked"], privileged_aliased_quit_still_blocked

    privileged_import_still_blocked = script_analysis.analyze_script(
        "__import__('os').system('echo nope')",
        privileged_capabilities=["filesystem", "network", "project_file"],
    )
    assert privileged_import_still_blocked["blocked"], privileged_import_still_blocked

    privileged_subprocess_still_blocked = script_analysis.analyze_script(
        "import subprocess\nsubprocess.run(['echo', 'nope'])",
        privileged_capabilities=["filesystem", "network", "project_file"],
    )
    assert privileged_subprocess_still_blocked["blocked"], privileged_subprocess_still_blocked

    privileged_quit_still_blocked = script_analysis.analyze_script(
        "import bpy\nbpy.ops.wm.quit_blender()",
        privileged_capabilities=["project_file"],
    )
    assert privileged_quit_still_blocked["blocked"], privileged_quit_still_blocked

    destructive = script_analysis.analyze_script("import bpy\nbpy.ops.object.delete()")
    assert destructive["ok"], destructive
    assert destructive["risk_level"] == "high", destructive
    assert destructive["warnings"], destructive

    persistent_bake = script_analysis.analyze_script("import bpy\nbpy.ops.fluid.bake_all()\nbpy.ops.ptcache.free_bake_all()")
    assert persistent_bake["ok"], persistent_bake
    assert persistent_bake["risk_level"] == "high", persistent_bake
    assert persistent_bake["explicit_approval_required"], persistent_bake
    assert not persistent_bake["trust_window_allowed"], persistent_bake
    assert any("explicit_approval_call:bpy.ops.fluid.bake_all" == reason for reason in persistent_bake["risk_reasons"]), persistent_bake

    aliased_bake = script_analysis.analyze_script("import bpy\nops = bpy.ops\nops.ptcache.bake_all(bake=True)")
    assert aliased_bake["explicit_approval_required"], aliased_bake
    assert not aliased_bake["trust_window_allowed"], aliased_bake

    reflected_bake = script_analysis.analyze_script("import bpy\ngetattr(bpy.ops.ptcache, 'bake_all')(bake=True)")
    assert reflected_bake["explicit_approval_required"], reflected_bake
    assert not reflected_bake["trust_window_allowed"], reflected_bake

    reflected_namespace_bake = script_analysis.analyze_script("import bpy\ngetattr(bpy.ops, 'ptcache').bake_all(bake=True)")
    assert reflected_namespace_bake["explicit_approval_required"], reflected_namespace_bake
    assert not reflected_namespace_bake["trust_window_allowed"], reflected_namespace_bake

    nested_reflected_bake = script_analysis.analyze_script(
        "import bpy\ncache = 'ptcache'\nbake = 'bake_all'\ngetattr(getattr(bpy.ops, cache), bake)(bake=True)"
    )
    assert nested_reflected_bake["explicit_approval_required"], nested_reflected_bake
    assert not nested_reflected_bake["trust_window_allowed"], nested_reflected_bake

    mutating = script_analysis.analyze_script(
        "import bpy\n"
        "mesh = bpy.data.meshes.new('Triangle')\n"
        "obj = bpy.data.objects.new('Triangle', mesh)\n"
        "bpy.context.scene.collection.objects.link(obj)\n"
    )
    assert mutating["ok"], mutating
    assert mutating["risk_level"] == "medium", mutating
    assert mutating["checkpoint_recommended"], mutating

    complex_scene_script = script_analysis.analyze_script(
        """
import bpy
import bmesh
from collections import defaultdict
from dataclasses import dataclass
from mathutils import Vector

@dataclass
class PanelSpec:
    name: str
    offset: Vector
    width: float = 1.0

class ProceduralSceneBuilder:
    def __init__(self):
        self.groups = defaultdict(list)

    def make_panel(self, spec):
        mesh = bpy.data.meshes.new(spec.name + "Mesh")
        verts = [
            (-spec.width, 0.0, -0.5),
            (spec.width, 0.0, -0.5),
            (spec.width, 0.0, 0.5),
            (-spec.width, 0.0, 0.5),
        ]
        mesh.from_pydata(verts, [], [(0, 1, 2, 3)])
        mesh.update()
        obj = bpy.data.objects.new(spec.name, mesh)
        obj.location = spec.offset
        bpy.context.scene.collection.objects.link(obj)
        obj.keyframe_insert(data_path="location", frame=1)
        obj.location.x += 1.5
        obj.keyframe_insert(data_path="location", frame=48)
        self.groups["panels"].append(obj)
        return obj

builder = ProceduralSceneBuilder()
for index in range(12):
    builder.make_panel(PanelSpec(f"Panel_{index:02d}", Vector((index * 0.4, 0.0, 0.0))))
scratch = bmesh.new()
scratch.free()
"""
    )
    assert complex_scene_script["ok"], complex_scene_script
    assert complex_scene_script["risk_level"] == "medium", complex_scene_script

    harmless = script_analysis.analyze_script("print('hello')")
    assert harmless["ok"], harmless
    assert harmless["risk_level"] == "low", harmless
    assert not harmless["checkpoint_recommended"], harmless

    larger_advanced_script = script_analysis.analyze_script("value = 1\n" * 12000)
    assert larger_advanced_script["ok"], larger_advanced_script

    near_limit_advanced_script = script_analysis.analyze_script(
        "payload = '" + ("x" * (script_analysis.MAX_SCRIPT_CHARS - 1000)) + "'\n"
    )
    assert near_limit_advanced_script["ok"], near_limit_advanced_script

    oversized_script = script_analysis.analyze_script(
        "payload = '" + ("x" * (script_analysis.MAX_SCRIPT_CHARS + 1000)) + "'\n"
    )
    assert oversized_script["blocked"], oversized_script
    assert "script_too_large" in oversized_script["risk_reasons"], oversized_script

    oversized_invalid_script = script_analysis.analyze_script(
        "payload = \n" + ("x" * (script_analysis.MAX_SCRIPT_CHARS + 1000))
    )
    assert oversized_invalid_script["blocked"], oversized_invalid_script
    assert "script_too_large" in oversized_invalid_script["risk_reasons"], oversized_invalid_script
    assert "syntax_error" not in oversized_invalid_script["risk_reasons"], oversized_invalid_script

    print("smoke_script_analysis: ok")


if __name__ == "__main__":
    main()
