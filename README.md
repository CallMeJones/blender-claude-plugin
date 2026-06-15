# Blender Agent Bridge

Blender Agent Bridge is a Blender extension and local MCP bridge for scene-aware AI agents. It brings a Claude-powered assistant into the 3D View sidebar, and it exposes the running Blender scene to Codex, Claude Desktop, Claude Code, and other MCP-capable clients through a localhost bridge.

The project was originally named Claude for Blender. The internal add-on id, Python package, zip name, local paths, and MCP environment variables still use `claude_blender` for compatibility.

Recommended GitHub repository name: `blender-agent-bridge`.

## Status

- Early `0.1.0` extension.
- Targets Blender `5.1.0` or newer, matching `addon/claude_blender/blender_manifest.toml`.
- Uses Anthropic's Messages API for the in-Blender Claude assistant.
- Supports optional local MCP access through a `127.0.0.1` bridge.
- Supports the latest public `main` branch only while the project is still moving quickly.

## Capabilities

- Inspect the active `.blend` file through structured scene, selection, material, animation, rigging, render, camera, compositor, collection, and node-tree summaries.
- Attach a bounded viewport screenshot when the `Viewport` toggle is enabled, with project/session-scoped local storage and MCP image resources for external clients.
- Capture sampled animation playblast frames as project/session-scoped MCP image resources so agents can review timing, spacing, staging, arcs, and contact poses.
- Search cached official Blender Python API and Manual documentation before version-sensitive scripting.
- Let the in-Blender Claude assistant or external MCP agents call bounded live helper tools for common scene edits such as transforms, primitives, materials, cameras, lights, keyframes, constraints, geometry-node starters, shape keys, particles, text/curves, render settings, lighting presets, material palettes, product/vehicle/character kits, product turntables, and production scene organization.
- Keep live helper edits inside preview transactions so the user can commit, revert, or use Blender undo.
- Stage arbitrary Blender Python in the `Claude Pending Script` Text datablock and run it only after approval inside Blender.
- Grant optional runtime-only external script trust from sidebar presets for iterative MCP/client sessions. Staged scripts still pass static checks before running.
- Store local chat history, transcript state, pending scripts, script logs, repair context, and optional scene-agent memory in Blender Text datablocks.
- Write local audit events for bridge and MCP tool calls with redaction for code, tokens, keys, passwords, and credential-like fields.

## Safety and Privacy

Connected agents do not get blanket access to Blender. The in-Blender Claude assistant sends compact context and selected tool schemas to Anthropic, while the extension executes local helper calls itself and requires approval for generated Python.

Viewport images are sent only when the user enables the `Viewport` toggle. The localhost bridge does not call a model provider by itself; external MCP clients decide what to send to their own providers after reading resources or tool results.

Saved `.blend` projects store generated viewport captures and playblast frame sequences under `.claude_blender/captures/<session_id>` by default, while unsaved or unwritable projects fall back to the user cache. Treat these captures as generated runtime artifacts unless you intentionally keep them as visual QA evidence.

See [SECURITY.md](SECURITY.md) and [PRIVACY.md](PRIVACY.md) for the detailed model.

## Requirements

- Blender `5.1.0+`.
- Python available on `PATH` for build scripts and the external MCP server.
- `ANTHROPIC_API_KEY` set in the environment before launching Blender when using the in-Blender Claude chat.
- Network permission for Anthropic requests, Blender docs downloads, and the optional localhost bridge.
- File permission for docs caches, viewport captures, playblast frame sequences, checkpoints, transcripts, and audit logs.

## Install from Source

Build the extension zip from the repository root:

```powershell
python scripts\build_extension_zip.py
```

The build writes:

```text
dist/claude_blender-0.1.0.zip
dist/claude_blender-0.1.0.zip.sha256
```

Install the zip in Blender through the extension installation flow, enable `Blender Agent Bridge`, and open the 3D View sidebar. Configure the model and local paths in the add-on preferences.

For day-to-day development on Windows, link the checkout into Blender's user extension repository:

```powershell
.\scripts\link_blender_dev_extension.ps1
```

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for alternate Blender versions and custom extension repositories.

## First Prompts

With an object selected, try:

```text
Move the selected cube up 1 Blender unit and make it red.
```

```text
Add a warm area light above and to the left of the selected object.
```

```text
Create a camera orbit around the Cube from frame 1 to 120.
```

```text
Build a simple sci-fi product pedestal scene around the selected cube using primitives, bevels, blue emission accents, two lights, and a camera orbit. If this needs many steps, draft one approved script instead of using a long helper chain.
```

Live preview changes remain pending until you use `Commit`, `Revert`, or Blender undo. Generated Python remains pending until you use `Run Approved Script` or `Reject Script`.

## MCP Bridge

The External Bridge section in the sidebar can expose a localhost-only JSON bridge from Blender. Use `Start`, then `Copy MCP Config` to copy a stdio MCP server config for compatible clients.

The MCP surface is intentionally compact by default. `blender_tool_catalog` is the main search/schema/invoke entry point for the full local tool catalog, with compatibility wrappers still available for direct search, schema lookup, and invocation.

External clients can also read resources such as scene status, tool contracts, transcripts, audit logs, viewport captures, and sampled animation playblast frames. The capture resources include `blender://captures/latest`, `blender://captures/latest/metadata`, and exact `blender://captures/{capture_id}` URIs returned in capture metadata. Animation review resources include `blender://playblasts/latest/metadata`, exact `blender://playblasts/{playblast_id}/metadata`, and `blender://playblasts/{playblast_id}/frames/{frame}` PNG frame resources.

Some MCP clients cache tool lists and server configs. After installing a new zip, reloading the add-on, or pressing `Copy MCP Config`, replace the old client config and refresh or restart that MCP client.

See [docs/EXTERNAL_BRIDGE_MCP.md](docs/EXTERNAL_BRIDGE_MCP.md) for setup and troubleshooting.

## Development Checks

Run the pure-Python smoke tests that do not require Blender:

```powershell
python tests\smoke_mcp_server.py
python tests\smoke_build_extension_zip.py
```

Compile the add-on package:

```powershell
python -m compileall addon\claude_blender
```

Run Blender-background smoke tests when Blender is available, for example:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe' --background --factory-startup --python tests\smoke_context_docs.py
& 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe' --background --factory-startup --python tests\smoke_bridge_server.py
& 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe' --background --factory-startup --python tests\smoke_script_runner.py
& 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe' --background --factory-startup --python tests\smoke_refinement_helpers.py
& 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe' --background --factory-startup --python tests\smoke_refinement_visual_qa.py
```

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - architecture and subsystem overview.
- [docs/CONTEXT_AND_DOCS_ENGINE.md](docs/CONTEXT_AND_DOCS_ENGINE.md) - context planning, docs cache, and prompt budgeting.
- [docs/LIVE_PREVIEW_LOOP.md](docs/LIVE_PREVIEW_LOOP.md) - reversible live helper transactions.
- [docs/SAFETY_MODEL.md](docs/SAFETY_MODEL.md) - approval, preview, script, and bridge safety rules.
- [docs/EXTERNAL_BRIDGE_MCP.md](docs/EXTERNAL_BRIDGE_MCP.md) - localhost bridge and MCP server.
- [docs/RELEASE.md](docs/RELEASE.md) - release build and verification checklist.

## Repository Layout

```text
addon/claude_blender/          Blender extension source
docs/                          Project, architecture, safety, and release notes
scripts/                       Build and development helper scripts
tests/                         Pure-Python and Blender smoke tests
CHANGELOG.md                   Release notes
SECURITY.md                    Security policy and hardening checklist
PRIVACY.md                     Local data and provider-data notes
LICENSE                        GPL-3.0-or-later license text
```

## License

Blender Agent Bridge is licensed under the GNU General Public License, version 3 or any later version. The Blender extension manifest declares this as `SPDX:GPL-3.0-or-later`; see [LICENSE](LICENSE) for the full license text. Release zips include the license file at the package root.
