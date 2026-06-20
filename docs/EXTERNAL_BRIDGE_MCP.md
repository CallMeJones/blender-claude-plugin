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

1. Install and enable the latest `claude_blender-<version>.zip` release asset.
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

The copied config also includes safe metadata in the MCP server `env` block, such as `CLAUDE_BLENDER_ADDON_VERSION`, `CLAUDE_BLENDER_ADDON_SOURCE_HASH`, `CLAUDE_BLENDER_BRIDGE_VERSION`, `CLAUDE_BLENDER_MCP_SERVER_VERSION`, `CLAUDE_BLENDER_MCP_CONFIG_VERSION`, and a short `CLAUDE_BLENDER_MCP_CONFIG_NOTE`. These fields behave like a comment for humans while remaining valid JSON for stricter clients.

## Client Env Auth

For Sketchfab downloads today, put the Sketchfab API token in the MCP server environment. OAuth is a future improvement; the current supported path is `SKETCHFAB_API_TOKEN`, with `BLENDER_AGENT_BRIDGE_SKETCHFAB_API_TOKEN` as a bridge-specific alias.

Claude Desktop-style JSON:

```json
{
  "mcpServers": {
    "blender": {
      "command": "python",
      "args": [
        "C:/path/to/claude_blender/mcp_server.py",
        "--bridge-url",
        "http://127.0.0.1:8765"
      ],
      "env": {
        "SKETCHFAB_API_TOKEN": "your-sketchfab-api-token"
      }
    }
  }
}
```

Codex-style TOML:

```toml
[mcp_servers.blender]
command = "python"
args = ["C:/path/to/claude_blender/mcp_server.py", "--bridge-url", "http://127.0.0.1:8765"]

[mcp_servers.blender.env]
SKETCHFAB_API_TOKEN = "your-sketchfab-api-token"
```

The bridge-specific alias `BLENDER_AGENT_BRIDGE_SKETCHFAB_API_TOKEN` is also accepted.

When a Sketchfab download/import is called through MCP, `mcp_server.py` resolves those environment variables in the Claude/Codex-launched MCP process and forwards the credential to Blender as a redacted per-call tool argument. This is deliberate: Blender itself usually does not inherit the MCP client's environment. For direct HTTP bridge calls that bypass MCP, put the credential in Blender's process environment or pass it as a per-call argument.

Use `blender_bridge_status` to check `mcp_external_asset_auth.sketchfab` and confirm whether the running MCP process actually inherited Sketchfab API-token auth. Use `get_external_asset_cache_diagnostics` to inspect cached assets and the Blender-process auth view.

## MCP Client Refresh

Some clients cache MCP tool lists, server paths, or environment values. After installing a new zip, reloading the add-on, or pressing `Copy MCP Config`, replace the old client config and refresh or restart the MCP client. If `blender_bridge_status` reports a different add-on, bridge, MCP server, config version, or source hash than Blender's sidebar, the client is probably still using stale config. The status payload compares the add-on source hash running in Blender, the MCP server source hash, and the hash embedded in copied MCP config so stale installs are visible from the client.

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
- `start_render_job`
- `get_render_job_status`
- `cancel_render_job`
- `assemble_render_job_video`
- `validate_render_job_output`

Use `blender_tool_catalog` as the primary entry point for the large helper catalog:

- `{"action":"search","query":"camera","limit":8}` returns compact summaries.
- `{"action":"categories"}` returns category, risk, and permission facets.
- `{"action":"schema","name":"add_camera"}` returns one tool's input schema, output schema, and safety annotations.
- `{"action":"invoke","name":"add_camera","arguments":{...}}` validates arguments against the target tool schema before forwarding the call to Blender.

The older `search_blender_tools`, `get_blender_tool_schema`, and `invoke_blender_tool` tools remain as compatibility wrappers for clients that prefer separate operations. Search results are compact by default; set `include_schemas=true` only for compatibility or debugging. For normal agent routing, search first, fetch exactly one schema with `get_blender_tool_schema`, then call `invoke_blender_tool`.

Set `BLENDER_MCP_FULL_TOOL_LIST=1` in the MCP server environment to expose every Blender helper as a top-level MCP tool for legacy clients or debugging. Do not enable it for normal client use unless that client handles large tool lists well.

