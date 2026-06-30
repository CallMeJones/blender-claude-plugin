# Comprehensive Testing Guide

This guide is the runbook for asking Codex to test Blender Agent Bridge end to end. It is designed to cover every feature family, every bridge path, and every tool surface, then drive failures into focused fixes and reruns.

Current project snapshot, checked on 2026-06-20:

- Extension: `Blender Agent Bridge`, manifest id `claude_blender`; version comes from `addon/claude_blender/blender_manifest.toml` and is checked against `build_info.py` and `CHANGELOG.md`.
- Minimum Blender: `5.0.0`.
- Local Blender detected on this workstation: `C:\Program Files\Blender Foundation\Blender 5.1\blender.exe`.
- Dispatcher inventory: 144 tool functions in `addon/claude_blender/tool_dispatcher.py`.
- Normal agent catalog inventory: 143 tool definitions in `addon/claude_blender/agent_tools.py`.
- Intentional catalog difference: `run_approved_script` is a dispatcher path for external approval/trust execution, but it is not exposed in the normal agent helper catalog.
- Fast baseline verified on 2026-06-20: `compileall`, pure-Python smoke tests, extension repository smoke, external assets catalog smoke, script analysis, and stdio MCP smoke passed.

## How To Ask Codex To Run This

Use these prompts when you want a specific level of testing.

```text
Run Phase 0 and Phase 1 from docs/TESTING_GUIDE.md. Fix any failures and rerun the failing checks.
```

```text
Run the full Blender-background suite from docs/TESTING_GUIDE.md. If anything fails, preserve logs, fix the issue, and rerun the owner test plus the fast baseline.
```

```text
Run the MCP live-bridge tests from docs/TESTING_GUIDE.md against the installed extension zip. Verify compact catalog mode and full tool-list mode.
```

```text
Run a comprehensive tool sweep for the feature group I changed. Check schema, validation, happy path, preview rollback, MCP catalog discovery, resources, and audit log behavior.
```

```text
Prepare a release verification pass using docs/TESTING_GUIDE.md and docs/RELEASE.md. Include clean install, MCP smoke, zip validation, Pages repository artifacts, and secret/artifact scans.
```

## Test Principles

- Test the same behavior through the layer the user will touch: helper function, dispatcher, bridge HTTP, MCP wrapper, Blender UI, or packaged extension.
- Prefer generated test scenes over private `.blend` files. Tests should create their own objects, materials, cameras, actions, rigs, and temporary project folders.
- Every mutating helper must prove live-preview behavior: pending transaction, expected change report, rollback manifest, commit/revert path, and Blender undo compatibility where possible.
- Every safety-sensitive path must test both allowed and refused cases.
- Every long or visual operation must return pollable artifacts or readable resource URIs instead of relying only on console output.
- Every bug fix gets the smallest owner test first, then the broader gate that would have caught the bug.
- No test should require provider API keys. Optional Sketchfab download/import tests may use a per-run token from the environment, but tokens must never be stored in Blender preferences, logs, committed files, or guide text.

## Phase 0: Preflight

Run from the repository root:

```powershell
Set-StrictMode -Version Latest
$Blender = "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
git status --short --branch
Test-Path -LiteralPath $Blender
python --version
python -m compileall addon\claude_blender tests
git diff --check
```

Pass criteria:

- Worktree state is understood before testing.
- Blender path exists when Blender-background or live tests are requested.
- Python compilation succeeds.
- No whitespace errors from `git diff --check`.

If the worktree already has unrelated changes, do not revert them. Keep test logs and fixes scoped to the requested work.

## Phase 1: Fast Pure-Python Gate

These checks run without opening Blender and should be the first gate after almost every change.

```powershell
$PureTests = @(
  "tests\smoke_audit_log.py",
  "tests\smoke_bridge_protocol_validation.py",
  "tests\smoke_build_extension_zip.py",
  "tests\smoke_context_budget.py",
  "tests\smoke_extension_repository.py",
  "tests\smoke_external_assets.py",
  "tests\smoke_helper_routing.py",
  "tests\smoke_real_client_routing.py",
  "tests\smoke_mcp_server.py",
  "tests\smoke_script_analysis.py",
  "tests\smoke_tool_contract_inventory.py"
)

foreach ($Test in $PureTests) {
  Write-Host "== $Test =="
  python $Test
  if ($LASTEXITCODE -ne 0) { throw "Failed: $Test" }
}
```

