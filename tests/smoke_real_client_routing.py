"""Fixture-driven routing checks for real MCP client prompt classes."""

from __future__ import annotations

import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import agent_tools  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "addon", "claude_blender"))
import mcp_server  # noqa: E402


class OfflineBridge:
    def get(self, _path, params=None):
        raise RuntimeError("offline routing smoke uses static tool contracts")


ROUTING_FIXTURES = [
    {
        "id": "animation_helper_first",
        "prompt": "Make the selected cube bounce twice, get smaller each bounce, capture a playblast, review it, repair issues, and leave it as a preview.",
        "must_select": ["plan_animation_workflow", "run_animation_workflow", "capture_animation_playblast", "review_playblast_against_brief", "run_animation_repair_loop"],
        "must_not_select": ["draft_script"],
        "search": "bounce twice get smaller playblast review repair",
        "search_before": [("run_animation_workflow", "draft_script"), ("plan_animation_workflow", "draft_script")],
    },
    {
        "id": "visual_inspection_helper_first",
        "prompt": "Inspect underside close-up renders of the aircraft landing gear and repair visual-detail issues.",
        "must_select": ["capture_object_inspection_renders", "review_inspection_renders_against_brief", "repair_animation_from_findings"],
        "must_not_select": ["draft_script"],
        "search": "underside close-up inspection renders landing gear visual detail repair",
        "search_before": [("capture_object_inspection_renders", "draft_script")],
    },
    {
        "id": "procedural_creation_helper_first",
        "prompt": "Create a hard-surface modular wall panel kit with geometry node starters, bevels, material presets, and production organization.",
        "must_select": ["plan_advanced_scene_workflow", "create_procedural_object_kit", "add_geometry_nodes_modifier", "create_shader_material", "organize_scene_for_production"],
        "must_not_select": ["draft_script"],
        "search": "hard surface modular wall panel geometry nodes material preset object kit",
        "search_before": [("plan_advanced_scene_workflow", "draft_script"), ("create_procedural_object_kit", "draft_script")],
    },
    {
        "id": "asset_import_async_path",
        "prompt": "Find a Poly Haven model, download it, import it, organize it, make a studio presentation, and capture viewport evidence.",
        "must_select": ["plan_asset_import_workflow", "start_external_asset_download", "get_external_asset_job_status", "start_external_asset_import_job", "get_external_asset_import_job_status"],
        "must_not_select": ["draft_script"],
        "search": "poly haven asset import organize studio presentation workflow",
        "search_before": [("plan_asset_import_workflow", "download_poly_haven_asset"), ("start_external_asset_download", "download_poly_haven_asset")],
    },
    {
        "id": "director_orchestration",
        "prompt": "Director workflow: import an asset, build a product scene, animate a reveal, review evidence, repair, and ask me to commit or revert.",
        "must_select": ["plan_director_workflow", "plan_asset_import_workflow", "plan_advanced_scene_workflow", "run_animation_workflow", "capture_viewport"],
        "must_not_select": ["draft_script"],
        "search": "director workflow import asset product scene animate reveal evidence commit revert",
        "search_before": [("plan_director_workflow", "draft_script"), ("plan_asset_import_workflow", "draft_script")],
    },
    {
        "id": "explicit_custom_script_allowed_after_gap",
        "prompt": "Draft a custom Python script for a bespoke geometry-node network that helper tools cannot express.",
        "must_select": ["draft_script", "get_geometry_nodes_details", "plan_advanced_scene_workflow"],
        "must_not_select": [],
        "search": "custom python geometry node network helpers cannot express",
        "search_before": [("plan_advanced_scene_workflow", "draft_script")],
    },
]


def _selected_names(prompt):
    tools, meta = agent_tools.select_blender_tool_definitions(prompt, context_bundle=None)
    return {tool["name"] for tool in tools}, meta


def _search_names(server, query, limit=16):
    result = server._search_blender_tools({"query": query, "limit": limit})
    structured = result["structuredContent"]
    return [tool["name"] for tool in structured["tools"]], structured


def _assert_before(names, earlier, later, fixture_id):
    assert earlier in names, (fixture_id, earlier, names)
    if later in names:
        assert names.index(earlier) < names.index(later), (fixture_id, earlier, later, names)


def main():
    server = mcp_server.BlenderMCPServer(OfflineBridge())
    for fixture in ROUTING_FIXTURES:
        selected, meta = _selected_names(fixture["prompt"])
        for name in fixture["must_select"]:
            assert name in selected, (fixture["id"], name, meta)
        for name in fixture["must_not_select"]:
            assert name not in selected, (fixture["id"], name, meta)

        search_names, search = _search_names(server, fixture["search"])
        for earlier, later in fixture["search_before"]:
            _assert_before(search_names, earlier, later, fixture["id"])
        assert search["count"] > 0, (fixture["id"], search)
    print("smoke_real_client_routing: ok")


if __name__ == "__main__":
    main()