`tools/list`, `resources/list`, `resources/templates/list`, and `prompts/list` support cursor pagination. Tool definitions include `inputSchema`, `outputSchema`, and risk/permission annotations derived from the bridge contract.

Catalog summaries, schema lookups, and tool-call results may include `guardrail_warnings`. These are advisory, machine-readable nudges for MCP clients; they do not replace Blender-side enforcement. Current warning categories cover synchronous external asset fallbacks, cache cleanup writes, destructive project-file operations, user-confirmed paths, approval-gated scripts, live-preview mutations, long-running synchronous calls, and background job polling.

`draft_script` is a fallback, not the preferred route for common edits. If a client drafts Python for helper-covered work such as transforms, materials, bounded object creation, external asset download/import, project file lifecycle operations, simulation bakes, or render/camera/world settings, the bridge refuses the draft and returns `recommended_tools`. Custom/procedural node, shader, rig, or explicitly stated helper-gap scripts still go through the normal approval path.

Simulation tools are exposed in compact MCP mode so clients do not have to discover them through the generic invoke wrapper. `stage_persistent_simulation_bake` carries machine-readable annotations: `requiresExplicitOneTimeApproval=true`, `trustWindowAutoRunAllowed=false`, `approvalPolicy`, and `recoveryHint`. Its output schema also includes `requires_explicit_one_time_approval`, `trust_window_auto_run_allowed`, `user_action_required`, and `recommended_next_step`. Clients should treat that response as a staged approval state, not as a long-running bake or bridge hang.

Project file tools are human-in-the-loop. For `save_blend_file` save-as/save-copy, `open_blend_file`, and `create_new_blender_project`, clients must ask the user for the target path or use a file picker and set `user_confirmed_path=true`; agents must not invent durable paths. Saving the already-bound active `.blend` may omit `filepath`. `autosave_current_blend_file` accepts no filepath and saves only the already-bound active `.blend` in place.

Recovery paths have the same standard: do not tell the user to open a checkpoint, autosave, or backup `.blend` path unless the client has just verified that exact path exists and is restorable through returned checkpoint metadata, diagnostics, or a filesystem check. If verification is unavailable, report that the path is unverified and ask the user to choose the file instead of inventing one.

`blender_bridge_status` also reports the current external script trust snapshot, including whether tokenless external script runs are allowed, seconds remaining, the runtime expiry timestamp, whether saved scene trust state is stale, and source-hash match/mismatch diagnostics. Some MCP clients cache callable tools aggressively; if a newly added Blender tool is missing, restart or refresh the MCP client after copying the latest config.

For advanced animation, compact MCP mode exposes the animation workflow directly. Use `run_animation_task` when a client has one prompt and should take the default helper-first path. Use `plan_animation_workflow` for read-only manual planning before repair, generation, or arbitrary Python; it creates the animation brief, animation-aware scene context, timing chart, ordered helper/evaluator/repair tool-call payloads, and explicit `draft_script` fallback rules. For common helper-backed requests, `run_animation_workflow` executes the plan through allowlisted helpers, runs structured evaluator review, optionally captures playblast evidence, optionally applies bounded repair operations, and leaves helper edits as a normal live preview. Bounce requests that also ask the subject to get smaller route through `create_progressive_bounce_animation` instead of script fallback. The MCP catalog boosts animation workflow tools for prompts with bounce, jump, keyframe, pose, timing, arcs, settle, squash/stretch, playblast, f-curve, spacing, or contact terms, while `draft_script` is kept as an explicit script/Python fallback. `get_animation_scene_context` remains the lower-level routing tool for likely edit targets, rig-driven meshes, rig control candidates, shape keys, drivers, constraints, physics hints, contact surfaces, camera readiness, subject routing, and recommended deeper inspection tools.

### Animation Routing Regression Prompts

Use these prompts after installing a fresh zip and refreshing the MCP client. During routing tests, revoke external script trust in Blender so early `draft_script` fallback is visible. Trust mode should still not bypass workflow guidance: animation-like `draft_script` calls are refused until an animation workflow has allowed script fallback or the client states an explicit helper gap.

