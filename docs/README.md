# Blender Agent Bridge Docs

Start with the top-level `README.md`, then use these deeper notes for development, safety, and external MCP setup.

## Current Implementation Notes

- Viewport captures are exposed to MCP clients through `blender://captures/latest`, `blender://captures/latest/metadata`, and exact `blender://captures/{capture_id}` resources.
- Sampled animation playblast frames are exposed through `blender://playblasts/latest/metadata`, exact playblast metadata resources, and frame PNG resources for animation review.
- Render thumbnails are exposed through `blender://render-thumbnails/latest`, exact thumbnail resources, and matching metadata resources.
- Async render jobs are exposed through `blender://render-jobs/latest/metadata`, exact job metadata resources, frame PNG resources, and log resources.
- Saved `.blend` files store generated captures and playblast frames in project-local `.claude_blender/captures/<session_id>` folders by default. Unsaved or unwritable projects use the global user cache.
- External script trust is runtime-only and can be granted from sidebar presets such as 15 minutes, 1 hour, 4 hours, or the current Blender session.
- The helper catalog now includes production kits for lighting presets, material palettes, product/vehicle/character refinement, product turntable staging, and scene organization.

## MCP Client Refresh

Some MCP clients cache tool lists and server configs. After installing a new zip or pressing `Copy MCP Config`, replace the old client config and refresh or restart the MCP client. The copied config includes `CLAUDE_BLENDER_MCP_CONFIG_VERSION`, add-on version, bridge version, MCP server version, and a short note in the server `env` block so stale configs are easier to spot.
