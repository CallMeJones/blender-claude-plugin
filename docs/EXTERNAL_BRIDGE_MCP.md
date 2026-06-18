# External Bridge And MCP

## Goal

Blender Agent Bridge exposes the live Blender scene to external agents through a localhost bridge and a stdio MCP server. This is the Codex/Claude Code style path: Blender keeps direct `bpy` access, while external clients discover tools/resources and call them over a standard protocol.

## Architecture

```text
MCP client
  -> stdio JSON-RPC
  -> addon/claude_blender/mcp_server.py
  -> HTTP JSON on 127.0.0.1
  -> bridge_server.py inside Blender
  -> tool_dispatcher.py / context_bundle.py / bpy
```

The add-on owns all Blender reads/writes. The MCP server is a small stdlib Python process that forwards requests to Blender's local bridge.

## Start The Bridge

1. Install and enable the latest `claude_blender-0.1.0.zip`.
2. Open the add-on sidebar in the 3D View.
3. In `External Bridge`, press `Start`.
4. Optional: set `Bridge Token` in add-on preferences before starting.
5. Press `Copy MCP Config` and paste it into a client that supports local MCP servers.

The bridge binds only to `127.0.0.1`. It does not listen on your LAN.

## MCP Config Shape

The copied config looks like this:

```json
{
  "mcpServers": {
    "blender": {
      "command": "python",
      "args": [
        "C:/path/to/claude_blender/mcp_server.py",
        "--bridge-url",
        "http://127.0.0.1:8765"
      ]
    }
  }
}
```

If you set a bridge token, the copied config includes:

```json
{
  "env": {
    "BLENDER_BRIDGE_TOKEN": "your-token"
  }
}
```

The copied config also includes safe metadata in the MCP server `env` block, such as `CLAUDE_BLENDER_ADDON_VERSION`, `CLAUDE_BLENDER_BRIDGE_VERSION`, `CLAUDE_BLENDER_MCP_SERVER_VERSION`, `CLAUDE_BLENDER_MCP_CONFIG_VERSION`, and a short `CLAUDE_BLENDER_MCP_CONFIG_NOTE`. These fields behave like a comment for humans while remaining valid JSON for stricter clients.

## MCP Client Refresh

Some clients cache MCP tool lists, server paths, or environment values. After installing a new zip, reloading the add-on, or pressing `Copy MCP Config`, replace the old client config and refresh or restart the MCP client. If `blender_bridge_status` reports a different add-on, bridge, MCP server, or config version than Blender's sidebar, the client is probably still using stale config.

## Bridge HTTP Endpoints

These are implementation details used by the MCP server:

- `GET /health`
- `GET /tools`
- `POST /tool`
- `GET /resources`
- `GET /resource?uri=...`
- `GET /contracts`