| Prompt | Expected tool path | Pass condition |
| --- | --- | --- |
| `make selected cube bounce twice and get smaller each bounce` | `run_animation_task` -> `run_animation_workflow` -> `create_progressive_bounce_animation` -> review tools | The client uses `run_animation_task` or `run_animation_workflow` before any `draft_script`. |
| `block a jump with anticipation, contact, apex, settle` | `plan_animation_workflow` or `run_animation_task` -> `create_timing_chart` / blocking helpers -> evaluators | The client plans or runs the animation workflow and does not start with Python. |
| `review this animation for spacing/contact` | `run_animation_task` or `plan_animation_workflow` -> evaluator tools -> `review_playblast_against_brief` / `repair_animation_from_findings` when evidence exists | The client uses workflow/evaluator/review helpers before considering script repair, even when the prompt is too ambiguous for generation. |

If a client still calls `draft_script` first for these prompts, refresh or restart the MCP client, press `Copy MCP Config` again, confirm `tools/list` includes `run_animation_task`, and check `blender_bridge_status` for matching add-on, bridge, MCP server, and config versions.

## Resources

Current resources:

- `blender://bridge/status`
- `blender://scene/status`
- `blender://scene/context`
- `blender://tools/catalog`
- `blender://transcript/latest`
- `blender://audit/summary`
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
- `blender://render-thumbnails/latest`
- `blender://render-thumbnails/latest/metadata`
- `blender://render-thumbnails/{thumbnail_id}`
- `blender://render-thumbnails/{thumbnail_id}/metadata`
- `blender://render-jobs/latest/metadata`
- `blender://render-jobs/{job_id}/metadata`
- `blender://render-jobs/{job_id}/frames/{frame}`
- `blender://render-jobs/{job_id}/log`
- `blender://render-jobs/{job_id}/video`

`blender://captures/latest` is scoped to the currently connected Blender bridge and its active project/session. Capture metadata includes the exact `capture_id` resource URIs for repeat reads. By default, saved `.blend` files store captures in a hidden project-local `.claude_blender/captures/<session_id>` folder so separate projects do not overwrite each other. Unsaved or unwritable projects fall back to Blender's extension user-data directory, with `~/.claude_blender/captures/<project_id>/<session_id>` kept only as a non-extension runtime fallback. A custom capture cache preference remains a custom base directory and still gets project/session subfolders.

`blender://tools/catalog` is the resource-friendly compact catalog for eager MCP clients. It contains tool names plus risk and permission metadata, not full schemas. The full contract registry remains readable at `blender://tools/contracts` for debugging, but it is intentionally not listed as a default resource because it is large. `blender://audit/summary` is likewise the compact default audit resource; `blender://audit/latest` remains readable for explicit debugging and returns a bounded recent event window.

`capture_animation_playblast` captures sampled viewport PNG frames across an animation range when Blender is running with an interactive window. It defaults to low-resolution preview evidence capped at 640x360; pass `quality`, `max_width`, or `max_height` only when higher fidelity is needed. It advances the scene frame, updates the view layer, and flushes the viewport draw path where possible before each screenshot; frame metadata includes `captured_scene_frame` as a sanity check against stale captures. The metadata resource lists exact frame URIs so external clients can inspect timing, spacing, staging, arcs, and contact poses without relying only on keyframe data. `review_playblast_against_brief` also derives compact pixel digests, visual-subject interpretation, and frame-to-frame motion deltas from available PNGs, then emits `repair_operations` with executable `tool_call` payloads for deliberate follow-up repairs. Those operations include `target_frames` and `target_frame_range` when a visual finding points to specific sampled frames, missing coverage, weak/cropped subject evidence, or a static-looking frame span. `run_animation_workflow` uses that review path after generation, and `run_animation_repair_loop` can apply a bounded allowlisted subset of repair operations, skip under-specified repairs, and re-run review while preserving the preview commit/revert model. Rig repair findings can route through `get_rigging_details`, `set_rig_custom_property_keyframes`, and then `set_rig_pose_hold` so a client inspects armature controls, holds scalar IK/FK or space-switch properties, and keys a pose-bone hold. For IK/FK-style rigs, repair operations include `metadata.rig_targeting` with the selected controls, roles, regions, score reasons, detected IK/FK or space-switch custom properties, pose-library/action candidates, and planning notes; support/contact rig findings avoid generic object `set_pose_hold` suggestions when rig controls are the better owner. In background/headless mode capture fails soft and reports that an interactive window is required.

