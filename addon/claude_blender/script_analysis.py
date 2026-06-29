"""Static analysis guardrails for approval-gated Blender Python."""

from __future__ import annotations

import ast


MAX_SCRIPT_CHARS = 500_000

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
    "codecs",
    "ftplib",
    "pickle",
}

BLOCKED_MODULE_FUNCTIONS = {
    "io": {"FileIO", "open", "open_code"},
}

FILESYSTEM_CAPABILITIES = {"filesystem", "files", "files:read", "files:write", "asset_import", "project_file"}
NETWORK_CAPABILITIES = {"network", "asset_import"}
PROJECT_FILE_CAPABILITIES = {"project_file"}

PROJECT_FILE_OPERATORS = {
    "bpy.ops.wm.save_as_mainfile",
    "bpy.ops.wm.open_mainfile",
    "bpy.ops.wm.read_homefile",
}

BLENDER_FILE_WINDOW_OPERATORS = PROJECT_FILE_OPERATORS | {"bpy.ops.wm.quit_blender"}

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


def _normalized_capabilities(capabilities):
    return {str(capability or "").strip().lower() for capability in (capabilities or []) if str(capability or "").strip()}


def _filesystem_allowed(capabilities):
    return bool(_normalized_capabilities(capabilities).intersection(FILESYSTEM_CAPABILITIES))


def _network_allowed(capabilities):
    return bool(_normalized_capabilities(capabilities).intersection(NETWORK_CAPABILITIES))


def _project_file_allowed(capabilities):
    return bool(_normalized_capabilities(capabilities).intersection(PROJECT_FILE_CAPABILITIES))


def _blocked_names_for_capabilities(capabilities):
    blocked = set(BLOCKED_NAMES)
    if _filesystem_allowed(capabilities):
        blocked.discard("open")
    return blocked


def _blocked_modules_for_capabilities(capabilities):
    blocked = set(BLOCKED_MODULES)
    if _filesystem_allowed(capabilities):
        blocked.discard("pathlib")
    if _network_allowed(capabilities):
        blocked.difference_update({"requests", "urllib", "http"})
    return blocked


def _blocked_module_functions_for_capabilities(capabilities):
    blocked = {module: set(functions) for module, functions in BLOCKED_MODULE_FUNCTIONS.items()}
    if _filesystem_allowed(capabilities):
        io_blocked = blocked.get("io", set())
        io_blocked.difference_update({"FileIO", "open"})
        if io_blocked:
            blocked["io"] = io_blocked
        else:
            blocked.pop("io", None)
    return blocked


def _builtin_reflection_name(node, builtin_module_aliases, constant_names, blocked_names=BLOCKED_NAMES):
    if isinstance(node.func, ast.Call):
        inner_name = _call_name(node.func.func)
        if inner_name.endswith(".__dict__.get") and node.func.args:
            target = inner_name[: -len(".__dict__.get")]
            attr = _resolved_string(node.func.args[0], constant_names)
            if target in builtin_module_aliases and attr in blocked_names:
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
    if target in builtin_module_aliases and attr in blocked_names:
        return f"{target}.{attr}"
    return ""


def _builtin_subscript_name(node, builtin_module_aliases, constant_names, blocked_names=BLOCKED_NAMES):
    if not isinstance(node, ast.Subscript):
        return ""
    target = _builtin_container_name(node.value, builtin_module_aliases)
    key = _resolved_string(node.slice, constant_names)
    if target in builtin_module_aliases and key in blocked_names:
        return f"{target}.{key}"
    return ""


def _blocked_module_container_name(node, blocked_module_aliases):
    name = _call_name(node)
    if name in blocked_module_aliases:
        return blocked_module_aliases[name]
    if name.endswith(".__dict__"):
        root_name = name[: -len(".__dict__")]
        return blocked_module_aliases.get(root_name, "")
    return ""


