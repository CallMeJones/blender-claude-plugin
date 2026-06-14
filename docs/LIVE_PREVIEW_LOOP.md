# Live Preview Loop

## Goal

Changes should appear in Blender as soon as they are safe to apply. The user should be able to watch Claude build or adjust the scene, while still having an obvious way to commit, undo, or revert changes.

## Product Behavior

Live preview should feel like this:

1. User asks for a change.
2. Claude inspects scene context and chooses safe helper calls where possible.
3. The add-on applies each low-risk helper call immediately.
4. Blender's viewport, timeline, and relevant UI redraw.
5. The sidebar logs what changed and keeps `Commit`, `Revert`, and `Undo` available.

This is different from risky generated Python. Arbitrary scripts should still go through code preview and explicit approval unless the user intentionally changes the execution mode.

## Preview Transactions

A preview transaction groups one or more visible changes:

```text
preview_transaction
  id
  user_request
  started_at
  changed_data_blocks
  before_state
  applied_steps
  status: pending | committed | reverted | failed
```

The transaction manager should capture enough previous state to revert common helper changes. For large or risky changes, it should also save a `.blend` checkpoint.

Commit and revert results include a compact transaction manifest with created datablocks, modified datablocks, rollback scopes, changed datablocks, and applied step count. Revert also returns `rollback_warnings` when a target object, material, collection, socket, or node link could not be restored exactly.

## Immediate Helper Changes

These are good candidates for live preview:

- Object transforms.
- Object visibility, selection, and collection assignment.
- Material creation and assignment.
- Material scalar/color properties.
- Light creation and light settings.
- Camera creation and camera settings.
- Simple modifiers with bounded settings.
- Keyframes on object transforms, light energy/color, camera properties, and material values.

Current implemented helper actions:

- Move selected objects by location delta.
- Set selected object location, rotation, and/or scale.
- Create mesh primitives.
- Create empty helper objects.
- Set object visibility and viewport display settings.
- Assign/create material for selected mesh objects.
- Assign new emission material node setups.
- Create collections and link selected objects to them.
- Add bounded BEVEL, SUBSURF, SOLIDIFY, and ARRAY modifiers.
- Add Track To constraints to selected objects.
- Add light.
- Add camera.
- Set scene timeline range/current frame/FPS.
- Create simple selected-object transform keyframes.
- Create a keyframed camera orbit rig around a target object.
- Commit preview.
- Revert preview.

These should generally require approval before mutating:

- Deleting data-blocks.
- Renaming many objects.
- Applying destructive mesh operations.
- Running arbitrary generated Python.
- Importing/exporting files.
- Editing linked library data.
- Adding drivers or modal handlers.
- Broad animation rewrites across many actions.

## Blender Update Loop

All scene mutations should happen on Blender's main thread. After applying a preview step, the add-on should refresh the dependency graph and request UI redraws for relevant areas. The implementation should centralize this in `live_preview.py` so every helper gets consistent behavior.

Expected implementation responsibilities:

- Apply helper changes on the main thread.
- Record rollback state before mutation.
- Push undo/checkpoint state at transaction boundaries.
- Include rollback coverage in tool results so external clients and the sidebar can show what was protected.
- Update scene/view layer state after mutation.
- Request redraw for 3D View, Timeline, Graph Editor, Dope Sheet, and Properties areas when relevant.
- Report success/failure back into the Claude tool loop.

## Animation Preview

For animation edits:

- Insert or update keyframes immediately.
- Show changed frame numbers in the sidebar.
- Optionally jump to the first changed frame.
- Optionally play a short preview range after commit.
- Keep revert available before the transaction is committed.

## UX Controls

The sidebar should expose:

- Live preview toggle.
- Execution mode: suggest-only, approval-required, live helpers, advanced.
- Current preview transaction status.
- Changed objects/actions/materials list.
- Running status/log text for live helper steps.
- Commit button.
- Revert button.
- Undo last step button.

## Safety Boundary

Live preview does not mean unchecked autonomy. It means safe, typed changes can be applied visibly and reversibly. Generated Python remains approval-gated by default.