What this covers:

- Audit log redaction and event shape.
- Bridge protocol schema validation.
- Extension ZIP builder smoke.
- Context-budget truncation and prompt JSON limits.
- Static extension repository generation.
- External asset catalog/cache helpers that do not need Blender imports.
- Helper-first script routing metadata and recommended-tool drift.
- Real-client prompt routing fixtures for animation, visual inspection, advanced creation, asset import, preview/revert, and director orchestration.
- Stdio MCP protocol, compact catalog, pagination, prompts, resources, wrappers, and error paths.
- Static script analysis and risk classification.
- Catalog-to-contract inventory drift, including intentional external-only tools.

## Phase 2: Blender-Background Suite

Run this when changes touch Blender APIs, tool behavior, live preview, animation, rendering, project files, UI registration, bridge server behavior, or packaging.

```powershell
$Blender = "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
$BlenderTests = @(
  "tests\smoke_advanced_helpers.py",
  "tests\smoke_agent_tools.py",
  "tests\smoke_animation_controls.py",
  "tests\smoke_animation_helpers.py",
  "tests\smoke_bridge_server.py",
  "tests\smoke_context_docs.py",
  "tests\smoke_context_planner.py",
  "tests\smoke_external_asset_imports.py",
  "tests\smoke_full_tool_inventory.py",
  "tests\smoke_live_helpers.py",
  "tests\smoke_project_files.py",
  "tests\smoke_refinement_helpers.py",
  "tests\smoke_refinement_visual_qa.py",
  "tests\smoke_render_jobs.py",
  "tests\smoke_safe_editing_helpers.py",
  "tests\smoke_script_runner.py",
  "tests\smoke_tool_selection.py",
  "tests\smoke_world_model.py"
)

foreach ($Test in $BlenderTests) {
  Write-Host "== $Test =="
  & $Blender --background --factory-startup --python $Test
  if ($LASTEXITCODE -ne 0) { throw "Failed: $Test" }
}
```

Useful optional environment:

```powershell
$env:BAB_RENDER_JOB_SMOKE_TIMEOUT_SECONDS = "180"
$env:CLAUDE_BLENDER_VISUAL_QA_DIR = "$env:TEMP\bab-visual-qa"
```

Pass criteria:

- Every test exits `0`.
- Visual QA artifacts, if kept, are nonblank and have a manifest.
- Render-job smoke reaches completed, failed-with-expected-message, or cancelled states as the test expects.
- No tests leave permanent files in the repo unless explicitly generated release artifacts are being tested.

## Phase 3: Packaging And Release Artifacts

Run after manifest, build, docs, release, install, or packaging changes.

```powershell
$Blender = "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
$Version = python -c "import tomllib; print(tomllib.load(open('addon/claude_blender/blender_manifest.toml','rb'))['version'])"
& $Blender --command extension validate addon\claude_blender
python scripts\build_extension_zip.py --blender $Blender
& $Blender --command extension validate "dist\claude_blender-$Version.zip"
python scripts\build_extension_repository.py --build-zip --blender $Blender --repo-dir public
python tests\smoke_release_consistency.py
python tests\smoke_build_extension_zip.py
python tests\smoke_extension_repository.py
```

Also inspect the ZIP:

```powershell
python -c "import tomllib, zipfile; from pathlib import Path; version=tomllib.load(open('addon/claude_blender/blender_manifest.toml','rb'))['version']; z=Path(f'dist/claude_blender-{version}.zip'); names=zipfile.ZipFile(z).namelist(); forbidden=[n for n in names if any(p in n.lower() for p in ['.git/','__pycache__/','.pytest_cache/','.claude_blender/captures','audit.jsonl','.blend1','.blend@','sketchfab','token'])]; print('entries', len(names)); print('forbidden', forbidden); assert 'LICENSE' in names; assert not forbidden"
```

Pass criteria:

- Manifest version, `CHANGELOG.md`, ZIP filename, and SHA-256 sidecar agree.
- Blender validates source extension and built ZIP.
- ZIP contains `LICENSE` and excludes private/generated artifacts.
- `public/index.json`, `public/index.html`, ZIP, and checksum sidecar are regenerated and valid.
- Optional live Pages smoke sets `BLENDER_AGENT_BRIDGE_LIVE_PAGES_SMOKE=1` before `tests\smoke_release_consistency.py` and verifies the deployed remote repository index advertises the current manifest version and that its hosted ZIP matches the advertised SHA-256 hash.

