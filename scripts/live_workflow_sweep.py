"""Live bridge workflow sweep for major helper-first paths.

Run with Blender open, the extension loaded, and the bridge started:

    python scripts/live_workflow_sweep.py

The sweep avoids external network downloads. It plans asset/director workflows,
applies small reversible local helper edits, captures evidence, and reverts the
pending preview unless --keep-preview is passed.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def _read_json(url: str, *, timeout: float) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_tool(base_url: str, name: str, arguments: dict | None = None, *, timeout: float) -> dict:
    payload = json.dumps({"name": name, "arguments": arguments or {}}).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/tool",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    result = payload.get("result")
    return result if isinstance(result, dict) else payload


def _require_ok(label: str, result: dict) -> None:
    if not result.get("ok"):
        raise RuntimeError(f"{label} failed: {result.get('message') or result}")


def _target_mesh(base_url: str, *, timeout: float) -> tuple[str, bool]:
    scene = _post_tool(base_url, "list_scene_objects", {"max_objects": 200}, timeout=timeout)
    _require_ok("list_scene_objects", scene)
    objects = scene.get("objects") or []
    for item in objects:
        if item.get("name") == "Cube" and item.get("type") == "MESH":
            return "Cube", False
    for item in objects:
        if item.get("type") == "MESH" and item.get("name"):
            return str(item["name"]), False
    created = _post_tool(
        base_url,
        "create_primitive",
        {
            "primitive_type": "CUBE",
            "name": "Agent Bridge Sweep Cube",
            "location": [0.0, 0.0, 0.5],
            "scale": [1.0, 1.0, 1.0],
        },
        timeout=timeout,
    )
    _require_ok("create_primitive", created)
    return str(created.get("object") or created.get("name") or "Agent Bridge Sweep Cube"), True


def _print_step(label: str, result: dict, extra: str = "") -> None:
    suffix = f" {extra}" if extra else ""
    print(f"ok: {label}{suffix}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sweep major live Blender Agent Bridge workflows.")
    parser.add_argument("--bridge-url", default="http://127.0.0.1:8765")
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--skip-viewport", action="store_true")
    parser.add_argument("--keep-preview", action="store_true")
    args = parser.parse_args()

    base_url = args.bridge_url.rstrip("/")
    preview_started = False
    try:
        health = _read_json(f"{base_url}/health", timeout=args.timeout)
        _require_ok("bridge health", health)
        print(
            "bridge ok:",
            f"Blender {health.get('blender_version', '?')}",
            f"source {health.get('addon_runtime_source_status', '?')}",
        )

        target, target_created_preview = _target_mesh(base_url, timeout=args.timeout)
        preview_started = preview_started or target_created_preview
        _print_step("target mesh", {"ok": True}, target)

        director_plan = _post_tool(
            base_url,
            "plan_director_workflow",
            {
                "prompt": "Director workflow: import an asset, build a product scene, animate a reveal, review evidence, then ask whether to commit or revert.",
                "target_objects": [target],
            },
            timeout=args.timeout,
        )
        _require_ok("plan_director_workflow", director_plan)
        _print_step("director plan", director_plan, ",".join(director_plan.get("domains") or []))

        asset_plan = _post_tool(
            base_url,
            "plan_asset_import_workflow",
            {
                "prompt": "Find a Poly Haven studio prop, import it, organize it, stage it, and capture evidence.",
                "target_object_name": target,
            },
            timeout=args.timeout,
        )
        _require_ok("plan_asset_import_workflow", asset_plan)
        _print_step("asset import plan", asset_plan, asset_plan.get("provider") or "provider pending")

        advanced_plan = _post_tool(
            base_url,
            "plan_advanced_scene_workflow",
            {
                "prompt": "Create a modular wall panel object kit with material presets, Geometry Nodes starters, and a directed animation review path.",
                "target_objects": [target],
            },
            timeout=args.timeout,
        )
        _require_ok("plan_advanced_scene_workflow", advanced_plan)
        _print_step("advanced workflow plan", advanced_plan, ",".join(advanced_plan.get("domains") or []))

        selected = _post_tool(
            base_url,
            "select_objects",
            {"object_names": [target], "active_object_name": target},
            timeout=args.timeout,
        )
        _require_ok("select_objects", selected)

        material = _post_tool(
            base_url,
            "create_shader_material",
            {"name": "Agent Bridge Sweep Screen Glow", "preset": "screen_glow"},
            timeout=args.timeout,
        )
        _require_ok("create_shader_material", material)
        preview_started = True
        _print_step("material preset", material, material.get("preset") or "")

        geometry_nodes = _post_tool(
            base_url,
            "add_geometry_nodes_modifier",
            {
                "name": "Agent Bridge Sweep GN",
                "node_group_name": "Agent Bridge Sweep GN Group",
                "template": "set_position",
                "selected_only": True,
            },
            timeout=args.timeout,
        )
        _require_ok("add_geometry_nodes_modifier", geometry_nodes)
        _print_step("geometry nodes", geometry_nodes, geometry_nodes.get("template") or "")

        object_kit = _post_tool(
            base_url,
            "create_procedural_object_kit",
            {
                "template": "modular_wall_panel",
                "name_prefix": "Agent Bridge Sweep Modular Kit",
                "location": [2.5, 0.0, 0.8],
                "count": 4,
                "radius": 1.0,
                "height": 1.3,
            },
            timeout=args.timeout,
        )
        _require_ok("create_procedural_object_kit", object_kit)
        _print_step("procedural object kit", object_kit, f"{len(object_kit.get('objects') or [])} objects")

        animation = _post_tool(
            base_url,
            "run_animation_workflow",
            {
                "prompt": f"Move {target} across the frame with a directed camera shot.",
                "subject_names": [target],
                "frame_start": 1,
                "frame_end": 36,
                "mode": "full",
                "run_review": False,
                "capture_playblast": False,
                "apply_repairs": False,
            },
            timeout=max(args.timeout, 60.0),
        )
        _require_ok("run_animation_workflow", animation)
        executed = [item.get("tool") for item in animation.get("executed") or []]
        if "create_directed_animation_shot" not in executed:
            raise RuntimeError(f"directed shot helper was not executed: {animation}")
        _print_step("animation workflow", animation, ",".join(executed))

        if not args.skip_viewport:
            viewport = _post_tool(base_url, "capture_viewport", {"max_bytes": 900000}, timeout=args.timeout)
            _require_ok("capture_viewport", viewport)
            visual = viewport.get("visual_context") or {}
            _print_step("viewport capture", viewport, visual.get("resource_uri") or visual.get("path") or "")

        evidence = _post_tool(
            base_url,
            "get_visual_evidence_resources",
            {"include_unavailable": True},
            timeout=args.timeout,
        )
        _require_ok("get_visual_evidence_resources", evidence)
        _print_step("visual evidence inventory", evidence, f"{evidence.get('available_count', 0)} available")

        if preview_started and not args.keep_preview:
            reverted = _post_tool(base_url, "revert_preview", {}, timeout=args.timeout)
            _require_ok("revert_preview", reverted)
            _print_step("preview reverted", reverted)
        elif preview_started:
            print("preview kept pending by --keep-preview")
        return 0
    except (OSError, urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
        if preview_started and not args.keep_preview:
            try:
                reverted = _post_tool(base_url, "revert_preview", {}, timeout=args.timeout)
                if reverted.get("ok"):
                    print("cleanup ok: reverted pending preview after failure", file=sys.stderr)
            except Exception:
                pass
        print(f"live workflow sweep failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
