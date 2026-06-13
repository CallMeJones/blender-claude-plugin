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
python tests\smoke_audit_log.py
python tests\smoke_mcp_server.py
python -m py_compile addon\claude_blender\audit_log.py addon\claude_blender\mcp_server.py addon\claude_blender\bridge_protocol.py addon\claude_blender\bridge_server.py scripts\build_extension_zip.py
```

Run Blender-background smoke tests when `blender` is on PATH.

## Release Checklist

- Confirm `blender_manifest.toml` `version` matches `CHANGELOG.md`.
- Build the zip and SHA-256 sidecar.
- Install the zip into a clean Blender profile.
- Start the External Bridge and run an MCP smoke against the installed extension.
- Review `SECURITY.md`, `PRIVACY.md`, and declared manifest permissions.
- Scan the zip for secrets, generated logs, checkpoints, screenshots, caches, and private `.blend` files.