## Phase 4: Clean Install Smoke

Use a temporary Blender profile so installed state, extension caches, and client config are not polluted.

```powershell
$Blender = "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
$Profile = Join-Path $env:TEMP "bab-clean-profile"
Remove-Item -Recurse -Force $Profile -ErrorAction SilentlyContinue
$env:BLENDER_USER_CONFIG = Join-Path $Profile "config"
$env:BLENDER_USER_SCRIPTS = Join-Path $Profile "scripts"
$env:BLENDER_USER_CACHE = Join-Path $Profile "cache"
$env:BLENDER_USER_EXTENSIONS = Join-Path $Profile "extensions"
New-Item -ItemType Directory -Force -Path $env:BLENDER_USER_CONFIG,$env:BLENDER_USER_SCRIPTS,$env:BLENDER_USER_CACHE,$env:BLENDER_USER_EXTENSIONS
& $Blender --background --factory-startup --python tests\smoke_agent_tools.py
```

For the GitHub Pages install path:

```powershell
& $Blender --online-mode --command extension repo-add blender_agent_bridge --name "Blender Agent Bridge" --directory "$env:BLENDER_USER_EXTENSIONS" --url "https://callmejones.github.io/blender-agent-bridge/index.json" --clear-all
& $Blender --online-mode --command extension sync
& $Blender --online-mode --command extension install -s -e claude_blender
& $Blender --online-mode --command extension list -s
```

Pass criteria:

- Extension installs and enables from a clean profile.
- The add-on registers without console errors.
- Sidebar reports add-on, bridge, MCP, and config versions.
- `Copy MCP Config` includes current version metadata and source hash metadata.

## Phase 5: Live Bridge And MCP Smoke

Run when changing `bridge_server.py`, `mcp_server.py`, `bridge_protocol.py`, `agent_tools.py`, `tool_dispatcher.py`, resource handling, prompts, copied MCP config, source hashes, bridge auth, or tool routing.

Manual setup:

1. Open Blender with the tested extension installed or linked.
2. Start from factory startup or a generated test scene.
3. In the 3D View sidebar, open `Agent Bridge`.
4. Press `Start Bridge`.
5. Press `Copy MCP Config`.
6. Restart or refresh the MCP client after replacing its config.

