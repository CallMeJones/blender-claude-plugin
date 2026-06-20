# Safety Model

## Core Principle

External agents can suggest changes, inspect scene state, and call narrow tools. They should not receive unchecked authority to run arbitrary Python in Blender by default.

## Execution Modes

### Suggest Only

External agents can analyze and draft code, but nothing runs.

Use this when:

- The user is exploring an idea.
- The script touches file paths, deletes data, imports modules, or edits many objects.
- The model is using unfamiliar APIs.

### Approval Required

An external agent drafts a script, the add-on shows it, and the user explicitly approves execution.

This should be the default.

Current implementation:

- External agents can stage code with `draft_script`.
- The add-on writes the code to the `Agent Bridge Pending Script` Text datablock.
- Static checks block obvious risky imports and calls before the Run button is enabled.
- The sidebar shows status, risk, intent, expected changes, static issues/warnings, and Run/Reject controls.
- Static analysis reports both declared script risk and detected risk (`low`, `medium`, `high`, or `blocked`) with risk reasons and checkpoint recommendation.
- Execution pushes a Blender undo step when possible, saves a timestamped `.blend` checkpoint when enabled, and records stdout/errors in `Agent Bridge Script Log`.
- Failed scripts keep their pending code, traceback, and logs available locally so the external client can inspect and stage a corrected draft.
- External clients can normally call `run_approved_script` with a short-lived one-time token issued by the Blender UI for the current pending script.
- Users can also enable a Blender-side external script trust window from sidebar presets. During that runtime-only window, external clients may call `draft_script` and have it auto-run after static checks pass, or run an already staged script without a per-script token. Blocked scripts remain refused. Timed grants expire; session grants last until Revoke, add-on reload, file load, or bridge start.

### Limited Autonomous

External agents can call only allowlisted tools such as `inspect_scene`, `capture_viewport`, `capture_animation_playblast`, `capture_object_inspection_renders`, `set_object_transform`, or `add_light`. Arbitrary Python stays blocked.

Use this later for fast iterative workflows.

### Live Helpers

External agents can apply low-risk helper changes immediately to the open scene. Each change must be part of a preview transaction with visible commit/revert controls.

Use this for transforms, primitive/empty creation, object visibility/display, materials, lights, cameras, timeline settings, camera orbit setup, bounded keyframe edits, and bounded advanced helpers such as shader material setup, Geometry Nodes starter modifiers, shape keys, text/curve creation, simple particles, basic armatures, copy-transform constraints, render settings, camera settings, and world background color.

Advanced helpers are not a general Blender automation sandbox. They should create or edit narrow, reversible data-blocks. Custom geometry-node networks, production rigs, compositor graphs, simulations, destructive mesh operations, import/export, and broad scene edits should stay in approval-required Python.
Refinement templates are also bounded live helpers. They may create multiple primitives/materials/curves at once, but every created data-block must be recorded in preview rollback. Templates should improve composition and detail without pretending to replace real topology modeling.

### External Bridge / MCP

External clients can connect through the optional localhost bridge and stdio MCP server. This does not create a second safety model; it exposes the same tools/resources through a different transport.

Defaults and boundaries:

- The bridge is off until the user starts it from Blender.
- The bridge binds only to `127.0.0.1`.
- Add-on preferences can require a bearer token for HTTP bridge requests.
- MCP clients call `mcp_server.py`; they do not import Blender Python or touch `bpy`.
- Mutating helper tools still run inside Blender and use the live-preview/revert path.
- Generated arbitrary Python is normally staged with `draft_script` and must be approved in Blender. When the user grants a runtime external script trust window, `draft_script` auto-runs scripts that pass static checks until trust is revoked or expires.
- External script trust does not bypass animation workflow routing. Animation-like `draft_script` calls are refused until the client has run the Milestone 7 animation workflow and script fallback is allowed, or until the request states an explicit helper gap that workflow helpers cannot express.
- Viewport screenshots, sampled animation playblast frames, inspection renders, render thumbnails, and async render-job outputs exposed through MCP resources are local artifacts. Saved `.blend` files use a project-local `.claude_blender/captures/` folder by default, while unsaved or unwritable projects use Blender's extension user-data directory. Async render jobs launch a background Blender process from a temporary `.blend` copy and can be cancelled with `cancel_render_job` while the bridge session is tracking the process.
- External clients should surface tool calls clearly because MCP tools are model-controlled.

## Risk Checks

Flag or block proposed scripts that include:

- File deletion, overwrite, or broad filesystem traversal.
- Network calls from generated scripts.
- Shell/process execution.
- Dynamic imports, `exec`, `eval`, `compile`, or unsafe deserialization.
- Attempts to read environment variables or credential files.
- Large destructive scene operations without a checkpoint.
- Infinite loops or modal handlers that are hard to stop.
- Use of `bpy.ops` without clear context/mode reasoning.
- Deleting or renaming many objects, collections, materials, or actions.
- Mutating linked library data without warning.

These checks are guardrails, not a true sandbox. Blender Python runs with broad local privileges, so user approval and checkpointing remain essential.

Live-preview reverts return a rollback manifest and warnings when restoration is incomplete. This is visibility, not a guarantee that every possible Blender API mutation is reversible.

If a helper call opens a new preview transaction and then fails, the dispatcher auto-reverts that new transaction and reports `auto_reverted_preview` plus the rollback manifest in the failed tool result. A preview transaction that already existed before the failed call is preserved instead of being unwound.

## Safer Defaults

- Prefer helper tools for simple edits.
- Allow live preview only for typed helper tools with rollback support.
- Prefer direct `bpy.data` and RNA API changes over context-sensitive operators when possible.
- Require docs lookup before unfamiliar or version-sensitive scripting.
- Require a change plan before non-trivial generated Python.
- Keep arbitrary Python disabled for limited autonomous mode.

## Privacy Rules

- Do not store provider API keys in Blender Agent Bridge.
- Let users toggle screenshot inclusion.
- Let users choose whether file paths, object names, material names, and custom properties are sent.
- Do not send raw mesh data unless the user requests it.
- Do not send the full docs cache, full scene graph, or large tool output; send compact summaries and top matching snippets.
- Keep transcripts local by default.
- Warn before using beta file upload features with different retention behavior.

## Recovery

Before approved execution:

- Push an undo step when possible.
- Save a timestamped bridge-created `.blend` checkpoint when checkpoints are enabled.
- Record the generated script and result log locally.
- For external clients, require the approval token to match the current pending script and consume it before execution.
- If an external script trust window is active, auto-run `draft_script` calls after static checks pass and accept tokenless external execution only within the runtime grant for a currently staged script that still passes static checks.
- For animation-like scripts, enforce workflow-first routing before considering trust auto-run.

During live preview:

- Record before-state for each helper step.
- Keep the transaction pending until the user commits it.
- Provide a one-click revert for pending preview changes.
- Show rollback coverage and warnings after commit/revert.
- Escalate to approval-required mode when rollback state cannot be captured confidently.

After execution:

- Show success/failure clearly.
- Offer undo for the last action.
- Offer explicit restore of the last bridge-created checkpoint.
- Return execution errors and checkpoint status back through tool results so the external client can draft a repaired script without running it automatically.

## Documentation Access

Docs access should be restricted to official sources by default:

- `docs.blender.org`
- `projects.blender.org/blender`
- `developer.blender.org` only when API/manual docs are insufficient

The docs tool should return focused snippets and source URLs. It should not scrape unrelated web content in MVP.
