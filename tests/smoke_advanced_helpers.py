"""Blender background smoke test for advanced safe helper tools."""

from __future__ import annotations

import json
import os
import sys

import bpy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import agent_tools, context_bundle, live_preview, tool_dispatcher  # noqa: E402


ADVANCED_TOOLS = {
    "plan_advanced_scene_workflow",
    "plan_asset_import_workflow",
    "plan_director_workflow",
    "get_2d_animation_details",
    "create_storyboard_panels",
    "create_2d_cutout_layer",
    "apply_procedural_array_stack",
    "create_procedural_object_kit",
    "create_camera_dolly_animation",
    "create_directed_animation_shot",
    "add_cloth_simulation_to_selected",
    "create_shader_material",
    "add_geometry_nodes_modifier",
    "create_shape_key",
    "animate_shape_key",
    "create_text_object",
    "create_curve_path",
    "add_particle_system_to_selected",
    "create_basic_armature",
    "add_copy_transform_constraint",
    "set_render_settings",
    "set_camera_settings",
    "set_world_background",
}


def _execute(context, name, args=None):
    result = json.loads(tool_dispatcher.execute_tool(context, name, args or {}))
    assert result.get("ok"), f"{name} failed: {result}"
    return result


def _select_object(context, obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    context.view_layer.objects.active = obj


def _snapshot(scene, cube, camera):
    world_color = tuple(scene.world.color) if scene.world else None
    return {
        "objects": set(bpy.data.objects.keys()),
        "curves": set(bpy.data.curves.keys()),
        "materials": set(bpy.data.materials.keys()),
        "node_groups": set(bpy.data.node_groups.keys()),
        "armatures": set(bpy.data.armatures.keys()),
        "particles": set(bpy.data.particles.keys()),
        "actions": set(bpy.data.actions.keys()),
        "cube_modifiers": [modifier.name for modifier in cube.modifiers],
        "cube_shape_keys": [block.name for block in cube.data.shape_keys.key_blocks] if cube.data.shape_keys else [],
        "camera_constraints": len(camera.constraints),
        "camera_lens": camera.data.lens,
        "camera_dof": camera.data.dof.use_dof,
        "resolution": (scene.render.resolution_x, scene.render.resolution_y),
        "fps": scene.render.fps,
        "frame_range": (scene.frame_start, scene.frame_end),
        "film_transparent": scene.render.film_transparent,
        "world": scene.world.name if scene.world else None,
        "world_color": world_color,
    }


def _material_topology(material):
    node_tree = getattr(material, "node_tree", None) if material else None
    if not node_tree:
        return {"has_node_tree": False, "nodes": [], "links": []}
    return {
        "has_node_tree": True,
        "nodes": sorted(node.name for node in node_tree.nodes),
        "links": sorted(
            (
                link.from_node.name,
                getattr(link.from_socket, "identifier", link.from_socket.name),
                link.to_node.name,
                getattr(link.to_socket, "identifier", link.to_socket.name),
            )
            for link in node_tree.links
        ),
    }


def main():
    claude_blender.register()
    context = bpy.context
    scene = context.scene
    cube = bpy.data.objects["Cube"]
    camera = bpy.data.objects["Camera"]
    existing_material = bpy.data.materials.new("Agent Bridge Existing Node Material")
    node_tree = existing_material.node_tree
    assert node_tree is not None, "New Blender materials should expose a shader node tree"
    nodes = node_tree.nodes
    for node in list(nodes):
        nodes.remove(node)
    diffuse = nodes.new(type="ShaderNodeBsdfDiffuse")
    output = nodes.new(type="ShaderNodeOutputMaterial")
    node_tree.links.new(diffuse.outputs["BSDF"], output.inputs["Surface"])
    cube.data.materials.clear()
    cube.data.materials.append(existing_material)
    existing_topology = _material_topology(existing_material)
    initial = _snapshot(scene, cube, camera)

    try:
        bundle = context_bundle.build_context_bundle(context)
        assert ADVANCED_TOOLS.issubset(set(bundle["available_tools"]))
        tool_names = {tool["name"] for tool in agent_tools.blender_tool_definitions()}
        assert ADVANCED_TOOLS.issubset(tool_names)

        assert live_preview.current_transaction() is None
        invalid_dolly = json.loads(tool_dispatcher.execute_tool(context, "create_camera_dolly_animation", {"camera_name": "Cube"}))
        assert invalid_dolly["ok"] is False, invalid_dolly
        assert "not a camera" in invalid_dolly["message"], invalid_dolly
        assert live_preview.current_transaction() is None, invalid_dolly

        workflow = _execute(
            context,
            "plan_advanced_scene_workflow",
            {"prompt": "Plan advanced 2D storyboard, procedural 3D, cloth simulation, and camera animation helpers."},
        )
        assert {"two_d_storyboard", "procedural_3d", "advanced_animation", "simulation_setup"}.intersection(set(workflow["domains"]))
        asset_plan = _execute(
            context,
            "plan_asset_import_workflow",
            {"prompt": "Find a Poly Haven product prop, import it, organize it, stage it, and capture evidence."},
        )
        asset_phase_names = [phase["name"] for phase in asset_plan["phases"]]
        assert asset_phase_names == ["discover", "select_asset", "download", "import", "present"], asset_plan
        assert asset_plan["provider"] == "poly_haven", asset_plan
        assert asset_plan["provider_selection_required"] is False, asset_plan
        assert asset_plan["asset_selection_required"] is True, asset_plan
        assert asset_plan["selection_required"] is True, asset_plan
        asset_tool_names = [call["name"] for phase in asset_plan["phases"] for call in phase["tool_calls"]]
        assert "start_external_asset_download" not in asset_tool_names, asset_plan
        assert "start_external_asset_import_job" not in asset_tool_names, asset_plan
        assert "inspect_poly_haven_asset_files" not in asset_tool_names, asset_plan
        assert "<poly_haven_asset_id>" not in str(asset_plan), asset_plan
        assert asset_plan["phases"][-1]["tool_calls"] == [], asset_plan
        concrete_asset_plan = _execute(
            context,
            "plan_asset_import_workflow",
            {
                "prompt": "Import the selected Poly Haven model and stage it.",
                "provider": "poly_haven",
                "asset_id": "agent_bridge_test_asset",
            },
        )
        concrete_phase_names = [phase["name"] for phase in concrete_asset_plan["phases"]]
        assert concrete_phase_names == ["discover", "download", "import", "present"], concrete_asset_plan
        assert concrete_asset_plan["asset_selection_required"] is False, concrete_asset_plan
        assert concrete_asset_plan["selection_required"] is False, concrete_asset_plan
        concrete_download = next(call for phase in concrete_asset_plan["phases"] for call in phase["tool_calls"] if call["name"] == "start_external_asset_download")
        assert concrete_download["input"]["asset_id"] == "agent_bridge_test_asset", concrete_asset_plan
        assert not concrete_download["input"]["uid"], concrete_asset_plan
        ambiguous_asset_plan = _execute(
            context,
            "plan_asset_import_workflow",
            {"prompt": "Find a product prop asset, import it, organize it, stage it, and capture evidence."},
        )
        ambiguous_phase_names = [phase["name"] for phase in ambiguous_asset_plan["phases"]]
        assert ambiguous_phase_names == ["discover", "select_asset", "download", "import", "present"], ambiguous_asset_plan
        assert ambiguous_asset_plan["provider"] == "", ambiguous_asset_plan
        assert ambiguous_asset_plan["provider_selection_required"] is True, ambiguous_asset_plan
        assert ambiguous_asset_plan["asset_selection_required"] is False, ambiguous_asset_plan
        assert ambiguous_asset_plan["selection_required"] is True, ambiguous_asset_plan
        ambiguous_tool_names = [
            call["name"]
            for phase in ambiguous_asset_plan["phases"]
            for call in phase["tool_calls"]
        ]
        assert "search_poly_haven_assets" in ambiguous_tool_names, ambiguous_asset_plan
        assert "search_sketchfab_models" in ambiguous_tool_names, ambiguous_asset_plan
        assert "start_external_asset_download" not in ambiguous_tool_names, ambiguous_asset_plan
        assert ambiguous_asset_plan["phases"][-1]["tool_calls"] == [], ambiguous_asset_plan

        director_plan = _execute(
            context,
            "plan_director_workflow",
            {
                "prompt": "Director workflow: import an asset, create a modular wall panel kit, animate a reveal, review evidence, and ask before commit.",
                "target_objects": ["Cube"],
            },
        )
        director_tool_names = [call["name"] for call in director_plan["next_tool_calls"]]
        assert "plan_asset_import_workflow" in director_tool_names, director_plan
        assert "create_procedural_object_kit" in director_tool_names, director_plan
        assert "run_animation_workflow" in director_tool_names, director_plan
        assert "commit_preview" not in director_tool_names, director_plan
        assert "revert_preview" not in director_tool_names, director_plan
        director_decision_names = [option["tool_call"]["name"] for option in director_plan["preview_decision_options"]]
        assert director_decision_names == ["commit_preview", "revert_preview"], director_plan
        gn_plan_call = next(call for call in director_plan["next_tool_calls"] if call["name"] == "add_geometry_nodes_modifier")
        assert gn_plan_call["input"]["name"], director_plan
        assert gn_plan_call["input"]["node_group_name"], director_plan
        assert director_plan["preview_policy"]["commit_only_on_user_request"] is True, director_plan
        details = _execute(context, "get_2d_animation_details", {"max_items": 12})
        assert "recommended_tools" in details

        board = _execute(
            context,
            "create_storyboard_panels",
            {
                "panel_count": 2,
                "columns": 2,
                "name_prefix": "Agent Bridge Advanced Board",
                "frame_start": 1,
                "frame_step": 12,
            },
        )
        assert len(board["panels"]) == 2
        assert board["camera"] in bpy.data.objects

        cutout = _execute(
            context,
            "create_2d_cutout_layer",
            {
                "name": "Agent Bridge Advanced Cutout",
                "location": [0.0, -0.2, 0.0],
                "size": [0.8, 0.5],
                "frame_start": 1,
                "frame_end": 24,
                "location_end": [0.5, -0.2, 0.25],
                "text": "Layer",
            },
        )
        assert cutout["object"] in bpy.data.objects
        assert cutout["action"] in bpy.data.actions

        _select_object(context, cube)
        material = _execute(
            context,
            "create_shader_material",
            {
                "name": "Agent Bridge Advanced Chrome",
                "base_color": [0.2, 0.45, 1.0, 1.0],
                "metallic": 0.8,
                "roughness": 0.22,
                "emission_color": [0.0, 0.25, 1.0, 1.0],
                "emission_strength": 0.2,
            },
        )
        assert material["material"] in bpy.data.materials
        assert cube.material_slots[0].material.name == material["material"]
        glass = _execute(
            context,
            "create_shader_material",
            {
                "name": "Agent Bridge Advanced Glass Preset",
                "preset": "clear_glass",
            },
        )
        assert glass["preset"] == "clear_glass", glass
        glass_material = bpy.data.materials[glass["material"]]
        assert round(float(glass_material.diffuse_color[3]), 2) == 0.32, tuple(glass_material.diffuse_color)
        assert cube.material_slots[0].material.name == glass["material"]
        glow = _execute(
            context,
            "create_shader_material",
            {
                "name": "Agent Bridge Advanced Screen Glow Preset",
                "preset": "screen_glow",
            },
        )
        assert glow["preset"] == "screen_glow", glow
        glow_material = bpy.data.materials[glow["material"]]
        glow_principled = next(node for node in glow_material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
        assert round(float(glow_principled.inputs["Emission Strength"].default_value), 1) == 2.4, glow["material"]
        bpy.ops.object.select_all(action="DESELECT")
        unassigned_material = _execute(
            context,
            "create_shader_material",
            {
                "name": "Agent Bridge Advanced Unassigned Preset",
                "preset": "matte_ceramic",
            },
        )
        assert unassigned_material["preview_change_report"]["targets"] == [unassigned_material["material"]], unassigned_material
        _select_object(context, cube)
        existing_update = _execute(
            context,
            "create_shader_material",
            {
                "name": existing_material.name,
                "base_color": [0.7, 0.2, 0.2, 1.0],
                "metallic": 0.4,
                "roughness": 0.35,
            },
        )
        assert existing_update["material"] == existing_material.name
        shader_snapshot = live_preview.current_transaction()["before_state"][f"material:{existing_material.name}:shader"]
        assert "Principled BSDF" not in shader_snapshot["node_names"], shader_snapshot
        assert _material_topology(existing_material) != existing_topology

        geometry_nodes = _execute(
            context,
            "add_geometry_nodes_modifier",
            {"name": "Agent Bridge Advanced GN", "node_group_name": "Agent Bridge Advanced GN Group", "template": "transform"},
        )
        assert geometry_nodes["node_group"] in bpy.data.node_groups
        assert geometry_nodes["template"] == "transform", geometry_nodes
        assert not geometry_nodes["warnings"], geometry_nodes
        assert bpy.data.node_groups[geometry_nodes["node_group"]].nodes.get("Agent Bridge Transform Geometry")
        assert cube.modifiers.get("Agent Bridge Advanced GN")
        set_position_nodes = _execute(
            context,
            "add_geometry_nodes_modifier",
            {"name": "Agent Bridge Advanced GN Set Position", "node_group_name": "Agent Bridge Advanced GN Set Position Group", "template": "set_position"},
        )
        assert set_position_nodes["template"] == "set_position", set_position_nodes
        assert bpy.data.node_groups[set_position_nodes["node_group"]].nodes.get("Agent Bridge Set Position")
        subdivide_nodes = _execute(
            context,
            "add_geometry_nodes_modifier",
            {"name": "Agent Bridge Advanced GN Subdivide", "node_group_name": "Agent Bridge Advanced GN Subdivide Group", "template": "subdivide_mesh"},
        )
        assert subdivide_nodes["template"] == "subdivide_mesh", subdivide_nodes
        assert bpy.data.node_groups[subdivide_nodes["node_group"]].nodes.get("Agent Bridge Subdivide Mesh")

        procedural = _execute(
            context,
            "apply_procedural_array_stack",
            {"object_names": ["Cube"], "selected_only": False, "count": 3, "name_prefix": "Agent Bridge Advanced Procedural"},
        )
        assert procedural["objects"][0]["object"] == "Cube"
        assert cube.modifiers.get("Agent Bridge Advanced Procedural Array")

        shape_key = _execute(context, "create_shape_key", {"object_name": "Cube", "key_name": "Agent Bridge Bulge", "value": 0.25})
        assert shape_key["shape_key"] in cube.data.shape_keys.key_blocks
        _execute(
            context,
            "animate_shape_key",
            {
                "object_name": "Cube",
                "key_name": "Agent Bridge Bulge",
                "frame_start": 1,
                "frame_end": 40,
                "value_start": 0.0,
                "value_end": 1.0,
            },
        )
        assert cube.data.shape_keys.animation_data and cube.data.shape_keys.animation_data.action

        particles = _execute(
            context,
            "add_particle_system_to_selected",
            {"name": "Agent Bridge Advanced Particles", "count": 12, "frame_start": 1, "frame_end": 20, "lifetime": 30},
        )
        assert particles["objects"] == ["Cube"]
        assert cube.modifiers.get("Agent Bridge Advanced Particles")

        cloth = _execute(
            context,
            "add_cloth_simulation_to_selected",
            {"object_names": ["Cube"], "selected_only": False, "name": "Agent Bridge Advanced Cloth", "quality": 3},
        )
        assert cloth["objects"][0]["modifier"] == "Agent Bridge Advanced Cloth"
        assert cube.modifiers.get("Agent Bridge Advanced Cloth")

        text = _execute(
            context,
            "create_text_object",
            {
                "name": "Agent Bridge Advanced Label",
                "body": "Advanced",
                "location": [0.0, -2.0, 1.5],
                "rotation": [1.5708, 0.0, 0.0],
                "scale": [1.0, 1.0, 1.0],
                "size": 0.5,
                "color": [0.8, 0.95, 1.0, 1.0],
            },
        )
        assert bpy.data.objects[text["object"]].type == "FONT"

        curve = _execute(
            context,
            "create_curve_path",
            {
                "name": "Agent Bridge Advanced Path",
                "points": [[-1.0, 0.0, 0.0], [0.0, 0.6, 1.0], [1.0, 0.0, 0.0]],
                "bevel_depth": 0.03,
                "color": [0.0, 0.6, 1.0, 1.0],
            },
        )
        assert bpy.data.objects[curve["object"]].type == "CURVE"

        armature = _execute(
            context,
            "create_basic_armature",
            {"name": "Agent Bridge Advanced Armature", "location": [2.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0]},
        )
        assert bpy.data.objects[armature["object"]].type == "ARMATURE"

        _select_object(context, camera)
        _execute(
            context,
            "add_copy_transform_constraint",
            {"target_name": "Cube", "constraint_type": "COPY_LOCATION", "name": "Agent Bridge Advanced Copy Location"},
        )
        assert len(camera.constraints) == initial["camera_constraints"] + 1

        dolly = _execute(
            context,
            "create_camera_dolly_animation",
            {
                "camera_name": "Camera",
                "target_name": "Cube",
                "frame_start": 1,
                "frame_end": 36,
                "start_location": [0.0, -5.0, 2.0],
                "end_location": [0.0, -3.5, 1.4],
                "lens_start": 35,
                "lens_end": 55,
            },
        )
        assert dolly["camera"] == "Camera"
        assert dolly["action"] in bpy.data.actions

        object_kit = _execute(
            context,
            "create_procedural_object_kit",
            {
                "template": "radial_array",
                "name_prefix": "Agent Bridge Smoke Kit",
                "location": [3.0, 0.0, 0.0],
                "count": 6,
                "radius": 1.4,
                "height": 0.7,
            },
        )
        assert object_kit["template"] == "radial_array", object_kit
        assert len(object_kit["objects"]) >= 7, object_kit
        assert bpy.data.objects[object_kit["objects"][0]].type == "MESH"

        mechanical_kit = _execute(
            context,
            "create_procedural_object_kit",
            {
                "template": "mechanical_joint",
                "name_prefix": "Agent Bridge Mechanical Kit",
                "location": [-3.0, 0.0, 0.0],
                "count": 5,
                "radius": 1.2,
                "height": 0.8,
            },
        )
        assert mechanical_kit["template"] == "mechanical_joint", mechanical_kit
        assert any("Bearing" in name for name in mechanical_kit["objects"]), mechanical_kit
        assert any("Bolt" in name for name in mechanical_kit["objects"]), mechanical_kit

        control_panel = _execute(
            context,
            "create_procedural_object_kit",
            {
                "template": "control_panel",
                "name_prefix": "Agent Bridge Control Panel Kit",
                "location": [0.0, 3.0, 0.0],
                "count": 6,
                "radius": 1.1,
                "height": 1.5,
            },
        )
        assert control_panel["template"] == "control_panel", control_panel
        assert any("Display Screen" in name for name in control_panel["objects"]), control_panel
        assert any("Control Knob" in name for name in control_panel["objects"]), control_panel

        modular_panel = _execute(
            context,
            "create_procedural_object_kit",
            {
                "template": "modular_wall_panel",
                "name_prefix": "Agent Bridge Modular Wall Kit",
                "location": [3.0, 3.0, 0.0],
                "count": 4,
                "radius": 1.0,
                "height": 1.4,
            },
        )
        assert modular_panel["template"] == "modular_wall_panel", modular_panel
        assert any("Wall Panel Body" in name for name in modular_panel["objects"]), modular_panel
        assert any("Inset Bay" in name for name in modular_panel["objects"]), modular_panel

        pipe_run = _execute(
            context,
            "create_procedural_object_kit",
            {
                "template": "pipe_run",
                "name_prefix": "Agent Bridge Pipe Run Kit",
                "location": [-3.0, 3.0, 0.0],
                "count": 4,
                "radius": 1.0,
                "height": 1.0,
            },
        )
        assert pipe_run["template"] == "pipe_run", pipe_run
        assert any("Pipe 01" in name for name in pipe_run["objects"]), pipe_run
        assert any("Pipe Support" in name for name in pipe_run["objects"]), pipe_run

        directed = _execute(
            context,
            "create_directed_animation_shot",
            {
                "shot_type": "path_slide",
                "object_names": ["Cube"],
                "selected_only": False,
                "frame_start": 1,
                "frame_end": 36,
                "travel_axis": "X",
                "travel_distance": 1.25,
                "camera_name": "Camera",
            },
        )
        assert directed["shot_type"] == "path_slide", directed
        assert "Cube" in directed["objects"], directed
        assert directed["camera"] == "Camera", directed

        crane = _execute(
            context,
            "create_directed_animation_shot",
            {
                "shot_type": "crane_reveal",
                "object_names": ["Cube"],
                "selected_only": False,
                "frame_start": 1,
                "frame_end": 48,
                "camera_name": "Camera",
            },
        )
        assert crane["shot_type"] == "crane_reveal", crane
        assert crane["subjects"] == ["Cube"], crane
        assert crane["objects"] == [], crane
        assert crane["camera_action"] in bpy.data.actions, crane

        truck = _execute(
            context,
            "create_directed_animation_shot",
            {
                "shot_type": "truck_slide",
                "object_names": ["Cube"],
                "selected_only": False,
                "frame_start": 1,
                "frame_end": 48,
                "travel_axis": "X",
                "travel_distance": 1.6,
                "camera_name": "Camera",
            },
        )
        assert truck["shot_type"] == "truck_slide", truck
        assert truck["subjects"] == ["Cube"], truck
        assert truck["objects"] == [], truck
        assert truck["camera_action"] in bpy.data.actions, truck

        invalid_directed = json.loads(
            tool_dispatcher.execute_tool(
                context,
                "create_directed_animation_shot",
                {"camera_name": "Cube", "object_names": ["Cube"], "selected_only": False},
            )
        )
        assert invalid_directed["ok"] is False, invalid_directed
        assert scene.claude_blender.pending_preview is True, "invalid directed shot must not clear existing preview"

        _execute(context, "set_render_settings", {"resolution": [1280, 720], "fps": 30, "frame_start": 1, "frame_end": 48, "film_transparent": True})
        assert scene.render.resolution_x == 1280 and scene.render.resolution_y == 720
        assert scene.render.fps == 30
        assert scene.frame_end == 48

        _execute(context, "set_camera_settings", {"camera_name": "Camera", "lens": 70, "dof_enabled": True, "focus_object_name": "Cube", "aperture_fstop": 2.8})
        assert camera.data.lens == 70
        assert camera.data.dof.use_dof
        assert camera.data.dof.focus_object == cube

        _execute(context, "set_world_background", {"color": [0.02, 0.03, 0.06]})
        assert tuple(round(float(component), 4) for component in scene.world.color) == (0.02, 0.03, 0.06)

        _execute(context, "revert_preview", {})
        final = _snapshot(scene, cube, camera)
        assert final == initial, {"initial": initial, "final": final}
        restored_topology = _material_topology(existing_material)
        assert restored_topology == existing_topology, {
            "expected": existing_topology,
            "actual": restored_topology,
        }
        print("smoke_advanced_helpers: ok")
    finally:
        claude_blender.unregister()


if __name__ == "__main__":
    main()