Direct bridge smoke from PowerShell:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8765/health
Invoke-RestMethod -Uri http://127.0.0.1:8765/tools
Invoke-RestMethod -Uri http://127.0.0.1:8765/tool -Method Post -ContentType application/json -Body '{"name":"list_scene_objects","arguments":{"max_objects":10}}'
Invoke-RestMethod -Uri http://127.0.0.1:8765/resources
```

Fast evidence smoke from the repository root:

```powershell
python scripts\live_bridge_smoke.py
```

This checks bridge health, captures a viewport PNG, captures a tiny sampled playblast, and verifies `get_visual_evidence_resources` can see the latest artifacts.

MCP stdio smoke against the live bridge:

```powershell
$Mcp = "addon\claude_blender\mcp_server.py"
$Request = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"manual-smoke","version":"1"}}}'
$Request | python $Mcp --bridge-url http://127.0.0.1:8765
```

Compact MCP mode must show these direct tools:

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

Full MCP mode:

```powershell
$env:BLENDER_MCP_FULL_TOOL_LIST = "1"
python tests\smoke_mcp_server.py
Remove-Item Env:\BLENDER_MCP_FULL_TOOL_LIST
```

Pass criteria:

- `blender_bridge_status` reports matching add-on, bridge, MCP server, config version, and source hash metadata.
- Compact mode uses catalog/search/schema/invoke for the large helper catalog.
- Full mode can expose every bridge contract as a top-level tool for debugging.
- Wrapper tools cannot invoke wrapper tools recursively through `invoke_blender_tool`.
- Pagination works for `tools/list`, `resources/list`, `resources/templates/list`, and `prompts/list`.
- `resources/read` works for status resources before captures and for exact artifact resources after captures.

## Phase 6: Tool Coverage Matrix

Every dispatcher tool should have coverage at four levels unless there is a documented reason it cannot:

- Schema: `agent_tools.py` definition or intentional hidden status, JSON Schema validation, output shape, risk/permission annotations.
- Dispatcher: direct `tool_dispatcher.execute_tool(context, name, args)` happy path and failure path.
- Bridge/MCP: discoverable through compact catalog or direct compact tool, schema retrievable, invalid arguments rejected before dispatch, valid call forwarded.
- Behavior: scene/resource/audit/preview effects match the contract.

Regenerate the inventory before a comprehensive sweep:

```powershell
$text = Get-Content -Raw -LiteralPath "addon\claude_blender\tool_dispatcher.py"
$dict = [regex]::Match($text, "TOOL_FUNCTIONS\s*=\s*\{(?<body>[\s\S]*?)\n\}")
$names = [regex]::Matches($dict.Groups["body"].Value, '"([a-zA-Z0-9_]+)"\s*:') | ForEach-Object { $_.Groups[1].Value }
"TOOL_FUNCTIONS count: $($names.Count)"
$names
```

### Inspection And Context

Tools:

```text
inspect_scene
list_scene_objects
get_object_details
get_animation_details
get_animation_scene_context
get_material_node_details
get_geometry_nodes_details
get_shader_nodes_details
get_rigging_details
get_shape_key_details
get_curve_text_details
get_simulation_details
inspect_simulation_bake
get_collection_layer_details
get_render_camera_compositor_details
plan_advanced_scene_workflow
get_2d_animation_details
get_blend_file_diagnostics
get_workspace_layout
get_visual_evidence_resources
search_blender_docs
```

Owner tests:

- `tests\smoke_context_docs.py`
- `tests\smoke_context_planner.py`
- `tests\smoke_world_model.py`
- `tests\smoke_tool_selection.py`
- `tests\smoke_bridge_protocol_validation.py`
- `tests\smoke_mcp_server.py`

Required scenarios:

- Empty factory scene, selected object, many objects, hidden objects, collections, materials, node trees, animation data, cameras, compositor settings, rigs, shape keys, particles/simulation hints.
- Budgeted context omits large details but recommends detail tools.
- Docs search returns focused snippets and official-source URLs or a clear offline/cache miss.
- Background mode returns soft failures for UI-only details instead of hard crashes.

### Selection, Transforms, Objects, Collections

Tools:

```text
select_objects
set_current_frame
set_selected_location_delta
set_selected_transform
create_primitive
create_empty
duplicate_selected_objects
parent_selected_to_empty
align_selected_objects
distribute_selected_objects
set_object_visibility
set_object_display
create_collection
link_selected_to_collection
```

Owner tests:

- `tests\smoke_safe_editing_helpers.py`
- `tests\smoke_live_helpers.py`
- `tests\smoke_agent_tools.py`

Required scenarios:

- Missing object names, invalid object names, empty selection, active object handling, multiple selected objects, name collisions.
- Preview transaction created, result includes expected changes, revert restores object state, commit clears pending state.
- Failed helper that opens a transaction auto-reverts only its own new transaction and preserves any previous pending transaction.

### Materials, Shading, Geometry Nodes, World

Tools:

```text
assign_material_to_selected
assign_emission_material_to_selected
create_shader_material
add_geometry_nodes_modifier
create_material_palette
set_world_background
```

Owner tests:

- `tests\smoke_advanced_helpers.py`
- `tests\smoke_safe_editing_helpers.py`
- `tests\smoke_refinement_helpers.py`
- `tests\smoke_world_model.py`

Required scenarios:

- Existing material reuse, new material creation, alpha/emission inputs, object with no material slots, invalid color values.
- Geometry Nodes starter modifier creates bounded nodes and rollback restores node group/material/link topology.
- Material palette swatches and optional assignment stay in preview rollback.

### Lighting, Cameras, Render Settings

Tools:

```text
add_light
add_camera
set_active_camera
set_camera_settings
set_render_settings
create_camera_orbit
analyze_camera_framing
render_scene_thumbnail
```

Owner tests:

- `tests\smoke_safe_editing_helpers.py`
- `tests\smoke_animation_helpers.py`
- `tests\smoke_render_jobs.py`
- `tests\smoke_bridge_server.py`

Required scenarios:

- Camera added and assigned active camera.
- DOF settings validate focus object existence.
- Thumbnail render restores render settings and exposes `blender://render-thumbnails/...` resources.
- Large thumbnail requests recommend `start_render_job` unless `allow_blocking_render=true`.

### Animation Generation, Review, And Repair

Tools:

```text
create_animation_brief
create_timing_chart
plan_animation_workflow
run_animation_workflow
run_animation_task
analyze_motion_arcs
analyze_fcurve_spacing
analyze_pose_clarity
analyze_animation_principles
sample_animation_state
analyze_contact_sliding
analyze_collision_penetration
analyze_center_of_mass
analyze_camera_framing
analyze_motion_physics
compare_animation_to_brief
review_playblast_against_brief
review_inspection_renders_against_brief
repair_animation_from_findings
run_animation_repair_loop
animate_selected_transform
animate_shape_key
animate_object_bounce
create_progressive_bounce_animation
animate_material_property
animate_light_property
create_follow_path_animation
set_action_interpolation
retime_actions
add_action_cycles
clear_animation
set_animation_preview_range
create_turntable_animation
create_pulse_animation
create_reveal_animation
create_staggered_motion
block_key_poses
add_breakdown_pose
set_pose_hold
create_motion_arc
set_scene_frame_range
```

Owner tests:

- `tests\smoke_animation_helpers.py`
- `tests\smoke_animation_controls.py`
- `tests\smoke_tool_selection.py`
- `tests\smoke_world_model.py`
- `tests\smoke_bridge_server.py`

Required scenarios:

- Prompt-only routing uses `run_animation_task` or `run_animation_workflow` before script fallback.
- Bounce plus shrinking routes to `create_progressive_bounce_animation`.
- Ambiguous review prompts use evaluator/review helpers and do not draft Python first.
- Timing chart, pose blocking, breakdown, holds, interpolation, retiming, cycles, preview range, and clear animation update expected f-curves/actions.
- Review tools return actionable findings and executable repair operation payloads.
- Repair loop respects allowlists, max iterations, skipped operations, fresh review after mutation, and live-preview rollback.

Regression prompts for real clients:

| Prompt | Expected route | Pass condition |
| --- | --- | --- |
| `make selected cube bounce twice and get smaller each bounce` | `run_animation_task` or `run_animation_workflow`, then `create_progressive_bounce_animation` | Workflow route preferred; explicit script/Python requests may still use `draft_script` after static checks. |
| `block a jump with anticipation, contact, apex, settle` | `plan_animation_workflow` or `run_animation_task`, then timing/blocking helpers | Workflow-first path before Python. |
| `review this animation for spacing/contact` | Workflow/evaluator/review tools | Review helpers before script repair. |

### Rig, Pose, Shape Keys, Simulation

Tools:

```text
set_rig_pose_hold
set_rig_custom_property_keyframes
get_rig_pose_library_details
apply_rig_pose_from_action
apply_rig_pose_marker
apply_rig_action_clip
offset_rig_limb_controls
create_shape_key
animate_shape_key
inspect_simulation_bake
stage_persistent_simulation_bake
```

Owner tests:

- `tests\smoke_animation_helpers.py`
- `tests\smoke_animation_controls.py`
- `tests\smoke_world_model.py`
- `tests\smoke_context_docs.py`

Required scenarios:

- Rig helpers require armature names and inspect controls before editing.
- IK/FK or space-switch custom properties are keyed only when found.
- Pose library/action helpers reject missing action or marker names clearly.
- Shape-key helpers validate object support, key existence, and value ranges.
- Simulation inspection is read-only and restores the original scene frame.
- Persistent simulation bake stages approval-gated Python and does not silently bake caches.

### Advanced Creation And Refinement Kits

Tools:

```text
create_text_object
create_curve_path
create_storyboard_panels
create_2d_cutout_layer
apply_procedural_array_stack
create_procedural_object_kit
create_camera_dolly_animation
create_directed_animation_shot
add_particle_system_to_selected
add_cloth_simulation_to_selected
create_basic_armature
add_copy_transform_constraint
shade_smooth_selected
add_bevel_and_subsurf
create_wheel_assembly
add_panel_seams
add_window_materials
apply_vehicle_refinement_template
apply_product_refinement_template
apply_character_refinement_template
create_studio_product_stage
add_dimension_callouts
apply_lighting_preset
create_product_turntable_setup
organize_scene_for_production
add_modifier_to_selected
add_track_to_constraint
```

Owner tests:

- `tests\smoke_advanced_helpers.py`
- `tests\smoke_refinement_helpers.py`
- `tests\smoke_refinement_visual_qa.py`
- `tests\smoke_safe_editing_helpers.py`

Required scenarios:

