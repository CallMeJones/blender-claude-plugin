"""Blender background smoke test for approval-gated script execution."""

from __future__ import annotations

import os
import json
import shutil
import sys
import tempfile
import time

import bpy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import (  # noqa: E402
    anthropic_client,
    bridge_protocol,
    bridge_server,
    build_info,
    script_runner,
    tool_dispatcher,
)


OBJECT_NAME = "Claude Script Smoke Object"
MESH_NAME = "Claude Script Smoke Mesh"


def _cleanup():
    obj = bpy.data.objects.get(OBJECT_NAME)
    if obj is not None:
        bpy.data.objects.remove(obj, do_unlink=True)
    mesh = bpy.data.meshes.get(MESH_NAME)
    if mesh is not None:
        bpy.data.meshes.remove(mesh)


def main():
    checkpoint_dir = tempfile.mkdtemp(prefix="claude-blender-checkpoints-")
    old_audit_path = os.environ.get("CLAUDE_BLENDER_AUDIT_LOG")
    audit_path = os.path.join(checkpoint_dir, "audit.jsonl")
    os.environ["CLAUDE_BLENDER_AUDIT_LOG"] = audit_path
    claude_blender.register()
    try:
        context = bpy.context
        state = context.scene.claude_blender
        _cleanup()

        copied = bpy.ops.claude_blender.copy_mcp_config()
        assert "FINISHED" in copied, copied
        clipboard = context.window_manager.clipboard.strip()
        if clipboard:
            copied_config = json.loads(clipboard)
        else:
            copied_config = build_info.mcp_config(f"http://127.0.0.1:{bridge_server.DEFAULT_PORT}")
        server_config = copied_config["mcpServers"]["blender"]
        assert server_config["command"] == "python", server_config
        assert server_config["args"][0].endswith("mcp_server.py"), server_config
        assert "--bridge-url" in server_config["args"], server_config
        env = server_config["env"]
        assert env["CLAUDE_BLENDER_ADDON_ID"] == build_info.ADDON_ID, env
        assert env["CLAUDE_BLENDER_ADDON_VERSION"] == build_info.ADDON_VERSION, env
        assert env["CLAUDE_BLENDER_BRIDGE_VERSION"] == bridge_protocol.BRIDGE_VERSION, env
        assert env["CLAUDE_BLENDER_MCP_SERVER_VERSION"] == build_info.MCP_SERVER_VERSION, env
        assert env["CLAUDE_BLENDER_MCP_CONFIG_VERSION"] == build_info.MCP_CONFIG_VERSION, env
        assert "MCP client" in env["CLAUDE_BLENDER_MCP_CONFIG_NOTE"], env
        assert "BLENDER_BRIDGE_TOKEN" not in env, env
        assert f"MCP config v{build_info.MCP_CONFIG_VERSION}" in state.status, state.status

        internal_tool_names = {tool["name"] for tool in anthropic_client.blender_tool_definitions()}
        assert "run_approved_script" not in internal_tool_names
        bridge_tools = {tool["name"]: tool for tool in bridge_server._tool_definitions()}
        external_tool = bridge_tools["run_approved_script"]
        assert "approval_token" not in external_tool["inputSchema"].get("required", []), external_tool
        assert "minLength" not in external_tool["inputSchema"]["properties"]["approval_token"], external_tool
        assert external_tool["annotations"]["requiresApproval"] is True, external_tool

        blocked = script_runner.stage_script(
            context,
            intent="Try a blocked filesystem operation",
            expected_changes="No scene changes should occur",
            risk_level="high",
            target_objects=[],
            code="import os\nos.remove('example.blend')",
        )
        assert blocked["ok"], blocked
        assert blocked["analysis"]["blocked"], blocked
        assert state.pending_script
        assert state.pending_script_blocked
        assert state.pending_script_issues

        blocked_run = script_runner.run_pending_script(context, checkpoint_enabled=False)
        assert not blocked_run["ok"], blocked_run
        assert state.pending_script_blocked

        rejected = script_runner.reject_pending_script(context)
        assert rejected["ok"], rejected
        assert not state.pending_script

        missing = script_runner.stage_script(
            context,
            intent="Missing code",
            expected_changes="No changes",
            risk_level="low",
            target_objects=[],
            code="",
        )
        assert not missing["ok"], missing
        assert missing["missing_code"], missing
        assert "code field" in missing["message"], missing

        failing = script_runner.stage_script(
            context,
            intent="Trigger a runtime failure",
            expected_changes="No scene changes should remain",
            risk_level="low",
            target_objects=[],
            code="raise RuntimeError('intentional smoke failure')",
        )
        assert failing["analysis"]["ok"], failing
        failed_run = script_runner.run_pending_script(context, checkpoint_enabled=False)
        assert not failed_run["ok"], failed_run
        assert state.pending_script
        assert state.pending_script_status == "Script failed"
        assert "RuntimeError" in state.last_script_error_summary
        repair_context = script_runner.repair_context_text(context)
        assert "intentional smoke failure" in repair_context
        assert "Checkpoint status:" in repair_context
        assert "Prepare a corrected draft only" in repair_context
        assert script_runner.SCRIPT_FAILURE_PROMPT_NAME in bpy.data.texts

        safe_code = f"""
import bpy

mesh = bpy.data.meshes.new("{MESH_NAME}")
mesh.from_pydata(
    [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
    [],
    [(0, 1, 2)],
)
mesh.update()
obj = bpy.data.objects.new("{OBJECT_NAME}", mesh)
scene.collection.objects.link(obj)
obj.location = (1.0, 2.0, 3.0)
print("created", obj.name)
"""
        staged = script_runner.stage_script(
            context,
            intent="Create a simple smoke-test mesh object",
            expected_changes="A triangle mesh object appears at location 1, 2, 3",
            risk_level="low",
            target_objects=[OBJECT_NAME],
            code=safe_code,
        )
        assert staged["ok"], staged
        assert staged["analysis"]["ok"], staged
        assert state.pending_script
        assert not state.pending_script_blocked

        rejected = script_runner.reject_pending_script(context)
        assert rejected["ok"], rejected
        alternate_field = json.loads(
            tool_dispatcher.execute_tool(
                context,
                "draft_script",
                {
                    "intent": "Stage from alternate field",
                    "expected_changes": "A harmless print script is staged",
                    "risk_level": "low",
                    "script": "print('alternate field staged')",
                },
            )
        )
        assert alternate_field["ok"], alternate_field
        assert state.pending_script
        assert not state.pending_script_blocked

        rejected = script_runner.reject_pending_script(context)
        assert rejected["ok"], rejected
        staged = script_runner.stage_script(
            context,
            intent="Create a simple smoke-test mesh object",
            expected_changes="A triangle mesh object appears at location 1, 2, 3",
            risk_level="low",
            target_objects=[OBJECT_NAME],
            code=safe_code,
        )
        assert staged["ok"], staged
        assert staged["analysis"]["ok"], staged
        assert state.pending_script
        assert not state.pending_script_blocked

        missing_external = script_runner.run_externally_approved_script(context, "", checkpoint_enabled=False)
        assert not missing_external["ok"], missing_external
        assert "approval token" in missing_external["message"], missing_external

        trusted = script_runner.approve_external_script_trust_window(context, ttl_seconds=900)
        assert trusted["ok"], trusted
        assert trusted["ttl_seconds"] == 900, trusted
        assert script_runner.external_script_trust_active(context, state=state)
        trust_snapshot = script_runner.external_script_trust_snapshot(context, state=state)
        assert trust_snapshot["active"], trust_snapshot
        assert trust_snapshot["can_run_without_token"], trust_snapshot
        assert 1 <= trust_snapshot["seconds_remaining"] <= 900, trust_snapshot
        assert "remaining" in trust_snapshot["status"], trust_snapshot
        bridge_status = bridge_server._scene_status()
        assert bridge_status["external_script_trust"] is True, bridge_status
        assert bridge_status["external_script_trust_can_run_without_token"] is True, bridge_status
        assert 1 <= bridge_status["external_script_trust_seconds_remaining"] <= 900, bridge_status
        assert "MCP client" in bridge_status["mcp_client_refresh_hint"], bridge_status

        script_runner._runtime_external_trust_expires_at = time.time() - 1
        assert not script_runner.external_script_trust_active(context, state=state)
        expired_snapshot = script_runner.external_script_trust_snapshot(context, state=state)
        assert expired_snapshot["expired"], expired_snapshot
        assert expired_snapshot["seconds_remaining"] == 0, expired_snapshot
        assert "expired" in script_runner.external_script_trust_status(context, state=state).lower()
        expired = script_runner.expire_external_script_trust_if_needed(context, state=state)
        assert expired
        assert state.external_script_trust_status == script_runner.EXTERNAL_TRUST_EXPIRED_STATUS
        post_expire_snapshot = script_runner.external_script_trust_snapshot(context, state=state)
        assert post_expire_snapshot["expired"], post_expire_snapshot
        assert not post_expire_snapshot["active"], post_expire_snapshot
        assert post_expire_snapshot["status"] == script_runner.EXTERNAL_TRUST_EXPIRED_STATUS, post_expire_snapshot
        post_expire_bridge_status = bridge_server._scene_status()
        assert post_expire_bridge_status["external_script_trust"] is False, post_expire_bridge_status
        assert post_expire_bridge_status["external_script_trust_status"] == script_runner.EXTERNAL_TRUST_EXPIRED_STATUS, post_expire_bridge_status

        cleared_expired = script_runner.clear_external_script_trust_for_all_scenes()
        assert cleared_expired >= 1
        state.external_script_trust_status = "External script trust active: 15m 00s remaining"
        state.external_script_trust_expires_at = f"{time.time() + 900:.6f}"
        assert not script_runner.external_script_trust_active(context, state=state)
        stale_snapshot = script_runner.external_script_trust_snapshot(context, state=state)
        assert stale_snapshot["stale_scene_state"], stale_snapshot
        assert stale_snapshot["status"] == script_runner.NO_EXTERNAL_TRUST_STATUS
        assert script_runner.external_script_trust_status(context, state=state) == script_runner.NO_EXTERNAL_TRUST_STATUS
        cleared_stale = script_runner.clear_external_script_trust_for_all_scenes()
        assert cleared_stale >= 1

        session_trusted = script_runner.approve_external_script_trust_window(context, session=True)
        assert session_trusted["ok"], session_trusted
        assert session_trusted["session"], session_trusted
        session_snapshot = script_runner.external_script_trust_snapshot(context, state=state)
        assert session_snapshot["active"], session_snapshot
        assert session_snapshot["session"], session_snapshot
        assert session_snapshot["seconds_remaining"] == 0, session_snapshot
        assert "session" in session_snapshot["status"].lower(), session_snapshot
        session_bridge_status = bridge_server._scene_status()
        assert session_bridge_status["external_script_trust"] is True, session_bridge_status
        assert session_bridge_status["external_script_trust_session"] is True, session_bridge_status
        session_script = script_runner.stage_script(
            context,
            intent="Run through session trust",
            expected_changes="A scene custom property is set",
            risk_level="low",
            target_objects=[],
            code="scene['claude_session_trust_smoke'] = 'ok'\nprint(scene['claude_session_trust_smoke'])",
        )
        assert session_script["ok"], session_script
        session_result = script_runner.run_externally_approved_script(context, "", checkpoint_enabled=False)
        assert session_result["ok"], session_result
        assert context.scene["claude_session_trust_smoke"] == "ok"
        assert script_runner.external_script_trust_active(context, state=state)
        session_revoked = script_runner.revoke_external_script_trust_window(context)
        assert session_revoked["ok"], session_revoked
        assert not script_runner.external_script_trust_active(context, state=state)

        staged = script_runner.stage_script(
            context,
            intent="Create a harmless object during the timed trust window",
            expected_changes=f"Creates mesh object {OBJECT_NAME}",
            risk_level="low",
            target_objects=[OBJECT_NAME],
            code=safe_code,
        )
        assert staged["ok"], staged
        assert staged["analysis"]["ok"], staged
        assert state.pending_script
        assert not state.pending_script_blocked

        trusted = script_runner.approve_external_script_trust_window(context, ttl_seconds=900)
        assert trusted["ok"], trusted
        assert script_runner.external_script_trust_active(context, state=state)
        bad_token_during_trust = script_runner.run_externally_approved_script(
            context,
            "wrong-token",
            checkpoint_enabled=False,
        )
        assert not bad_token_during_trust["ok"], bad_token_during_trust
        assert script_runner.external_script_trust_active(context, state=state)
        trusted_result = script_runner.run_externally_approved_script(context, "", checkpoint_enabled=False)
        assert trusted_result["ok"], trusted_result
        assert OBJECT_NAME in bpy.data.objects
        assert not state.pending_script
        assert script_runner.external_script_trust_active(context, state=state)
        _cleanup()

        trusted_blocked = script_runner.stage_script(
            context,
            intent="Try blocked code during an active trust window",
            expected_changes="No scene changes should occur",
            risk_level="high",
            target_objects=[],
            code="import os\nos.remove('still_blocked.blend')",
        )
        assert trusted_blocked["ok"], trusted_blocked
        trusted_blocked_run = script_runner.run_externally_approved_script(context, "", checkpoint_enabled=False)
        assert not trusted_blocked_run["ok"], trusted_blocked_run
        assert "blocked" in trusted_blocked_run["message"].lower(), trusted_blocked_run
        assert script_runner.external_script_trust_active(context, state=state)
        rejected = script_runner.reject_pending_script(context)
        assert rejected["ok"], rejected

        trusted_second = script_runner.stage_script(
            context,
            intent="Run a second script through the trust window",
            expected_changes="A scene custom property is set",
            risk_level="low",
            target_objects=[],
            code="scene['claude_trust_smoke'] = 'second'\nprint(scene['claude_trust_smoke'])",
        )
        assert trusted_second["ok"], trusted_second
        trusted_second_result = script_runner.run_externally_approved_script(context, "", checkpoint_enabled=False)
        assert trusted_second_result["ok"], trusted_second_result
        assert context.scene["claude_trust_smoke"] == "second"
        assert script_runner.external_script_trust_active(context, state=state)

        revoked = script_runner.revoke_external_script_trust_window(context)
        assert revoked["ok"], revoked
        assert not script_runner.external_script_trust_active(context, state=state)
        with open(audit_path, "r", encoding="utf-8") as handle:
            trust_events = [
                json.loads(line)
                for line in handle
                if line.strip() and '"event":"external_script_trust"' in line
            ]
        trust_actions = {event.get("action") for event in trust_events}
        assert {"grant", "expire", "revoke"}.issubset(trust_actions), trust_events
        needs_approval = script_runner.stage_script(
            context,
            intent="Require explicit approval after trust revocation",
            expected_changes="No scene changes should occur without approval",
            risk_level="low",
            target_objects=[],
            code="print('approval required')",
        )
        assert needs_approval["ok"], needs_approval
        missing_after_revoke = script_runner.run_externally_approved_script(context, "", checkpoint_enabled=False)
        assert not missing_after_revoke["ok"], missing_after_revoke
        assert "trust window" in missing_after_revoke["message"], missing_after_revoke

        approval = script_runner.approve_pending_script_for_external_run(context, ttl_seconds=60)
        assert approval["ok"], approval
        assert approval["approval_token"], approval
        assert approval["approval_token"] not in state.pending_script_external_approval_hash
        assert approval["approval_token"] not in state.pending_script_external_approval_status

        wrong_token = script_runner.run_externally_approved_script(context, "wrong-token", checkpoint_enabled=False)
        assert not wrong_token["ok"], wrong_token
        assert "did not match" in wrong_token["message"], wrong_token
        assert state.pending_script

        text = bpy.data.texts[state.pending_script_text_name]
        text.write("\n# edited after external approval")
        stale = script_runner.run_externally_approved_script(
            context,
            approval["approval_token"],
            checkpoint_enabled=False,
        )
        assert not stale["ok"], stale
        assert "stale" in stale["message"], stale

        staged = script_runner.stage_script(
            context,
            intent="Create a simple smoke-test mesh object",
            expected_changes="A triangle mesh object appears at location 1, 2, 3",
            risk_level="low",
            target_objects=[OBJECT_NAME],
            code=safe_code,
        )
        assert staged["ok"], staged
        approval = script_runner.approve_pending_script_for_external_run(context, ttl_seconds=60)
        assert approval["ok"], approval

        result = script_runner.run_externally_approved_script(
            context,
            approval["approval_token"],
            checkpoint_enabled=True,
            checkpoint_dir=checkpoint_dir,
        )
        assert result["ok"], result
        assert result["checkpoint"]["ok"], result
        assert os.path.exists(result["checkpoint"]["path"]), result
        assert state.last_checkpoint_path == result["checkpoint"]["path"]
        assert result["checkpoint"]["exists"], result
        assert result["checkpoint"]["restorable"], result
        assert result["checkpoint"]["size_bytes"] > 0, result
        assert OBJECT_NAME in bpy.data.objects
        assert tuple(round(value, 4) for value in bpy.data.objects[OBJECT_NAME].location) == (1.0, 2.0, 3.0)
        assert script_runner.SCRIPT_LOG_NAME in bpy.data.texts
        assert not state.pending_script
        assert not state.pending_script_external_approval_hash
        replay = script_runner.run_externally_approved_script(
            context,
            approval["approval_token"],
            checkpoint_enabled=False,
        )
        assert not replay["ok"], replay

        non_checkpoint_path = os.path.join(checkpoint_dir, "manual.blend")
        with open(non_checkpoint_path, "wb") as handle:
            handle.write(b"not really a blend")
        refused = script_runner.restore_checkpoint(context, non_checkpoint_path)
        assert not refused["ok"], refused
        assert not refused["checkpoint"]["ok"], refused
        assert refused["checkpoint"]["exists"], refused
        assert not refused["checkpoint"]["restorable"], refused

        restored = script_runner.restore_checkpoint(context, result["checkpoint"]["path"])
        assert restored["ok"], restored
        assert restored["checkpoint"]["exists"], restored
        assert restored["checkpoint"]["restorable"], restored
        context = bpy.context
        state = context.scene.claude_blender
        assert OBJECT_NAME not in bpy.data.objects, restored
        assert state.last_checkpoint_path == result["checkpoint"]["path"], state.last_checkpoint_path
        assert state.last_checkpoint_restored_path == result["checkpoint"]["path"], state.last_checkpoint_restored_path
        assert "Checkpoint restored" in state.last_checkpoint_restored_status, state.last_checkpoint_restored_status

        _cleanup()
        claude_blender.unregister()
        print("smoke_script_runner: ok")
    finally:
        if old_audit_path is None:
            os.environ.pop("CLAUDE_BLENDER_AUDIT_LOG", None)
        else:
            os.environ["CLAUDE_BLENDER_AUDIT_LOG"] = old_audit_path
        shutil.rmtree(checkpoint_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