Example direct bridge call:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8765/tool -Method Post -ContentType application/json -Body '{"name":"list_scene_objects","arguments":{"max_objects":10}}'
```

## MCP Surface

The stdio MCP server implements:

- `initialize`
- `tools/list`
- `tools/call`
- `resources/list`
- `resources/read`
- `resources/templates/list`
- `prompts/list`
- `prompts/get`
- `logging/setLevel`
- `ping`

By default it exposes a compact, client-friendly tool surface:

- `blender_bridge_status`
- `blender_tool_catalog`
- `search_blender_tools`
- `get_blender_tool_schema`
- `invoke_blender_tool`
- `list_scene_objects`
- `plan_animation_workflow`
- `run_animation_workflow`
- `run_animation_task`

Use `blender_tool_catalog` as the primary entry point for the large helper catalog:

- `{"action":"search","query":"camera","limit":8}` returns compact summaries.
- `{"action":"categories"}` returns category, risk, and permission facets.
- `{"action":"schema","name":"add_camera"}` returns one tool's input schema, output schema, and safety annotations.
- `{"action":"invoke","name":"add_camera","arguments":{...}}` validates arguments against the target tool schema before forwarding the call to Blender.

The older `search_blender_tools`, `get_blender_tool_schema`, and `invoke_blender_tool` tools remain as compatibility wrappers for clients that prefer separate operations.

Set `BLENDER_MCP_FULL_TOOL_LIST=1` in the MCP server environment to expose every Blender helper as a top-level MCP tool for legacy clients or debugging.

`tools/list`, `resources/list`, `resources/templates/list`, and `prompts/list` support cursor pagination. Tool definitions include `inputSchema`, `outputSchema`, and risk/permission annotations derived from the bridge contract.

`blender_bridge_status` also reports the current external script trust snapshot, including whether tokenless external script runs are allowed, seconds remaining, the runtime expiry timestamp, and whether saved scene trust state is stale. Some MCP clients cache callable tools aggressively; if a newly added Blender tool is missing, restart or refresh the MCP client after copying the latest config.

For advanced animation, compact MCP mode exposes the animation workflow directly. Use `run_animation_task` when a client has one prompt and should take the default helper-first path. Use `plan_animation_workflow` for read-only manual planning before repair, generation, or arbitrary Python; it creates the animation brief, animation-aware scene context, timing chart, ordered helper/evaluator/repair tool-call payloads, and explicit `draft_script` fallback rules. For common helper-backed requests, `run_animation_workflow` executes the plan through allowlisted helpers, runs structured evaluator review, optionally captures playblast evidence, optionally applies bounded repair operations, and leaves helper edits as a normal live preview. Bounce requests that also ask the subject to get smaller route through `create_progressive_bounce_animation` instead of script fallback. The MCP catalog boosts animation workflow tools for prompts with bounce, jump, keyframe, pose, timing, arcs, settle, squash/stretch, playblast, f-curve, spacing, or contact terms, while `draft_script` is kept as an explicit script/Python fallback. `get_animation_scene_context` remains the lower-level routing tool for likely edit targets, rig-driven meshes, rig control candidates, shape keys, drivers, constraints, physics hints, contact surfaces, camera readiness, subject routing, and recommended deeper inspection tools.

### Animation Routing Regression Prompts

Use these prompts after installing a fresh zip and refreshing the MCP client. During routing tests, revoke external script trust in Blender so early `draft_script` fallback is visible. Trust mode should still not bypass workflow guidance: animation-like `draft_script` calls are refused until an animation workflow has allowed script fallback or the client states an explicit helper gap.

| Prompt | Expected tool path | Pass condition |
| --- | --- | --- |
| `make selected cube bounce twice and get smaller each bounce` | `run_animation_task` -> `run_animation_workflow` -> `create_progressive_bounce_animation` -> review tools | The client uses `run_animation_task` or `run_animation_workflow` before any `draft_script`. |
| `block a jump with anticipation, contact, apex, settle` | `plan_animation_workflow` or `run_animation_task` -> `create_timing_chart` / blocking helpers -> evaluators | The client plans or runs the animation workflow and does not start with Python. |
| `review this animation for spacing/contact` | `plan_animation_workflow` or evaluator tools -> `review_playblast_against_brief` / `repair_animation_from_findings` when evidence exists | The client uses workflow/evaluator/review helpers before considering script repair. |

If a client still calls `draft_script` first for these prompts, refresh or restart the MCP client, press `Copy MCP Config` again, confirm `tools/list` includes `run_animation_task`, and check `blender_bridge_status` for matching add-on, bridge, MCP server, and config versions.

## Resources

Current resources:

- `blender://bridge/status`
- `blender://scene/status`
- `blender://scene/context`
- `blender://tools/contracts`
- `blender://transcript/latest`
- `blender://audit/latest`
- `blender://captures/latest`
- `blender://captures/latest/metadata`
- `blender://captures/{capture_id}`
- `blender://captures/{capture_id}/metadata`
- `blender://playblasts/latest/metadata`
- `blender://playblasts/{playblast_id}/metadata`
- `blender://playblasts/{playblast_id}/frames/{frame}`
- `blender://inspection-renders/latest/metadata`
- `blender://inspection-renders/{render_id}/metadata`
- `blender://inspection-renders/{render_id}/images/{image_id}`