- Helpers create bounded, reversible data-blocks and reject unsupported complex operations.
- 2D/storyboard helpers create reversible panels, labels, flat cutout layers, and camera moves.
- Procedural stack helpers add bounded array/bevel/weighted-normal modifiers without destructive mesh edits.
- Cloth setup adds a modifier only; cache inspection and persistent bake remain separate explicit steps.
- Product, vehicle, and character templates generate expected named objects/materials/collections.
- Visual QA renders product and character outputs and rejects blank images.
- Rollback restores created objects, materials, modifiers, constraints, collections, cameras, and lights.

### Visual Evidence And MCP Resources

Tools and resources:

```text
capture_viewport
capture_animation_playblast
capture_object_inspection_renders
render_scene_thumbnail
get_visual_evidence_resources
blender://captures/latest
blender://captures/latest/metadata
blender://captures/{capture_id}
blender://playblasts/latest/metadata
blender://playblasts/{playblast_id}/metadata
blender://playblasts/{playblast_id}/frames/{frame}
blender://inspection-renders/latest/metadata
blender://inspection-renders/{render_id}/metadata
blender://inspection-renders/{render_id}/images/{image_id}
blender://render-thumbnails/latest
blender://render-thumbnails/latest/metadata
blender://render-thumbnails/{thumbnail_id}
blender://render-thumbnails/{thumbnail_id}/metadata
```

Owner tests:

- `tests\smoke_bridge_server.py`
- `tests\smoke_context_docs.py`
- `tests\smoke_refinement_visual_qa.py`
- `tests\smoke_mcp_server.py`

Required scenarios:

- Background mode fails soft for viewport/playblast capture when an interactive window is required.
- Interactive mode captures readable PNG resources and metadata includes project id, session id, dimensions, byte size, and exact resource URIs.
- Oversized captures downscale or reject according to byte budgets.
- Resource reads return correct `mimeType`, text/blob shape, and bounded output.

### Async Render Jobs

Tools and resources:

```text
start_render_job
get_render_job_status
cancel_render_job
assemble_render_job_video
validate_render_job_output
blender://render-jobs/latest/metadata
blender://render-jobs/{job_id}/metadata
blender://render-jobs/{job_id}/frames/{frame}
blender://render-jobs/{job_id}/log
blender://render-jobs/{job_id}/video
```

Owner tests:

- `tests\smoke_render_jobs.py`
- `tests\smoke_mcp_server.py`
- `tests\smoke_bridge_server.py`

Required scenarios:

- Preview jobs use lower defaults unless quality/resolution/samples are explicit.
- Final jobs keep final-quality defaults.
- Bridge tokens and URLs are scrubbed from child process environments.
- Polling reports elapsed time, progress, log tail, newest frame URI, and terminal state.
- Cancel stops tracked processes and leaves useful status.
- Video assembly and output validation report MP4 path/resource state.
- Large MP4 resources return a local path when too large for base64 MCP transfer.

### Project Files And Autosave

Tools:

```text
save_blend_file
open_blend_file
create_new_blender_project
autosave_current_blend_file
get_blend_file_diagnostics
```

Owner tests:

- `tests\smoke_project_files.py`
- `tests\smoke_context_docs.py`

Required scenarios:

- Save active bound file without a new filepath.
- Save-as/save-copy, open, and new project require `user_confirmed_path=true`.
- Opening or creating a new project requires `confirm_discard_current=true`.
- Unsaved scenes refuse autosave.
- Checkpoint behavior is clear when required, optional, failed, or skipped.
- Agents never invent durable user paths during MCP/client tests.

### External Assets

Tools:

```text
list_poly_haven_categories
search_poly_haven_assets
inspect_poly_haven_asset_files
download_poly_haven_asset
import_poly_haven_asset
search_sketchfab_models
download_sketchfab_model
import_sketchfab_model
start_external_asset_download
get_external_asset_job_status
cancel_external_asset_job
import_external_asset_job_result
start_external_asset_import_job
get_external_asset_import_job_status
cancel_external_asset_import_job
delete_external_asset_job
get_external_asset_cache_diagnostics
prune_external_asset_cache
```

Owner tests:

- `tests\smoke_external_assets.py`
- `tests\smoke_external_asset_imports.py`
- `tests\smoke_mcp_server.py`

Required scenarios:

