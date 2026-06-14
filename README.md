# Claude for Blender

Interactive Blender extension that connects Claude/Anthropic to the current scene, viewport, and Blender Python API so a user can ask for modeling, lighting, layout, rigging, and animation changes from inside Blender.

## Product Goal

The extension should feel like a scene-aware creative collaborator inside Blender:

- It can inspect the open `.blend` file through structured scene data.
- It can attach a bounded viewport screenshot when the Viewport toggle is enabled.
- It can reason with version-relevant Blender Python documentation.
- It can propose, explain, and run Blender Python changes with user approval.
- It can build objects, modify materials, set up cameras/lights, and create animations.
- It can use safe helper tools and script templates so common edits are simple and less fragile.
- It can inspect deeper Blender systems such as geometry nodes, shader nodes, rigs, constraints/drivers, shape keys, curves/text, simulations, collections/view layers, render settings, cameras, and compositor nodes through read-only tools.
- It can use bounded advanced helpers for shader materials, Geometry Nodes starter groups, shape keys, text/curves, particle systems, armatures, copy-transform constraints, render settings, camera settings, and world background colors before falling back to approved Python.
- It can expose the running Blender scene over an optional localhost bridge plus stdio MCP server, so external MCP clients can inspect resources and call Blender tools.
- It can apply approved low-risk changes immediately so the viewport and timeline update as Claude works.
- It can let Claude call safe Blender tools for object listing/selection, playhead changes, selected-object movement, absolute transforms, primitive/empty creation, object visibility/display, material assignment, emission materials, collections, modifiers, Track To constraints, timeline setup, active camera selection, transform keyframes, lights, cameras, and camera orbits.

## Initial Direction

Build this as a Blender 4.2+ extension with a 3D View sidebar panel, a Claude Messages API client, a context/docs engine, and a client-side tool loop. Claude should not get blanket control of Blender. Instead, the add-on exposes specific tools such as `inspect_scene`, `get_object_details`, `capture_viewport`, `search_blender_docs`, `draft_script`, and `run_approved_script`.

The first usable milestone is a human-in-the-loop assistant with live preview:

1. User asks a prompt in Blender.
2. Add-on sends Claude a scene summary and optional screenshot.
3. Claude responds with guidance, safe helper calls, or a proposed Blender Python script.
4. Low-risk helper calls can update the scene immediately inside a reversible preview transaction.
5. Riskier generated Python is shown for approval before execution.
6. The user can commit, undo, or revert the visible changes.

Viewport screenshots are captured only when the `Viewport` toggle is on. The full base64 image is sent to Claude as an image block but omitted from the local transcript text.
The sidebar shows screenshot status, file size, path, and a stable Blender image datablock name (`Claude Viewport Preview`) after capture. Use `Capture Preview` to test the screenshot without calling Claude, and `Open Screenshot` to inspect the exact PNG.

The sidebar also includes a Docs section. `Check` reports the local docs cache state, and `Build Full Python Docs Cache` downloads Blender's official versioned Python API zip, extracts it locally, and builds a compact searchable JSON index. Claude receives only the top matching snippets, not the whole docs set.

LLM requests are guarded by a context budget. Large scene data, docs search results, tool results, and transcript-visible context are compacted/truncated before the Anthropic API request is built, while screenshots remain separate image blocks.

The assistant now has scene-agent memory. Each successful prompt appends a compact turn summary to the `Claude Agent Memory` Text datablock, and that memory is sent with future prompts when the `Memory` toggle is on. Clearing the input box does not clear memory; use `Clear Memory` when you want a fresh working thread. Current Blender scene context remains authoritative if memory is stale.

Requests now pass through a token-aware context planner before Claude is called. The sidebar shows the planned character count and rough token estimate, and the bundle includes a `context_plan` that tells Claude what was included or omitted. Instead of concatenating every object, memory entry, material, animation, node tree, rig, collection, and docs page into the prompt, Claude can call read-only local tools such as `inspect_scene`, `get_object_details`, `get_animation_details`, `get_material_node_details`, `get_geometry_nodes_details`, `get_shader_nodes_details`, `get_rigging_details`, `get_shape_key_details`, `get_curve_text_details`, `get_simulation_details`, `get_collection_layer_details`, `get_render_camera_compositor_details`, and `search_blender_docs` when it needs deeper detail.