`blender://captures/latest` is scoped to the currently connected Blender bridge and its active project/session. Capture metadata includes the exact `capture_id` resource URIs for repeat reads. By default, saved `.blend` files store captures in a hidden project-local `.claude_blender/captures/<session_id>` folder so separate projects do not overwrite each other. Unsaved or unwritable projects fall back to `~/.claude_blender/captures/<project_id>/<session_id>`. A custom capture cache preference remains a custom base directory and still gets project/session subfolders.

`capture_animation_playblast` captures sampled viewport PNG frames across an animation range when Blender is running with an interactive window. The metadata resource lists exact frame URIs so external clients can inspect timing, spacing, staging, arcs, and contact poses without relying only on keyframe data. `review_playblast_against_brief` also derives compact pixel digests, visual-subject interpretation, and frame-to-frame motion deltas from available PNGs, then emits `repair_operations` with executable `tool_call` payloads for deliberate follow-up repairs. Those operations include `target_frames` and `target_frame_range` when a visual finding points to specific sampled frames, missing coverage, weak/cropped subject evidence, or a static-looking frame span. `run_animation_workflow` uses that review path after generation, and `run_animation_repair_loop` can apply a bounded allowlisted subset of repair operations, skip under-specified repairs, and re-run review while preserving the preview commit/revert model. Rig repair findings can route through `get_rigging_details` and then `set_rig_pose_hold` so a client inspects armature controls before keying a pose-bone hold. In background/headless mode capture fails soft and reports that an interactive window is required.

`capture_object_inspection_renders` renders bounded diagnostic close-ups of named objects from views such as `front_below`, `underside`, and `side`. It is meant for evidence gathering when the client needs to inspect object details before repair, for example open bays, landing gear, underside geometry, occluded parts, or small model defects. The tool writes PNG artifacts into the project/session capture cache, restores render settings and removes its temporary camera, then returns metadata and image resource URIs under `blender://inspection-renders/{render_id}/...`. `review_inspection_renders_against_brief` can then turn those PNG manifests into visual-detail findings, visual-subject interpretation, and recapture repair operations when required views or readable image evidence are missing.

## Prompts

The MCP server exposes prompt templates for common safe workflows: scene inspection, reversible scene changes, advanced animation workflow planning, and approval-gated Python drafts.

## Safety

MCP tools are model-controlled, so the external client must make tool use visible to the user. The Blender bridge preserves the existing safety model:

- Read-only tools inspect scene context and docs.
- Live helper tools mutate the scene through preview rollback.
- Generated arbitrary Python is normally staged with `draft_script` and requires approval inside Blender.
- External `run_approved_script` calls normally include a one-time token minted by the Blender sidebar's `Approve External Run` action. Tokens are short-lived, bound to the current pending script text, and consumed after one call.
- For iterative sessions, the Blender sidebar can also grant external script trust from presets such as 15 minutes, 1 hour, 4 hours, or the current Blender session. While active, `draft_script` automatically runs scripts after staging if static checks pass; if a static-check-passing script is already pending when trust is granted, Blender runs it immediately. External clients may still call `run_approved_script` without `approval_token`, or with an empty token string, for already staged scripts. Blender reruns static checks, refuses blocked scripts, checkpoints when enabled, and records the call in the audit log. Use `Revoke Trust` to end the window early. Trust grants are runtime-only and are cleared on add-on reload, file load, and bridge start.
- The bridge is off until started and binds to localhost only.
- Optional bearer token auth is available through add-on preferences.
- MCP and bridge tool calls are recorded in a local JSONL audit log at `~/.claude_blender/audit.jsonl` by default, with code/token-like arguments redacted.

## Limitations

- The first MCP server uses stdio only, because it is the most widely supported local MCP transport.
- The localhost bridge is HTTP JSON, not MCP streamable HTTP. MCP clients should launch `mcp_server.py`.
- The default MCP surface is compact because some clients do not handle large dynamic catalogs well. Full top-level exposure is still available with `BLENDER_MCP_FULL_TOOL_LIST=1`.
- External clients cannot bypass Blender's approval gate for generated Python; they can only consume an approval token that the user created inside Blender.
