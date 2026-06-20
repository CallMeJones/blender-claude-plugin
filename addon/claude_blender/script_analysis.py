"""Static analysis guardrails for approval-gated Blender Python."""

from __future__ import annotations

import ast


MAX_SCRIPT_CHARS = 80_000

BLOCKED_NAMES = {
    "eval",
    "exec",
    "compile",
    "__import__",
    "open",
    "input",
    "globals",
    "locals",
    "vars",
}

BLOCKED_MODULES = {
    "os",
    "subprocess",
    "socket",
    "shutil",
    "pathlib",
    "requests",
    "urllib",
    "http",
    "importlib",
    "io",
    "codecs",
    "ftplib",
    "pickle",
}

BUILTINS_MODULES = {"builtins", "__builtins__"}

WARNING_ATTRS = {
    "delete",
    "remove",
    "unlink",
    "orphans_purge",
    "save_as_mainfile",
    "open_mainfile",
    "quit_blender",
}

HIGH_RISK_CALLS = {
    "bpy.ops.object.delete",
    "bpy.ops.mesh.delete",
    "bpy.ops.outliner.orphans_purge",
}

EXPLICIT_APPROVAL_OPERATOR_PREFIXES = (
    "bpy.ops.fluid.bake",
    "bpy.ops.fluid.free",
    "bpy.ops.ptcache.bake",
    "bpy.ops.ptcache.free",
)

EXPLICIT_APPROVAL_OPERATOR_SEGMENTS = (
    ".fluid.bake",
    ".fluid.free",
    ".ptcache.bake",
    ".ptcache.free",
)

MUTATION_HINTS = {
    "animation_data_create",
    "clear",
    "from_pydata",
    "keyframe_insert",
    "link",
    "new",
}

RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "blocked": 3}


def _line(node):
    return getattr(node, "lineno", "?")


