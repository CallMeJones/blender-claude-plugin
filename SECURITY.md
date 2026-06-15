# Security

Blender Agent Bridge gives AI agents structured access to a live Blender scene. Treat generated Blender Python as powerful local code.

## Supported Versions

This project is early and currently supports the latest public `main` branch only.

## Reporting

Please report security issues privately when possible through GitHub security advisories for this repository. If advisories are not available, contact the maintainer through the repository before publishing details.

Do not include API keys, bridge tokens, proprietary `.blend` files, or private scene screenshots in a public issue.

## Security Model

- Generated arbitrary Python must be staged with `draft_script` and approved inside Blender before execution.
- The MCP bridge binds to `127.0.0.1` only and can require a bearer token.
- Live helper tools are bounded and should use reversible preview transactions.
- Checkpoints are saved before approved scripts when enabled.
- Runtime external script trust presets allow iterative tokenless script runs only for staged scripts that still pass static checks. Trust is cleared by revoke, add-on reload, file load, or bridge restart depending on the preset.
- MCP capture resources expose local viewport screenshots to connected MCP clients. Keep screenshots off when visual context is not needed, and treat project-local `.claude_blender/captures/` folders as generated artifacts.
- Audit events are written locally to `~/.claude_blender/audit.jsonl` by default. Script/code-like arguments, tokens, keys, and passwords are redacted before logging.
- Static script checks are guardrails, not a sandbox. Blender Python can still access local files, network, and process state if the user approves it.

## Hardening Checklist Before Release

- Run the smoke tests and build workflow.
- Review `blender_manifest.toml` permissions.
- Verify no secrets are present in docs, examples, generated zips, or logs.
- Confirm generated Python cannot run through external MCP without in-Blender approval.
- Confirm external script trust presets expire, revoke, and clear on bridge restart or reload.
