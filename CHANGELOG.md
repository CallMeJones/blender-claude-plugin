# Changelog

## Unreleased

- Nothing yet.

## 0.1.4

- Added asynchronous external asset download/cache jobs for Poly Haven and Sketchfab, with separate polling, cancellation, and main-thread import-result tools.
- Moved external asset download/cache jobs into background Blender worker processes by default, with stronger cancellation and an in-process compatibility mode for focused tests.
- Added resumable external asset downloads with `.part` files, HTTP Range resume, bounded retry/backoff, and checksum/size revalidation.
- Added Sketchfab archive extraction quotas for member count, uncompressed bytes, member size, path depth, symlinks, and compression ratio.
- Added cached-manifest import support so completed asset jobs can be imported without rerunning the download step.
- Added queued external asset import jobs with start/status/cancel tools so main-thread imports have the same pollable shape as downloads.
- Added external asset cache maintenance tools for dry-run pruning and terminal job metadata deletion.
- Added external asset job progress fields for phase, current file/url, bytes downloaded, expected size, per-file progress, attempts, and resume state.
- Added an opt-in live-network external asset smoke test, skipped by default and requiring explicit env vars for downloads.
- Hardened asset job metadata writes for Windows polling races and redacted Sketchfab secrets from persisted job metadata.

## 0.1.2

- Fixed Sketchfab download/import auth for MCP clients by forwarding `SKETCHFAB_API_TOKEN` / `BLENDER_AGENT_BRIDGE_SKETCHFAB_API_TOKEN` from the Claude/Codex MCP server environment into Blender as redacted per-call arguments.
- Added MCP status diagnostics for Sketchfab external-asset auth so stale client environments are visible through `blender_bridge_status`.
- Kept Sketchfab OAuth deferred; the public auth path for this release remains API-token based.
- Lowered the declared minimum Blender version to `5.0.0` for Blender 5.x compatibility.

## 0.1.1

- Added human-in-the-loop `.blend` lifecycle path policy: save-as/save-copy, open, and new-project operations require a user-confirmed path.
- Added in-place autosave for the active bound `.blend` file, with no snapshot files and no invented path for unsaved scenes.
- Added MCP path-policy annotations and compact-catalog recovery smoke coverage so clients can discover when to ask the user for a path.
- Hardened the stdio MCP server with protocol fallback, pagination, prompts, resource templates, structured tool errors, output schemas, and JSON Schema argument validation.
- Added normalized bridge tool contracts with risk levels, permissions, output schemas, and MCP annotations.
- Added local JSONL audit logging for MCP and bridge tool calls with redaction for code, tokens, keys, passwords, and credential-like fields.
- Exposed recent audit events through `blender://audit/latest`.
- Added pure-Python smoke tests and GitHub Actions coverage for the MCP/audit surface.
- Added a reproducible extension zip builder with SHA-256 sidecar output.
- Added Phase 2A safety hardening: transaction rollback manifests, rollback warnings, shader material node-link restoration, and pure static script risk classification.
- Added a compact `blender_tool_catalog` MCP entry point for search, facets, schema lookup, and validated invocation across the full Blender helper catalog.
- Added live external script trust status fields to bridge/MCP status, including countdown, tokenless-run capability, stale scene-state detection, and MCP client refresh guidance.
- Added runtime external script trust presets for 15 minutes, 1 hour, 4 hours, or the current Blender session, with revoke/reload/bridge-start clearing behavior.
- Added MCP viewport capture resources, including latest capture metadata and exact `blender://captures/{capture_id}` reads.
- Added project/session-scoped capture storage: saved `.blend` files use project-local `.claude_blender/captures/<session_id>` folders by default, with global fallback for unsaved or unwritable projects.
- Added sampled animation playblast frame capture with MCP metadata and exact `blender://playblasts/{playblast_id}/frames/{frame}` PNG resources for visual animation review.
- Added production helper kits for lighting presets, material palettes, product turntable staging, and scene organization.

## 0.1.0

- Initial public release.
