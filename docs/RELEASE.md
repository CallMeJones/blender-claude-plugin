# Release Process

## Build

From the repository root:

```powershell
python scripts\build_extension_zip.py
```

The script reads `addon/claude_blender/blender_manifest.toml` and writes:

```text
dist/claude_blender-<version>.zip
dist/claude_blender-<version>.zip.sha256
```

If Blender is available and you want to use Blender's official extension builder:

```powershell
python scripts\build_extension_zip.py --blender blender
```

Blender documents the official extension build flow in the manual:
https://docs.blender.org/manual/en/latest/advanced/extensions/getting_started.html

## Verify

Run the checks that do not require Blender:

```powershell
python tests\smoke_mcp_server.py
python tests\smoke_build_extension_zip.py
python -m compileall addon\claude_blender
git diff --check
```

Run the focused Blender-background smoke tests:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe' --background --factory-startup --python tests\smoke_context_docs.py
& 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe' --background --factory-startup --python tests\smoke_bridge_server.py
& 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe' --background --factory-startup --python tests\smoke_script_runner.py
& 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe' --background --factory-startup --python tests\smoke_refinement_helpers.py
& 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe' --background --factory-startup --python tests\smoke_refinement_visual_qa.py
```

If Blender is on `PATH`, the same commands can use `blender` instead of the full executable path.

## Clean Install And MCP Smoke

After building a release zip, install `dist/claude_blender-<version>.zip` in a clean Blender profile and verify:

- The sidebar shows add-on, bridge, MCP, and config versions.
- `Start` enables the bridge without console errors.
- `Copy MCP Config` includes the current config metadata.
- The MCP client sees `blender_bridge_status`, `list_scene_objects`, `draft_script`, and `run_approved_script`, or can reach them through the compact catalog surface.
- `blender_bridge_status` reports matching add-on/bridge/MCP versions.
- `resources/list` includes capture, playblast, inspection-render, render-thumbnail, and async render-job resources, and `resources/read` can read `blender://captures/latest/metadata` after a capture, `blender://playblasts/latest/metadata` after a playblast capture, `blender://inspection-renders/latest/metadata` after diagnostic object renders, `blender://render-thumbnails/latest/metadata` after thumbnail renders, plus `blender://render-jobs/latest/metadata` after background render jobs.
- External script trust presets can be granted and revoked, and trust clears after bridge restart or add-on reload.

## Release Checklist

- Confirm `blender_manifest.toml` `version` matches `CHANGELOG.md`.
- Build the zip and SHA-256 sidecar.
- Confirm the generated zip includes `LICENSE` at the package root.
- Install the zip into a clean Blender profile.
- Start the External Bridge and run an MCP smoke against the installed extension.
- Capture one viewport screenshot and one sampled animation playblast, then confirm project-local or fallback capture storage behaves as documented.
- Review `SECURITY.md`, `PRIVACY.md`, and declared manifest permissions.
- Scan the zip for secrets, generated logs, checkpoints, screenshots, playblast frame sequences, caches, and private `.blend` files.