Tool schemas are also selected per request. The agent loop keeps a small core set of inspection/docs tools, then adds only the helper groups that match the prompt and recent memory, such as animation, materials, camera/rendering, geometry nodes, rigging, particles, or vehicle refinement. The request context includes a `tool_selection` summary with selected tool names and schema token estimates, so Claude knows which actions are available without carrying the whole toolbox every turn.

The extension now includes an External Bridge section. Press `Start` to expose a localhost-only JSON bridge from Blender, then `Copy MCP Config` to copy a stdio MCP server config for clients that support local MCP servers. The MCP surface is compact by default: use `blender_tool_catalog` as the single search/schema/invoke entry point for the full Blender helper catalog. Compatibility wrappers for search, schema lookup, and invocation remain available. See [EXTERNAL_BRIDGE_MCP.md](docs/EXTERNAL_BRIDGE_MCP.md).

If a client still shows an old tool list after a zip reinstall or reload, replace the copied MCP config and refresh or restart that MCP client. The copied config includes add-on, bridge, MCP server, and config-version metadata in the server `env` block to make stale configs easier to spot.

The sidebar is chat-oriented: `Send` starts a new instruction and clears the input box, `Continue` asks Claude to keep working from the current scene and memory, and short prompts like `ok`/`continue` are expanded into a real continuation request. Recent messages are stored in the `Claude Chat History` Text datablock and shown in the Conversation section. They do not approve or run generated Python.

The Action Center groups the current agent state: running tool, pending script approval, live preview commit/revert, screenshot capture/open, docs cache controls, checkpoint status, and retry actions when Claude needs to stage a script again.

Generated Python now uses an approval gate. If Claude needs Blender API code beyond the live helper tools, it can call `draft_script`, which writes the proposed code to the `Claude Pending Script` Text datablock and shows status, risk, intent, and expected changes in the sidebar. The script runs only when the user presses `Run Approved Script`; blocked scripts can be inspected but not executed from the UI. External clients can run a pending script after the user presses `Approve External Run` in Blender and gives that client the short-lived one-time token, or while a runtime-only Blender-side 15-minute external script trust window is active.
When checkpoints are enabled, approved scripts save a timestamped `.blend` copy before execution. Failed scripts keep their traceback in `Claude Script Log` and expose a `Repair Script` button that asks Claude to draft a corrected pending script.
Complex helper-driven builds have a larger tool-call budget and end with a readable summary instead of raw API JSON if the budget is reached. For many-object scenes, ask Claude to stage one cohesive approved script instead of issuing a long chain of live helper calls.

Advanced live helpers are now available for common deeper Blender systems:

- `create_shader_material`
- `create_empty`
- `set_object_visibility`
- `set_object_display`
- `add_geometry_nodes_modifier`
- `create_shape_key`
- `animate_shape_key`
- `create_text_object`
- `create_curve_path`
- `add_particle_system_to_selected`
- `create_basic_armature`
- `add_copy_transform_constraint`
- `set_render_settings`
- `set_camera_settings`
- `set_world_background`
- `shade_smooth_selected`
- `add_bevel_and_subsurf`
- `create_wheel_assembly`
- `add_panel_seams`
- `add_window_materials`
- `apply_vehicle_refinement_template`

These helpers mutate the live scene through the same preview transaction as the simpler tools, so the user can still use `Revert`, `Commit`, or Blender undo. They are intentionally bounded starter actions; complex custom geometry-node graphs, complex rigs, simulations, and mesh edits should still be staged as approved Python.
The vehicle refinement template is a first taste of reusable domain kits: it can add smoothing/bevels, wheels, glass panels, panel seams, headlights, and taillights around a selected mesh body.

## Planned Structure