def _blocked_module_function_name(node, blocked_module_aliases, constant_names, blocked_module_functions=None):
    blocked_module_functions = BLOCKED_MODULE_FUNCTIONS if blocked_module_functions is None else blocked_module_functions
    reference_name = _call_name(node)
    if "." in reference_name:
        parts = reference_name.split(".")
        module_name = blocked_module_aliases.get(parts[0], parts[0])
        attr_name = parts[-1]
        if attr_name in blocked_module_functions.get(module_name, set()):
            return reference_name
    if isinstance(node, ast.Call):
        call_name = _call_name(node.func)
        if call_name == "getattr" and len(node.args) >= 2:
            module_name = _blocked_module_container_name(node.args[0], blocked_module_aliases)
            attr_name = _resolved_string(node.args[1], constant_names)
        elif call_name.endswith(".__dict__.get") and node.args:
            module_name = _blocked_module_container_name(node.func.value, blocked_module_aliases)
            attr_name = _resolved_string(node.args[0], constant_names)
        elif call_name.endswith(".__getattribute__") and node.args:
            module_name = _blocked_module_container_name(node.func.value, blocked_module_aliases)
            attr_name = _resolved_string(node.args[0], constant_names)
        else:
            module_name = ""
            attr_name = ""
        if attr_name in blocked_module_functions.get(module_name, set()):
            return f"{module_name}.{attr_name}"
    if isinstance(node, ast.Subscript):
        module_name = _blocked_module_container_name(node.value, blocked_module_aliases)
        attr_name = _resolved_string(node.slice, constant_names)
        if attr_name in blocked_module_functions.get(module_name, set()):
            return f"{module_name}.{attr_name}"
    return ""


def _blocked_reference_name(node, blocked_name_aliases, builtin_module_aliases, constant_names, blocked_names=BLOCKED_NAMES):
    reference_name = _call_name(node)
    root_name = reference_name.split(".")[0]
    attr_name = reference_name.split(".")[-1]
    if root_name in blocked_name_aliases:
        return reference_name
    if root_name in builtin_module_aliases and attr_name in blocked_names:
        return reference_name
    if isinstance(node, ast.Call):
        return _builtin_reflection_name(node, builtin_module_aliases, constant_names, blocked_names)
    return _builtin_subscript_name(node, builtin_module_aliases, constant_names, blocked_names)


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


def _resolved_getattr_name(node, constant_names, approval_aliases=None, getattr_aliases=None):
    if not isinstance(node, ast.Call):
        return ""
    getattr_aliases = getattr_aliases or {"getattr"}
    if _call_name(node.func) not in getattr_aliases or len(node.args) < 2:
        return ""
    target = _approval_reference_name(node.args[0], constant_names, approval_aliases, getattr_aliases)
    attr = _resolved_string(node.args[1], constant_names)
    if target and attr:
        return f"{target}.{attr}"
    return ""


def _approval_reference_name(node, constant_names, approval_aliases=None, getattr_aliases=None):
    approval_aliases = approval_aliases or {}
    if isinstance(node, ast.Name):
        return approval_aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        parent = _approval_reference_name(node.value, constant_names, approval_aliases, getattr_aliases)
        reference = f"{parent}.{node.attr}" if parent else node.attr
        return approval_aliases.get(reference, reference)
    if isinstance(node, ast.Call):
        reference = _resolved_getattr_name(node, constant_names, approval_aliases, getattr_aliases)
        return approval_aliases.get(reference, reference)
    return ""


def _approval_call_name(node, constant_names, approval_aliases=None, getattr_aliases=None):
    return _approval_reference_name(node, constant_names, approval_aliases, getattr_aliases) or _call_name(node)


def _is_blender_reference(reference):
    return reference == "bpy" or reference.startswith("bpy.")


def _imported_approval_aliases(node):
    aliases = {}
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name == "bpy":
                aliases[alias.asname or "bpy"] = "bpy"
    elif isinstance(node, ast.ImportFrom) and node.module:
        module = node.module
        for alias in node.names:
            local_name = alias.asname or alias.name
            if module == "bpy" and alias.name == "ops":
                aliases[local_name] = "bpy.ops"
            elif module == "bpy.ops" and alias.name == "wm":
                aliases[local_name] = "bpy.ops.wm"
            elif module == "bpy.ops.wm":
                aliases[local_name] = f"bpy.ops.wm.{alias.name}"
    return aliases


def _imported_getattr_aliases(node):
    aliases = set()
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name in BUILTINS_MODULES:
                aliases.add(f"{alias.asname or alias.name}.getattr")
    elif isinstance(node, ast.ImportFrom) and node.module in BUILTINS_MODULES:
        for alias in node.names:
            if alias.name == "getattr":
                aliases.add(alias.asname or alias.name)
    return aliases


