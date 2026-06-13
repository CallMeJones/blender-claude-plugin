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

    io_open = script_analysis.analyze_script("import io\nio.open('x', 'w')")
    assert io_open["blocked"], io_open

    codecs_open = script_analysis.analyze_script("import codecs\ncodecs.open('x', 'w')")
    assert codecs_open["blocked"], codecs_open

    destructive = script_analysis.analyze_script("import bpy\nbpy.ops.object.delete()")
    assert destructive["ok"], destructive
    assert destructive["risk_level"] == "high", destructive
    assert destructive["warnings"], destructive

    mutating = script_analysis.analyze_script(
        "import bpy\n"
        "mesh = bpy.data.meshes.new('Triangle')\n"
        "obj = bpy.data.objects.new('Triangle', mesh)\n"
        "bpy.context.scene.collection.objects.link(obj)\n"
    )
    assert mutating["ok"], mutating
    assert mutating["risk_level"] == "medium", mutating
    assert mutating["checkpoint_recommended"], mutating

    harmless = script_analysis.analyze_script("print('hello')")
    assert harmless["ok"], harmless
    assert harmless["risk_level"] == "low", harmless
    assert not harmless["checkpoint_recommended"], harmless
    print("smoke_script_analysis: ok")


if __name__ == "__main__":
    main()