- Poly Haven search and file-tree inspection handle network success, timeout, unavailable assets, hash/size metadata, and license/source reporting.
- Download helpers cache files and verify MD5/size when available.
- Import helpers leave preview changes and record imported data-block names.
- Async asset download jobs run through the default subprocess worker, publish progress/final manifests, and can feed queued import jobs.
- Sketchfab public search works without tokens for public metadata.
- Sketchfab download/import only uses per-call `api_token` or `SKETCHFAB_API_TOKEN` / `BLENDER_AGENT_BRIDGE_SKETCHFAB_API_TOKEN`.
- Cache diagnostics and job status do not expose secrets.

### Script Safety, Approval, Trust, Audit, Preview

Tools:

```text
draft_script
run_approved_script
commit_preview
revert_preview
```

Owner tests:

- `tests\smoke_script_analysis.py`
- `tests\smoke_script_runner.py`
- `tests\smoke_audit_log.py`
- `tests\smoke_live_helpers.py`
- `tests\smoke_bridge_server.py`

Required scenarios:

- Missing code, alternate code field names, compile errors, static warnings, blocked imports/calls, and harmless scripts.
- Approval token is short-lived, bound to the pending script text, one-time use, and rejected when stale or wrong.
- Runtime external script trust allows tokenless runs only while active and only after static checks pass.
- Trust is cleared on add-on reload, file load, and bridge start.
- Animation-like and helper-overlap script drafts can stage or auto-run under trust after static checks pass, with helper advice returned as metadata.
- External asset download/import and project file lifecycle scripts use `draft_privileged_script` when custom Python is required; they require a review/audit manifest and one-time approval and do not auto-run under normal trust. The manifest is not a runtime filesystem or network sandbox. Persistent simulation/cache bake and static-dangerous Python remain blocked or explicitly approval-gated.
- Checkpoints, undo, stdout/stderr logs, error tracebacks, and pending script state are visible.
- Audit logs redact code/token-like fields and record bridge/MCP tool calls.
- Commit/revert preview status and rollback warnings are returned and shown.

## Phase 7: Real Client End-To-End Tests

These catch issues unit/smoke tests cannot, especially stale MCP client caches and model/tool routing behavior.

Run after installing a fresh ZIP or changing MCP/tool schemas:

1. Install or link the tested extension.
2. Start Blender with a factory cube.
3. Start the bridge and copy fresh MCP config.
4. Restart the MCP client.
5. Ask the client to call `blender_bridge_status`.
6. Confirm source hashes and versions match the Blender sidebar.
7. Run these prompts:

```text
Inspect the scene and list the objects.
```

```text
Move the selected cube up 1 Blender unit and make it red. Leave it as a preview.
```

```text
Revert the pending preview.
```

```text
Make the selected cube bounce twice and get smaller each bounce. Review it against the brief and leave it as a preview.
```

```text
Create an advanced procedural object kit using a radial array. Leave it as a preview.
```

```text
Create a directed camera push reveal shot for the selected cube. Leave it as a preview.
```

```text
Capture a viewport screenshot, then read the latest capture metadata resource.
```

```text
Render a small scene thumbnail and read its metadata resource.
```

For a repeatable live bridge sweep that covers the same major workflow families without a real external asset download:

```powershell
python scripts\live_workflow_sweep.py
```

Use `--skip-viewport` when Blender is running headless or the foreground viewport capture path is not available. The sweep reverts its preview changes by default; pass `--keep-preview` only when you want to inspect the result in Blender.

Pass criteria:

- Client uses helper/workflow tools when they clearly fit, but custom advanced `draft_script` calls can proceed after static checks and approval/trust.
- Preview changes are visible in Blender and reversible.
- MCP resources can be read by URI.
- Blender sidebar stays lean while bridge/tool responses expose source/hash status, audit status, preview manifest, and visual evidence inventory.
- Client final responses accurately state what changed, what is pending, and what artifact URIs or paths exist.

## Phase 8: Negative And Security Tests

Run after changes touching script execution, bridge auth, filesystem paths, project files, external assets, audit logging, or trust.

Required negative cases:

- Invalid JSON to MCP returns parse error.
- Unknown MCP method returns method-not-found.
- Tool with missing required arguments is rejected before dispatch.
- Extra properties are rejected when schemas say `additionalProperties: false`.
- Bridge with wrong bearer token rejects protected endpoints.
- `draft_script` refuses filesystem deletion, shell/process execution, credential/environment reads, dynamic `exec/eval`, unsafe imports, and blocked network calls.
- `open_blend_file`, `create_new_blender_project`, and save-as/copy refuse unconfirmed paths.
- Sketchfab token arguments are redacted from logs and not written to preferences.
- Render child processes do not inherit `BLENDER_BRIDGE_TOKEN` or `BLENDER_BRIDGE_URL`.
- Trust Off/reload/file-load/bridge-start revokes trust and tokenless `run_approved_script` fails afterward.

## Phase 9: Coverage Gap Audit

At the end of a comprehensive run, report these gaps explicitly if they were not tested:

- Real MCP client routing after fresh ZIP install and client restart.
- Interactive viewport/playblast capture in a foreground Blender window.
- GitHub Pages remote repository install from a clean profile.
- Optional external network download/import tests for Poly Haven or Sketchfab.
- Cross-version Blender compatibility beyond 5.1.
- Long 1080p/4K render-job behavior.
- Manual visual inspection of kept render/playblast artifacts.

Known current gaps to prioritize:

- `scripts\live_workflow_sweep.py` now covers the major bridge workflow families, but there is still no exhaustive automated happy-path sweep that invokes every dispatcher tool through the live bridge.
- Background tests verify many visual paths, but true viewport/playblast capture still needs a foreground Blender window for full confidence.
- Real-client MCP routing is still necessary after tool-surface changes because clients can cache old tools and configs.

## Bug Fix Loop

For every failure:

1. Capture the failing command, exit code, stack trace, tool name, arguments, and any generated artifact path.
2. Identify the owning feature group in this guide.
3. Fix the narrow cause without rewriting unrelated modules.
4. Add or update the smallest owner smoke test that would fail before the fix.
5. Rerun the owner test.
6. Rerun Phase 1.
7. Rerun Phase 2 or Phase 5 if the fix touched Blender APIs, bridge contracts, MCP schema, resources, live preview, or script safety.
8. Summarize the failure, fix, tests run, and any remaining untested gaps.

Bug report template:

```text
Feature group:
Tool or command:
Layer: direct / dispatcher / bridge / MCP / UI / package
Expected:
Actual:
Reproduction command:
Artifact/log path:
Fix:
Owner test:
Regression gate:
Remaining risk:
```

## When Adding Or Changing A Tool

Update and test all of these:

- `addon/claude_blender/agent_tools.py`: schema, description, risk/permission hints, routing guidance.
- `addon/claude_blender/tool_dispatcher.py`: dispatcher implementation and `TOOL_FUNCTIONS`.
- `addon/claude_blender/bridge_protocol.py`: schema validation if contract shape changes.
- `addon/claude_blender/mcp_server.py`: compact wrapper behavior, catalog/search/schema/invoke behavior, timeout/resource handling if relevant.
- Owner smoke test under `tests/`.
- `tests\smoke_mcp_server.py`: catalog/wrapper/protocol expectations if MCP-visible.
- `tests\smoke_tool_selection.py`: routing expectations if agent guidance should prefer the tool.
- Docs: update the relevant architecture/MCP/safety/release docs when user-visible behavior changes.

Minimum new-tool test set:

- Valid call succeeds.
- Missing required input fails clearly.
- Wrong type or unsupported enum fails through schema validation.
- Extra property is rejected when appropriate.
- Mutating call creates preview state and can revert.
- Read-only call does not create preview state.
- MCP catalog finds it by name and likely search terms.
- `get_blender_tool_schema` returns exactly the intended schema.
- `invoke_blender_tool` forwards valid args and refuses invalid args.
- Audit log records the call with sensitive arguments redacted.

## Suggested Automation Backlog

These are good next improvements to make the suite more comprehensive:

- Keep `tests\smoke_full_tool_inventory.py` current so dispatcher/catalog/bridge contract consistency and the intentional `run_approved_script` exception stay covered.
- Add a generated-scene live bridge harness that starts Blender foreground, starts the bridge, then drives MCP stdio calls against real resources.
- Add a compact per-tool smoke manifest with tool name, feature group, mutates/read-only, required fixture, positive args, negative args, expected preview behavior, and expected resources.
- Add a CI job that runs all pure-Python tests plus a smaller Blender-background subset on Windows with Blender cached or installed.
- Add artifact retention for visual QA PNG manifests on manual workflow dispatch.
- Add optional network-marked tests for Poly Haven and Sketchfab that skip cleanly without network/token access.
