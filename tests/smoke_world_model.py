"""Smoke tests for deep Blender world-model inspection tools."""

from __future__ import annotations

import json
import os
import sys

import bpy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import agent_tools, context_bundle, tool_dispatcher  # noqa: E402


def _execute(context, name, args=None):
    result = json.loads(tool_dispatcher.execute_tool(context, name, args or {}))
    assert result.get("ok"), f"{name} failed: {result}"
    return result


def _select(context, obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    context.view_layer.objects.active = obj


def _make_curve_object(scene):
    curve = bpy.data.curves.new("Agent Bridge World Curve Data", "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = 0.03
    spline = curve.splines.new("POLY")
    spline.points.add(1)
    spline.points[0].co = (0.0, 0.0, 0.0, 1.0)
    spline.points[1].co = (1.0, 0.0, 1.0, 1.0)
    obj = bpy.data.objects.new("Agent Bridge World Curve", curve)
    scene.collection.objects.link(obj)
    return obj


def _make_text_object(scene):
    text = bpy.data.curves.new("Agent Bridge World Text Data", "FONT")
    text.body = "World model"
    text.align_x = "CENTER"
    obj = bpy.data.objects.new("Agent Bridge World Text", text)
    scene.collection.objects.link(obj)
    return obj


def main():
    claude_blender.register()
    created_objects = []
    created_node_groups = []
    created_actions = []
    try:
        context = bpy.context
        scene = context.scene
        cube = bpy.data.objects["Cube"]
        _select(context, cube)

        material = bpy.data.materials.new("Agent Bridge World Shader")
        material.use_nodes = True
        cube.data.materials.clear()
        cube.data.materials.append(material)

        shape_basis = cube.shape_key_add(name="Basis")
        shape_lift = cube.shape_key_add(name="Lift")
        shape_lift.value = 0.4
        assert shape_basis.name == "Basis"

        gn_group = bpy.data.node_groups.new("Agent Bridge World Geometry Nodes", "GeometryNodeTree")
        gn_modifier = cube.modifiers.new("Agent Bridge World GN", "NODES")
        gn_modifier.node_group = gn_group

        cube["custom_driver_source"] = 1.0
        cube.driver_add('["custom_driver_source"]')

        try:
            bpy.ops.object.particle_system_add()
        except Exception:
            pass
        _select(context, cube)
        bpy.ops.rigidbody.object_add(type="ACTIVE")
        if cube.rigid_body:
            cube.rigid_body.mass = 2.5
            cube.rigid_body.collision_shape = "BOX"
        if scene.rigidbody_world and scene.rigidbody_world.point_cache:
            scene.rigidbody_world.point_cache.frame_start = int(scene.frame_start)
            scene.rigidbody_world.point_cache.frame_end = int(scene.frame_end)

        bpy.ops.object.armature_add(location=(2.0, 0.0, 0.0))
        armature = context.object
        armature.name = "Agent Bridge World Armature"
        if armature.data and armature.data.bones:
            armature.data.bones[0].name = "CTRL_Main"
            armature.data.bones["CTRL_Main"].use_deform = False
        pose_action = None
        pose_bone = armature.pose.bones.get("CTRL_Main") if armature.pose else None
        if pose_bone:
            pose_bone.location.x = 0.0
            pose_bone.keyframe_insert(data_path="location", frame=1)
            pose_bone.location.x = 1.0
            pose_bone.keyframe_insert(data_path="location", frame=12)
            pose_action = armature.animation_data.action if armature.animation_data else None
        if pose_action:
            pose_action.name = "Agent Bridge World Pose Action"
            created_actions.append(pose_action)
        try:
            if pose_action:
                marker = pose_action.pose_markers.new("Ready Pose")
                marker.frame = 1
        except Exception:
            pass
        created_objects.append(armature)
        armature_modifier = cube.modifiers.new("Agent Bridge World Armature Mod", "ARMATURE")
        armature_modifier.object = armature

        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, -0.55))
        ground = context.object
        ground.name = "Agent Bridge World Ground"
        ground.data.name = "Agent Bridge World Ground Mesh"
        ground.scale = (3.0, 3.0, 0.04)
        created_objects.append(ground)
        context.view_layer.update()

        curve_obj = _make_curve_object(scene)
        text_obj = _make_text_object(scene)
        created_objects.extend([curve_obj, text_obj])

        collection = bpy.data.collections.new("Agent Bridge World Collection")
        scene.collection.children.link(collection)
        collection.objects.link(cube)

        scene.use_nodes = True
        if hasattr(scene, "node_tree") and scene.node_tree:
            scene.node_tree.nodes.new(type="CompositorNodeBlur")
        elif hasattr(scene, "compositing_node_group"):
            compositor_group = bpy.data.node_groups.new("Agent Bridge World Compositor", "CompositorNodeTree")
            created_node_groups.append(compositor_group)
            compositor_group.nodes.new(type="CompositorNodeBlur")
            scene.compositing_node_group = compositor_group

        bundle = context_bundle.build_context_bundle(context)
        assert "world_model_summary" in bundle
        assert bundle["world_model_summary"]["shape_key_mesh_count"] >= 1
        assert "get_geometry_nodes_details" in bundle["available_tools"]
        assert "get_animation_scene_context" in bundle["available_tools"]

        tool_names = {tool["name"] for tool in agent_tools.blender_tool_definitions()}
        for expected in {
            "get_animation_scene_context",
            "get_geometry_nodes_details",
            "get_shader_nodes_details",
            "get_rigging_details",
            "get_shape_key_details",
            "get_curve_text_details",
            "get_simulation_details",
            "inspect_simulation_bake",
            "get_collection_layer_details",
            "get_render_camera_compositor_details",
        }:
            assert expected in tool_names, expected

        geometry = _execute(context, "get_geometry_nodes_details", {"object_names": ["Cube"]})
        assert geometry["objects"], geometry
        assert geometry["objects"][0]["geometry_node_modifiers"], geometry

        shader = _execute(context, "get_shader_nodes_details", {"material_names": ["Agent Bridge World Shader"]})
        assert shader["materials"][0]["node_tree"], shader

        rigging = _execute(context, "get_rigging_details", {"object_names": ["Agent Bridge World Armature", "Cube"]})
        assert any(item["type"] == "ARMATURE" for item in rigging["objects"]), rigging
        armature_details = next(item for item in rigging["objects"] if item["type"] == "ARMATURE")
        assert armature_details["armature"]["control_hints"]["control_candidate_count"] >= 1, rigging
        assert armature_details["armature"]["pose_library_candidates"], rigging

        animation_context = _execute(
            context,
            "get_animation_scene_context",
            {"object_names": ["Cube", "Agent Bridge World Armature", "Agent Bridge World Ground"]},
        )
        by_name = {item["name"]: item for item in animation_context["objects"]}
        assert by_name["Cube"]["rig"]["likely_rig_driven"] is True, animation_context
        assert by_name["Cube"]["suggested_primary_animation_target"] == "rig_controls", animation_context
        assert by_name["Cube"]["animation_routing_confidence"] == "high", animation_context
        assert by_name["Cube"]["rig"]["control_targets"][0]["control_candidate_count"] >= 1, animation_context
        assert by_name["Agent Bridge World Armature"]["rig_control_hints"]["control_candidate_count"] >= 1, animation_context
        assert by_name["Agent Bridge World Armature"]["object_animation"]["channel_summary"]["has_pose_bone_keys"], animation_context
        assert by_name["Agent Bridge World Armature"]["pose_library_candidates"], animation_context
        assert "get_rigging_details" in by_name["Cube"]["recommended_detail_tools"], animation_context
        assert "get_shape_key_details" in by_name["Cube"]["recommended_detail_tools"], animation_context
        assert "get_simulation_details" in animation_context["recommended_next_tools"], animation_context
        assert animation_context["summary"]["rig_driven_object_count"] >= 2, animation_context
        assert animation_context["summary"]["rig_control_candidate_count"] >= 1, animation_context
        assert animation_context["summary"]["pose_library_candidate_count"] >= 1, animation_context
        assert animation_context["summary"]["contact_surface_candidate_count"] >= 1, animation_context
        assert animation_context["contact_surface_candidates"][0]["name"] == "Agent Bridge World Ground", animation_context
        assert any(route["object"] == "Cube" and route["rig_control_candidate_count"] >= 1 and route["animation_routing_confidence"] == "high" for route in animation_context["subject_routing"]), animation_context
        assert animation_context["summary"]["active_camera"] == "Camera", animation_context

        shape_keys = _execute(context, "get_shape_key_details", {"object_names": ["Cube"]})
        assert shape_keys["objects"], shape_keys
        assert any(key["name"] == "Lift" for key in shape_keys["objects"][0]["key_blocks"]), shape_keys

        curves = _execute(context, "get_curve_text_details", {"object_names": ["Agent Bridge World Curve", "Agent Bridge World Text"]})
        assert len(curves["objects"]) == 2, curves

        simulations = _execute(context, "get_simulation_details", {"object_names": ["Cube"]})
        assert "objects" in simulations, simulations
        assert simulations["scene"]["rigid_body_world"], simulations
        assert simulations["summary"]["rigid_body_object_count"] >= 1, simulations
        assert simulations["summary"]["particle_system_count"] >= 1, simulations
        assert simulations["summary"]["unbaked_cache_count"] >= 1, simulations
        cube_simulation = next(item for item in simulations["objects"] if item["name"] == "Cube")
        assert cube_simulation["rigid_body"]["mass"] == 2.5, simulations
        assert cube_simulation["particle_systems"][0]["point_cache"], simulations
        assert "compare_animation_to_brief" in simulations["recommended_next_tools"], simulations

        frame_before_simulation_inspect = scene.frame_current
        simulation_bake = _execute(
            context,
            "inspect_simulation_bake",
            {"object_names": ["Cube"], "frame_start": 1, "frame_end": 24, "sample_count": 4},
        )
        assert simulation_bake["mode"] == "sample_evaluated_state", simulation_bake
        assert simulation_bake["persistent_bake_performed"] is False, simulation_bake
        assert simulation_bake["sampled_frames"][0] == 1, simulation_bake
        assert simulation_bake["sampled_frames"][-1] == 24, simulation_bake
        assert simulation_bake["object_names"] == ["Cube"], simulation_bake
        assert simulation_bake["frame_samples"], simulation_bake
        assert simulation_bake["frame_samples"][0]["objects"][0]["name"] == "Cube", simulation_bake
        assert simulation_bake["object_summaries"][0]["sample_count"] == len(simulation_bake["sampled_frames"]), simulation_bake
        assert simulation_bake["simulation_details"]["summary"]["rigid_body_object_count"] >= 1, simulation_bake
        assert scene.frame_current == frame_before_simulation_inspect, simulation_bake

        bpy.ops.mesh.primitive_cube_add(size=0.25, location=(3.0, 3.0, 0.0))
        plain_object = context.object
        plain_object.name = "Agent Bridge Plain Simulation Inspect"
        try:
            plain_simulation_bake = _execute(
                context,
                "inspect_simulation_bake",
                {"object_names": ["Agent Bridge Plain Simulation Inspect"], "frame_start": 1, "frame_end": 3, "sample_count": 2},
            )
            assert plain_simulation_bake["object_count"] == 0, plain_simulation_bake
            assert plain_simulation_bake["object_names"] == [], plain_simulation_bake
            assert plain_simulation_bake["non_simulation_object_names"] == ["Agent Bridge Plain Simulation Inspect"], plain_simulation_bake
            assert plain_simulation_bake["simulation_details"]["objects"] == [], plain_simulation_bake
        finally:
            bpy.data.objects.remove(plain_object, do_unlink=True)

        collections = _execute(context, "get_collection_layer_details", {"max_depth": 3})
        assert collections["scene_collection"], collections
        assert any(item["name"] == "Agent Bridge World Collection" for item in collections["collections"]), collections

        render = _execute(context, "get_render_camera_compositor_details", {})
        assert render["render"]["engine"], render
        assert render["compositor"]["use_nodes"] is True, render

        print("smoke_world_model: ok")
    finally:
        for obj in created_objects:
            if obj.name in bpy.data.objects:
                bpy.data.objects.remove(obj, do_unlink=True)
        for name in ["Agent Bridge World Curve Data", "Agent Bridge World Text Data"]:
            data = bpy.data.curves.get(name)
            if data:
                bpy.data.curves.remove(data)
        for name in ["Agent Bridge World Shader"]:
            material = bpy.data.materials.get(name)
            if material:
                bpy.data.materials.remove(material)
        for group in created_node_groups:
            if group.name in bpy.data.node_groups:
                bpy.data.node_groups.remove(group)
        for action in created_actions:
            if action.name in bpy.data.actions:
                bpy.data.actions.remove(action)
        for name in ["Agent Bridge World Geometry Nodes"]:
            group = bpy.data.node_groups.get(name)
            if group:
                bpy.data.node_groups.remove(group)
        for name in ["Agent Bridge World Ground Mesh"]:
            mesh = bpy.data.meshes.get(name)
            if mesh:
                bpy.data.meshes.remove(mesh)
        collection = bpy.data.collections.get("Agent Bridge World Collection")
        if collection:
            bpy.data.collections.remove(collection)
        claude_blender.unregister()


if __name__ == "__main__":
    main()