```text
addon/claude_blender/
  __init__.py              # Blender extension entrypoint
  preferences.py           # API key, model, privacy, approval settings
  ui.py                    # Sidebar chat panel and operators
  anthropic_client.py      # Claude Messages API transport
  agent_loop.py            # Tool-use loop and transcript state
  chat_history.py          # Persistent per-blend chat history
  bridge_protocol.py       # Semantic tool contract for local bridge/MCP
  context_bundle.py        # Layered Blender world model for Claude
  context_planner.py       # Token-aware request context selection
  world_model.py           # Read-only deep Blender system summaries
  advanced_helpers.py      # Bounded advanced edit helpers
  scene_snapshot.py        # Structured scene/animation summaries
  viewport_capture.py      # Viewport screenshot and preview render capture
  live_preview.py          # Reversible preview transactions and redraws
  bridge_server.py         # Localhost JSON bridge for external agents
  mcp_server.py            # stdio MCP server that forwards to the Blender bridge
  script_runner.py         # Script validation, approval, execution, undo
  script_templates.py      # Safer helpers for common Blender edits
  docs_index.py            # Blender docs search/fetch interface
docs/
  PROJECT_PLAN.md
  ARCHITECTURE.md
  CONTEXT_AND_DOCS_ENGINE.md
  LIVE_PREVIEW_LOOP.md
  SAFETY_MODEL.md
  EXTERNAL_BRIDGE_MCP.md
```

## Reference Docs

- Development workflow: [DEVELOPMENT.md](docs/DEVELOPMENT.md)
- Anthropic tool use: https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview
- Anthropic vision: https://platform.claude.com/docs/en/build-with-claude/vision
- Anthropic Files API: https://platform.claude.com/docs/en/build-with-claude/files
- Blender extension packaging: https://docs.blender.org/manual/en/latest/advanced/extensions/getting_started.html
- Blender Python API: https://docs.blender.org/api/current/index.html

## First Action Prompts

With the cube selected, try:

```text
Move the selected cube up 1 Blender unit and make it red.
```

```text
Add a warm area light above and to the left of the selected object.
```

```text
Add a camera looking at the selected cube.
```

```text
Create a blue UV sphere to the right of the cube.
```

```text
Animate the selected cube moving from z 0 to z 3 over frames 1 to 80.
```

```text
Create a camera orbit around the Cube from frame 1 to 120.
```

```text
Make the selected cube glow cyan, add a bevel modifier, put it in a collection called Product Hero, then create a camera orbit from frame 1 to 120.
```

```text
Create a small abstract scene from primitives: a central glowing sphere, three surrounding torus rings, warm area lighting, and a camera orbit over 160 frames.
```

```text
Build a simple sci-fi product pedestal scene around the selected cube using primitives, bevels, blue emission accents, two lights, and a camera orbit. If this needs many steps, draft one approved script instead of using a long helper chain.
```

```text
Continue building the current sci-fi product pedestal scene from the existing objects. Finish the missing blue emission accents, lights, and camera orbit. If this needs many more steps, draft one approved script instead.
```

```text
List the scene objects, select the object named Cube, make it glow cyan, then set frame 40 so I can inspect the animation.
```

```text
Search the Blender docs for bpy.types.Constraint, then draft a script that adds a Track To constraint from the active camera to the selected cube.
```

```text
Create a polished blue metallic material on the selected cube, add a Geometry Nodes starter modifier, add a shape key named Lift, and animate that shape key from 0 to 1 over frames 1 to 80.
```

```text
Add a text label and a glowing curved path around the selected object, set the camera lens to 70mm with depth of field focused on the cube, and make the world background dark blue.
```

```text
Add a small particle system to the selected cube and create a simple armature next to it for later rigging. Keep it as live preview changes.
```

```text
Improve the selected car body using the vehicle refinement template, then add smoother bevels, panel seams, blue glass, wheel assemblies, headlights, taillights, better camera settings, and a dark world background. Keep it as live preview changes.
```

The live changes remain pending until you use `Commit`, `Revert`, or Blender undo.
Generated Python remains pending until you use `Run Approved Script` or `Reject Script`.