`capture_object_inspection_renders` renders bounded diagnostic close-ups of named objects from views such as `front_below`, `underside`, and `side`. It is meant for evidence gathering when the client needs to inspect object details before repair, for example open bays, landing gear, underside geometry, occluded parts, or small model defects. The tool writes PNG artifacts into the project/session capture cache, restores render settings and removes its temporary camera, then returns metadata and image resource URIs under `blender://inspection-renders/{render_id}/...`. `review_inspection_renders_against_brief` can then turn those PNG manifests into visual-detail findings, visual-subject interpretation, and recapture repair operations when required views or readable image evidence are missing.

`render_scene_thumbnail` renders a small PNG from the active scene camera or a named camera, stores metadata in the same project/session capture cache, restores render settings, and exposes the still through `blender://render-thumbnails/{thumbnail_id}` plus metadata resources. Use it when an MCP client needs a client-readable render output or thumbnail without falling back to custom Python.

`start_render_job` is the long-render path for high-resolution animation renders, frame sequences, MP4 quality checks, 1080p/4K previews, and anything likely to exceed the MCP request timeout. It saves a temporary copy of the current `.blend`, starts a background Blender process, and returns a `job_id`, rough estimate, and polling interval immediately. With `quality=auto`, final renders keep final-quality defaults, while playblast/preview/review/draft job names or notes default to a low-resolution preview profile unless the caller explicitly passes `quality`, `resolution_x`, `resolution_y`, or `samples`. Poll `get_render_job_status` until the job reaches `completed`, `failed`, or `cancelled`; status updates include elapsed time, frame rate when frames are available, estimated remaining time, `poll_after_seconds`, frame counts, progress, output paths, log tails, and newest frame resource URI. Logs are available at `blender://render-jobs/{job_id}/log`; exact frames are available at `blender://render-jobs/{job_id}/frames/{frame}`. After a PNG sequence completes, call `assemble_render_job_video` to start a background MP4 assembly pass, then poll `get_render_job_status` again and call `validate_render_job_output` before reporting success. MP4 output is exposed through `blender://render-jobs/{job_id}/video` when small enough for MCP, and always reports a local path in metadata. Use `cancel_render_job` when a tracked job should stop. `render_scene_thumbnail` refuses large synchronous stills by default and returns `recommended_tool: start_render_job`; pass `allow_blocking_render=true` only for an intentional one-off blocking still. `draft_script` warns clients to use this path first when a generated script appears to be a long render or playblast job.

Persistent simulation/cache bakes are separate from render jobs. Before baking, inspect with `get_simulation_details` or `inspect_simulation_bake`, then use `stage_persistent_simulation_bake`. Scripts containing `bpy.ops.fluid.*` or `bpy.ops.ptcache.*` bake/free operators are high risk and require explicit one-time user approval; a session-wide external script trust window must not auto-run them. Prefer small bounded frame ranges, avoid clearing existing caches unless the user explicitly accepts that data loss, and verify checkpoint metadata before asking the user to recover from a checkpoint.

Official Blender Lab parity helpers are exposed as direct tools:

- `get_blend_file_diagnostics` reports save path state, backup files, verified script checkpoint metadata, missing external file paths, linked libraries, and data-block usage summaries.
- `get_workspace_layout` returns workspace/window/screen/area JSON for UI diagnostics.
- `jump_to_workspace` switches the interactive Blender UI to a named workspace and fails soft in background mode.
- `set_viewport_view` switches the first interactive 3D viewport to an axis, camera, or user view and can frame a named object.
- `focus_object_in_viewport` frames a named object in the first 3D viewport and optionally selects it; it also fails soft when no interactive 3D view exists.
- `get_visual_evidence_resources` summarizes latest viewport captures, playblasts, inspection renders, render thumbnails, and render jobs with MCP resource URIs.