def _call_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _constant_string(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else ""


def _assigned_names(node):
    names = []
    for target in getattr(node, "targets", []):
        if isinstance(target, ast.Name):
            names.append(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                if isinstance(element, ast.Name):
                    names.append(element.id)
    return names


def _builtin_container_name(node, builtin_module_aliases):
    name = _call_name(node)
    if name in builtin_module_aliases:
        return name
    if name.endswith(".__dict__"):
        root_name = name[: -len(".__dict__")]
        if root_name in builtin_module_aliases:
            return root_name
    return ""


def _resolved_string(node, constant_names):
    value = _constant_string(node)
    if value:
        return value
    if isinstance(node, ast.Name):
        return constant_names.get(node.id, "")
    return ""


def _builtin_reflection_name(node, builtin_module_aliases, constant_names):
    if isinstance(node.func, ast.Call):
        inner_name = _call_name(node.func.func)
        if inner_name.endswith(".__dict__.get") and node.func.args:
            target = inner_name[: -len(".__dict__.get")]
            attr = _resolved_string(node.func.args[0], constant_names)
            if target in builtin_module_aliases and attr in BLOCKED_NAMES:
                return f"{target}.{attr}"
        return ""
    call_name = _call_name(node.func)
    if call_name == "getattr" and len(node.args) >= 2:
        target = _builtin_container_name(node.args[0], builtin_module_aliases)
        attr = _resolved_string(node.args[1], constant_names)
    elif call_name.endswith(".__dict__.get") and node.args:
        target = call_name[: -len(".__dict__.get")]
        attr = _resolved_string(node.args[0], constant_names)
    elif call_name.endswith(".__getattribute__") and node.args:
        target = call_name[: -len(".__getattribute__")]
        attr = _resolved_string(node.args[0], constant_names)
    else:
        return ""
    if target in builtin_module_aliases and attr in BLOCKED_NAMES:
        return f"{target}.{attr}"
    return ""


def _builtin_subscript_name(node, builtin_module_aliases, constant_names):
    if not isinstance(node, ast.Subscript):
        return ""
    target = _builtin_container_name(node.value, builtin_module_aliases)
    key = _resolved_string(node.slice, constant_names)
    if target in builtin_module_aliases and key in BLOCKED_NAMES:
        return f"{target}.{key}"
    return ""


def _blocked_reference_name(node, blocked_name_aliases, builtin_module_aliases, constant_names):
    reference_name = _call_name(node)
    root_name = reference_name.split(".")[0]
    attr_name = reference_name.split(".")[-1]
    if root_name in blocked_name_aliases:
        return reference_name
    if root_name in builtin_module_aliases and attr_name in BLOCKED_NAMES:
        return reference_name
    if isinstance(node, ast.Call):
        return _builtin_reflection_name(node, builtin_module_aliases, constant_names)
    return _builtin_subscript_name(node, builtin_module_aliases, constant_names)


def _risk_max(*levels):
    selected = "low"
    for level in levels:
        if RISK_ORDER.get(str(level), 0) > RISK_ORDER[selected]:
            selected = str(level)
    return selected


def _requires_explicit_approval(call_name):
    normalized = f".{call_name}"
    return any(call_name.startswith(prefix) for prefix in EXPLICIT_APPROVAL_OPERATOR_PREFIXES) or any(
        segment in normalized for segment in EXPLICIT_APPROVAL_OPERATOR_SEGMENTS
    )


def _resolved_getattr_name(node, constant_names):
    if not isinstance(node, ast.Call):
        return ""
    if _call_name(node.func) != "getattr" or len(node.args) < 2:
        return ""
    target = _approval_reference_name(node.args[0], constant_names)
    attr = _resolved_string(node.args[1], constant_names)
    if target and attr:
        return f"{target}.{attr}"
    return ""


def _approval_reference_name(node, constant_names):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _approval_reference_name(node.value, constant_names)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Call):
        return _resolved_getattr_name(node, constant_names)
    return ""


def _approval_call_name(node, constant_names):
    return _approval_reference_name(node, constant_names) or _call_name(node)


def analyze_script(source):
    blocks = []
    warnings = []
    explicit_approval_reasons = []
    risk_reasons = []
    risk_level = "low"
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return {
            "ok": False,
            "blocked": True,
            "issues": [f"Syntax error: {exc}"],
            "warnings": [],
            "risk_level": "blocked",
            "risk_reasons": ["syntax_error"],
            "checkpoint_recommended": True,
            "explicit_approval_required": False,
            "explicit_approval_reasons": [],
            "trust_window_allowed": False,
        }
    if len(source) > MAX_SCRIPT_CHARS:
        blocks.append(f"Script is too large: {len(source)} chars > {MAX_SCRIPT_CHARS}")
        risk_reasons.append("script_too_large")
    blocked_name_aliases = set(BLOCKED_NAMES)
    builtin_module_aliases = set(BUILTINS_MODULES)
    constant_names = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            assigned_value = _constant_string(node.value)
            if assigned_value:
                for name in _assigned_names(node):
                    constant_names[name] = assigned_value
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_name = alias.name.split(".")[0]
                local_name = alias.asname or root_name
                if root_name in BUILTINS_MODULES:
                    builtin_module_aliases.add(local_name)
        if isinstance(node, ast.ImportFrom) and node.module:
            root_name = node.module.split(".")[0]
            if root_name in BUILTINS_MODULES:
                for alias in node.names:
                    if alias.name == "*":
                        blocks.append(f"Line {_line(node)} blocked import: {node.module}.*")
                        risk_reasons.append(f"blocked_import:{node.module}.*")
                    elif alias.name in BLOCKED_NAMES:
                        local_name = alias.asname or alias.name
                        blocked_name_aliases.add(local_name)
                        blocks.append(f"Line {_line(node)} blocked import: {node.module}.{alias.name}")
                        risk_reasons.append(f"blocked_import:{node.module}.{alias.name}")
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                if not _blocked_reference_name(
                    node.value,
                    blocked_name_aliases,
                    builtin_module_aliases,
                    constant_names,
                ):
                    continue
                for name in _assigned_names(node):
                    if name not in blocked_name_aliases:
                        blocked_name_aliases.add(name)
                        changed = True
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            call_name = _call_name(node.func)
            approval_call_name = _approval_call_name(node.func, constant_names)
            root_name = call_name.split(".")[0]
            attr_name = call_name.split(".")[-1]
            reflected_builtin = _builtin_reflection_name(node, builtin_module_aliases, constant_names)
            subscript_builtin = _builtin_subscript_name(node.func, builtin_module_aliases, constant_names)
            if root_name in blocked_name_aliases:
                blocks.append(f"Line {_line(node)} blocked call: {call_name}")
                risk_reasons.append(f"blocked_call:{call_name}")
            if root_name in builtin_module_aliases and attr_name in BLOCKED_NAMES:
                blocks.append(f"Line {_line(node)} blocked builtin call: {call_name}")
                risk_reasons.append(f"blocked_builtin_call:{call_name}")
            if reflected_builtin:
                blocks.append(f"Line {_line(node)} blocked builtin reflection: {reflected_builtin}")
                risk_reasons.append(f"blocked_builtin_reflection:{reflected_builtin}")
            if subscript_builtin:
                blocks.append(f"Line {_line(node)} blocked builtin subscript call: {subscript_builtin}")
                risk_reasons.append(f"blocked_builtin_subscript:{subscript_builtin}")
            if call_name in {"bpy.ops.wm.save_as_mainfile", "bpy.ops.wm.open_mainfile", "bpy.ops.wm.quit_blender"}:
                blocks.append(f"Line {_line(node)} blocked Blender file/window operation: {call_name}")
                risk_reasons.append(f"blocked_blender_file_op:{call_name}")
            if _requires_explicit_approval(approval_call_name):
                reason = (
                    f"Line {_line(node)} persistent simulation/cache operator requires explicit "
                    f"one-time user approval and cannot auto-run under external script trust: {approval_call_name}"
                )
                warnings.append(reason)
                explicit_approval_reasons.append(reason)
                risk_level = _risk_max(risk_level, "high")
                risk_reasons.append(f"explicit_approval_call:{approval_call_name}")
            if attr_name in WARNING_ATTRS or call_name in HIGH_RISK_CALLS:
                warnings.append(f"Line {_line(node)} risky call: {call_name}")
                risk_level = _risk_max(risk_level, "high")
                risk_reasons.append(f"risky_call:{call_name}")
            elif call_name.startswith("bpy.ops.") or attr_name in MUTATION_HINTS:
                risk_level = _risk_max(risk_level, "medium")
                risk_reasons.append(f"mutation_hint:{call_name}")
        if isinstance(node, ast.While) and isinstance(node.test, ast.Constant) and node.test.value is True:
            warnings.append(f"Line {_line(node)} possible unbounded loop: while True")
            risk_level = _risk_max(risk_level, "high")
            risk_reasons.append("possible_unbounded_loop")
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in BLOCKED_MODULES:
                    blocks.append(f"Line {_line(node)} blocked import: {alias.name}")
                    risk_reasons.append(f"blocked_import:{alias.name}")
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in BLOCKED_MODULES:
                blocks.append(f"Line {_line(node)} blocked import: {node.module}")
                risk_reasons.append(f"blocked_import:{node.module}")
    if blocks:
        risk_level = "blocked"
    return {
        "ok": not blocks,
        "blocked": bool(blocks),
        "issues": blocks,
        "warnings": warnings,
        "risk_level": risk_level,
        "risk_reasons": risk_reasons,
        "checkpoint_recommended": risk_level in {"medium", "high", "blocked"},
        "explicit_approval_required": bool(explicit_approval_reasons),
        "explicit_approval_reasons": explicit_approval_reasons,
        "trust_window_allowed": bool(not blocks and not explicit_approval_reasons),
    }