def analyze_script(source, *, privileged_capabilities=None):
    privileged_capabilities = _normalized_capabilities(privileged_capabilities)
    blocked_names = _blocked_names_for_capabilities(privileged_capabilities)
    blocked_modules = _blocked_modules_for_capabilities(privileged_capabilities)
    blocked_module_functions = _blocked_module_functions_for_capabilities(privileged_capabilities)
    blocks = []
    warnings = []
    explicit_approval_reasons = []
    risk_reasons = []
    risk_level = "low"
    if len(source) > MAX_SCRIPT_CHARS:
        return {
            "ok": False,
            "blocked": True,
            "issues": [f"Script is too large: {len(source)} chars > {MAX_SCRIPT_CHARS}"],
            "warnings": [],
            "risk_level": "blocked",
            "risk_reasons": ["script_too_large"],
            "checkpoint_recommended": True,
            "explicit_approval_required": False,
            "explicit_approval_reasons": [],
            "privileged_capabilities": sorted(privileged_capabilities),
            "trust_window_allowed": False,
        }
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
            "privileged_capabilities": sorted(privileged_capabilities),
            "trust_window_allowed": False,
        }
    for capability in sorted(privileged_capabilities):
        risk_reasons.append(f"privileged_capability:{capability}")
    blocked_name_aliases = set(blocked_names)
    builtin_module_aliases = set(BUILTINS_MODULES)
    blocked_module_aliases = {}
    approval_aliases = {"bpy": "bpy"}
    getattr_aliases = {"getattr"}
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
                if root_name in blocked_module_functions:
                    blocked_module_aliases[local_name] = root_name
            approval_aliases.update(_imported_approval_aliases(node))
            getattr_aliases.update(_imported_getattr_aliases(node))
        if isinstance(node, ast.ImportFrom) and node.module:
            approval_aliases.update(_imported_approval_aliases(node))
            getattr_aliases.update(_imported_getattr_aliases(node))
            root_name = node.module.split(".")[0]
            blocked_functions = blocked_module_functions.get(root_name, set())
            for alias in node.names:
                if blocked_functions and alias.name == "*":
                    blocks.append(f"Line {_line(node)} blocked import: {node.module}.*")
                    risk_reasons.append(f"blocked_import:{node.module}.*")
                elif alias.name in blocked_functions:
                    local_name = alias.asname or alias.name
                    blocked_name_aliases.add(local_name)
                    blocks.append(f"Line {_line(node)} blocked import: {node.module}.{alias.name}")
                    risk_reasons.append(f"blocked_import:{node.module}.{alias.name}")
            if root_name in BUILTINS_MODULES:
                for alias in node.names:
                    if alias.name == "*":
                        blocks.append(f"Line {_line(node)} blocked import: {node.module}.*")
                        risk_reasons.append(f"blocked_import:{node.module}.*")
                    elif alias.name in blocked_names:
                        local_name = alias.asname or alias.name
                        blocked_name_aliases.add(local_name)
                        blocks.append(f"Line {_line(node)} blocked import: {node.module}.{alias.name}")
                        risk_reasons.append(f"blocked_import:{node.module}.{alias.name}")
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                builtin_container = _builtin_container_name(node.value, builtin_module_aliases)
                blocked_module_container = _blocked_module_container_name(node.value, blocked_module_aliases)
                if builtin_container:
                    for name in _assigned_names(node):
                        if name not in builtin_module_aliases:
                            builtin_module_aliases.add(name)
                            changed = True
                if blocked_module_container:
                    for name in _assigned_names(node):
                        if blocked_module_aliases.get(name) != blocked_module_container:
                            blocked_module_aliases[name] = blocked_module_container
                            changed = True
                if _call_name(node.value) in getattr_aliases:
                    for name in _assigned_names(node):
                        if name not in getattr_aliases:
                            getattr_aliases.add(name)
                            changed = True
                approval_reference = _approval_reference_name(
                    node.value,
                    constant_names,
                    approval_aliases,
                    getattr_aliases,
                )
                if _is_blender_reference(approval_reference):
                    for name in _assigned_names(node):
                        if approval_aliases.get(name) != approval_reference:
                            approval_aliases[name] = approval_reference
                            changed = True
                blocked_reference = _blocked_reference_name(
                    node.value,
                    blocked_name_aliases,
                    builtin_module_aliases,
                    constant_names,
                    blocked_names,
                )
                blocked_module_reference = _blocked_module_function_name(
                    node.value,
                    blocked_module_aliases,
                    constant_names,
                    blocked_module_functions,
                )
                if not (blocked_reference or blocked_module_reference):
                    continue
                for name in _assigned_names(node):
                    if name not in blocked_name_aliases:
                        blocked_name_aliases.add(name)
                        changed = True
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            call_name = _call_name(node.func)
            approval_call_name = _approval_call_name(node.func, constant_names, approval_aliases, getattr_aliases)
            root_name = call_name.split(".")[0]
            attr_name = (approval_call_name or call_name).split(".")[-1]
            reflected_builtin = _builtin_reflection_name(node, builtin_module_aliases, constant_names, blocked_names)
            subscript_builtin = _builtin_subscript_name(node.func, builtin_module_aliases, constant_names, blocked_names)
            if root_name in blocked_name_aliases:
                blocks.append(f"Line {_line(node)} blocked call: {call_name}")
                risk_reasons.append(f"blocked_call:{call_name}")
            if root_name in builtin_module_aliases and attr_name in blocked_names:
                blocks.append(f"Line {_line(node)} blocked builtin call: {call_name}")
                risk_reasons.append(f"blocked_builtin_call:{call_name}")
            if reflected_builtin:
                blocks.append(f"Line {_line(node)} blocked builtin reflection: {reflected_builtin}")
                risk_reasons.append(f"blocked_builtin_reflection:{reflected_builtin}")
            if subscript_builtin:
                blocks.append(f"Line {_line(node)} blocked builtin subscript call: {subscript_builtin}")
                risk_reasons.append(f"blocked_builtin_subscript:{subscript_builtin}")
            blocked_module_call = _blocked_module_function_name(
                node.func,
                blocked_module_aliases,
                constant_names,
                blocked_module_functions,
            )
            if blocked_module_call:
                blocks.append(f"Line {_line(node)} blocked module call: {blocked_module_call}")
                risk_reasons.append(f"blocked_module_call:{blocked_module_call}")
            if approval_call_name in BLENDER_FILE_WINDOW_OPERATORS and (
                approval_call_name == "bpy.ops.wm.quit_blender" or not _project_file_allowed(privileged_capabilities)
            ):
                blocks.append(f"Line {_line(node)} blocked Blender file/window operation: {approval_call_name}")
                risk_reasons.append(f"blocked_blender_file_op:{approval_call_name}")
            if _requires_explicit_approval(approval_call_name):
                reason = (
                    f"Line {_line(node)} persistent simulation/cache operator requires explicit "
                    f"one-time user approval and cannot auto-run under external script trust: {approval_call_name}"
                )
                warnings.append(reason)
                explicit_approval_reasons.append(reason)
                risk_level = _risk_max(risk_level, "high")
                risk_reasons.append(f"explicit_approval_call:{approval_call_name}")
            risk_call_name = approval_call_name or call_name
            if attr_name in WARNING_ATTRS or call_name in HIGH_RISK_CALLS or risk_call_name in HIGH_RISK_CALLS:
                warnings.append(f"Line {_line(node)} risky call: {risk_call_name}")
                risk_level = _risk_max(risk_level, "high")
                risk_reasons.append(f"risky_call:{risk_call_name}")
            elif call_name.startswith("bpy.ops.") or risk_call_name.startswith("bpy.ops.") or attr_name in MUTATION_HINTS:
                risk_level = _risk_max(risk_level, "medium")
                risk_reasons.append(f"mutation_hint:{risk_call_name}")
        if isinstance(node, ast.While) and isinstance(node.test, ast.Constant) and node.test.value is True:
            warnings.append(f"Line {_line(node)} possible unbounded loop: while True")
            risk_level = _risk_max(risk_level, "high")
            risk_reasons.append("possible_unbounded_loop")
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in blocked_modules:
                    blocks.append(f"Line {_line(node)} blocked import: {alias.name}")
                    risk_reasons.append(f"blocked_import:{alias.name}")
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in blocked_modules:
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
        "privileged_capabilities": sorted(privileged_capabilities),
        "trust_window_allowed": bool(not blocks and not explicit_approval_reasons and not privileged_capabilities),
    }