External asset helpers are provider-neutral bridge tools. They do not add provider API keys to Blender preferences; Sketchfab download/import takes a per-call `api_token` or reads a Sketchfab-specific token from `SKETCHFAB_API_TOKEN` or `BLENDER_AGENT_BRIDGE_SKETCHFAB_API_TOKEN` in the MCP server environment.

For real MCP clients, the normal route is discovery, `start_external_asset_download`, `get_external_asset_job_status` until completion, `start_external_asset_import_job` for scene import, then `get_external_asset_import_job_status` until completion. Direct provider download/import tools remain available as synchronous fallback/debug paths, but clients should not choose them for ordinary asset-import requests.

- `list_poly_haven_categories` lists Poly Haven category slugs for HDRIs, textures, and models.
- `search_poly_haven_assets` searches Poly Haven's CC0 catalog and returns source/file API URLs.
- `inspect_poly_haven_asset_files` fetches Poly Haven's per-asset file tree with resolutions, formats, sizes, hashes, and dependency includes.
- `search_sketchfab_models` searches Sketchfab public models and returns viewer, author, license, thumbnail, and downloadability metadata.
- `start_external_asset_download` starts a background Poly Haven or Sketchfab cache job and returns a pollable job id.
- `get_external_asset_job_status` reports download progress, cached manifest paths, logs, and completion state.
- `start_external_asset_import_job` queues a completed asset job or cached manifest for Blender main-thread import, then `get_external_asset_import_job_status` reports queued/running/completed state.
- `cancel_external_asset_job`, `cancel_external_asset_import_job`, and `delete_external_asset_job` handle cancellation and job cleanup.
- `get_external_asset_cache_diagnostics` reports cached/imported providers, licenses, source URLs, file counts, cache paths, and imported Blender data-block names.
- `prune_external_asset_cache` removes old or oversized cached assets, with dry-run mode by default.
- `download_poly_haven_asset`, `import_poly_haven_asset`, `download_sketchfab_model`, `import_sketchfab_model`, and `import_external_asset_job_result` are synchronous fallback/debug paths for explicit direct use.

## Prompts

The MCP server exposes prompt templates for common safe workflows: scene inspection, reversible scene changes, advanced animation workflow planning, async external asset import, and approval-gated Python drafts.

## Safety

MCP tools are model-controlled, so the external client must make tool use visible to the user. The Blender bridge preserves the existing safety model:

- Read-only tools inspect scene context and docs.
- Live helper tools mutate the scene through preview rollback.
- Generated arbitrary Python is normally staged with `draft_script` and requires approval inside Blender.
- External `run_approved_script` calls normally include a one-time token minted by the Blender sidebar's `Approve External Run` action. Tokens are short-lived, bound to the current pending script text, and consumed after one call.
- For iterative sessions, the Blender sidebar can also grant external script trust from presets such as 15 minutes, 1 hour, 4 hours, or the current Blender session. While active, `draft_script` automatically runs scripts after staging if static checks pass; if a static-check-passing script is already pending when trust is granted, Blender runs it immediately. External clients may still call `run_approved_script` without `approval_token`, or with an empty token string, for already staged scripts. Blender reruns static checks, refuses blocked scripts, checkpoints when enabled, and records the call in the audit log. Persistent simulation/cache bake and free operators are excluded from this broad trust path and require a fresh one-time approval. Use `Revoke Trust` to end the window early. Trust grants are runtime-only and are cleared on add-on reload, file load, and bridge start.
- The bridge is off until started and binds to localhost only.
- Optional bearer token auth is available through add-on preferences.
- MCP and bridge tool calls are recorded in a local JSONL audit log in Blender's extension user-data directory by default, with `~/.claude_blender/audit.jsonl` kept as a non-extension runtime fallback. Code/token-like arguments are redacted.

## Limitations

- The first MCP server uses stdio only, because it is the most widely supported local MCP transport.
- The localhost bridge is HTTP JSON, not MCP streamable HTTP. MCP clients should launch `mcp_server.py`.
- The default MCP surface is compact because some clients do not handle large dynamic catalogs well. Full top-level exposure is still available with `BLENDER_MCP_FULL_TOOL_LIST=1`.
- External clients cannot bypass Blender's approval gate for generated Python; they can only consume an approval token that the user created inside Blender.
