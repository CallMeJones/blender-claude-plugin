"""Blender background smoke test for progressive agent memory."""

from __future__ import annotations

import os
import sys

import bpy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import agent_memory, context_bundle  # noqa: E402


def main():
    claude_blender.register()
    context = bpy.context
    scene = context.scene
    state = scene.claude_blender

    agent_memory.clear_memory(scene)
    assert agent_memory.MEMORY_TEXT_NAME in bpy.data.texts
    assert "cleared" in state.agent_memory_status.lower()

    bundle = context_bundle.build_context_bundle(context)
    agent_memory.add_to_bundle(bundle, context)
    assert bundle["agent_memory"]["enabled"] is True
    assert "No prior agent memory" in bundle["agent_memory"]["memory"]

    agent_memory.record_turn(
        scene,
        user_prompt="Build a sci-fi pedestal scene",
        assistant_response="Created the pedestal base; blue accent lights remain.",
        context_summary="2 objects, 0 selected",
    )
    memory = agent_memory.get_memory(scene)
    assert "Build a sci-fi pedestal scene" in memory
    assert "blue accent lights remain" in memory

    followup = context_bundle.build_context_bundle(context)
    agent_memory.add_to_bundle(followup, context)
    assert "blue accent lights remain" in followup["agent_memory"]["memory"]

    state.agent_memory_enabled = False
    disabled = context_bundle.build_context_bundle(context)
    agent_memory.add_to_bundle(disabled, context)
    assert disabled["agent_memory"]["enabled"] is False

    state.agent_memory_enabled = True
    agent_memory.clear_memory(scene)
    claude_blender.unregister()
    print("smoke_agent_memory: ok")


if __name__ == "__main__":
    main()
