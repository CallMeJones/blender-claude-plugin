"""Milestone 7 animation workflow orchestration helpers."""

from __future__ import annotations

from . import animation_brief, world_model


def _as_string_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item)]
    return []


def _optional_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _tool_call(name, arguments, *, reason="", mutates_scene=False, requires_live_preview=False):
    return {
        "name": name,
        "input": dict(arguments or {}),
        "reason": reason,
        "mutates_scene": bool(mutates_scene),
        "requires_live_preview": bool(requires_live_preview),
    }


def _step(phase, status, title, *, tool_call=None, result_key="", notes=None):
    item = {
        "phase": phase,
        "status": status,
        "title": title,
    }
    if tool_call:
        item["tool_call"] = tool_call
    if result_key:
        item["result_key"] = result_key
    if notes:
        item["notes"] = list(notes)
    return item


def _brief_subject_names(brief):
    names = _as_string_list((brief or {}).get("subject_names"))
    if names:
        return names
    return [
        str(item.get("name"))
        for item in ((brief or {}).get("subjects") or [])
        if isinstance(item, dict) and item.get("name")
    ]


def _frame_range(context, brief, frame_start=None, frame_end=None):
    timing = (brief or {}).get("timing") if isinstance(brief, dict) else {}
    if not isinstance(timing, dict):
        timing = {}
    start = _optional_int(frame_start, timing.get("frame_start", context.scene.frame_start))
    end = _optional_int(frame_end, timing.get("frame_end", context.scene.frame_end))
    if end <= start:
        end = start + 24
    return start, end


def _requested_count(brief, default=1):
    timing = (brief or {}).get("timing") if isinstance(brief, dict) else {}
    if not isinstance(timing, dict):
        timing = {}
    count = timing.get("requested_count")
    try:
        return max(1, int(count))
    except (TypeError, ValueError):
        return int(default)


def _primary_subject(subject_names):
    return subject_names[0] if subject_names else ""


def _generation_tool_calls(brief, chart, *, frame_start, frame_end):
    subject_names = _brief_subject_names(brief)
    primary = _primary_subject(subject_names)
    action = str((brief or {}).get("action") or "").lower()
    secondary_actions = [str(item).lower() for item in ((brief or {}).get("secondary_actions") or [])]
    calls = []
    blockers = []

    if subject_names:
        calls.append(
            _tool_call(
                "select_objects",
                {"object_names": subject_names, "active_object_name": primary, "replace": True},
                reason="Select the resolved animation subject before applying selected-object helpers.",
                mutates_scene=True,
            )
        )
    calls.append(
        _tool_call(
            "set_scene_frame_range",
            {"frame_start": frame_start, "frame_end": frame_end, "current_frame": frame_start},
            reason="Align the scene timeline to the animation brief before keying.",
            mutates_scene=True,
            requires_live_preview=True,
        )
    )
    calls.append(
        _tool_call(
            "set_animation_preview_range",
            {"frame_start": frame_start, "frame_end": frame_end, "current_frame": frame_start},
            reason="Make playback focus on the contracted shot range.",
            mutates_scene=True,
            requires_live_preview=True,
        )
    )

    if action in {"bounce", "jump"}:
        calls.append(
            _tool_call(
                "animate_object_bounce",
                {
                    "object_name": primary,
                    "frame_start": frame_start,
                    "frame_end": frame_end,
                    "axis": "Z",
                    "cycles": _requested_count(brief, default=2),
                    "interpolation": "BEZIER",
                },
                reason="Use the bounded bounce helper for the primary vertical motion.",
                mutates_scene=True,
                requires_live_preview=True,
            )
        )
    elif action in {"rotate", "turntable"}:
        calls.append(
            _tool_call(
                "create_turntable_animation",
                {
                    "object_name": primary,
                    "frame_start": frame_start,
                    "frame_end": frame_end,
                    "axis": "Z",
                    "revolutions": 1.0,
                    "add_cycles": False,
                },
                reason="Use the bounded turntable helper for rotation timing.",
                mutates_scene=True,
                requires_live_preview=True,
            )
        )
    elif action == "reveal":
        calls.append(
            _tool_call(
                "create_reveal_animation",
                {"object_name": primary, "frame_start": frame_start, "frame_end": frame_end},
                reason="Use the bounded reveal helper for scale/visibility reveal.",
                mutates_scene=True,
                requires_live_preview=True,
            )
        )
    elif action == "pulse":
        calls.append(
            _tool_call(
                "create_pulse_animation",
                {"object_name": primary, "frame_start": frame_start, "frame_end": frame_end},
                reason="Use the bounded pulse helper for scale/emphasis motion.",
                mutates_scene=True,
                requires_live_preview=True,
            )
        )
    else:
        blockers.append(
            "No single high-level helper confidently matches the primary action; use the timing chart to plan concrete block_key_poses poses before scripting."
        )

    if any("scale decreases" in item or "get smaller" in item or "smaller" in item for item in secondary_actions):
        blockers.append(
            "Secondary scale decrease requires explicit scale poses or a purpose-built helper; do not skip brief, scene context, and timing chart before using draft_script."
        )
    if chart and not ((chart or {}).get("ready_for_blocking")):
        blockers.append("Timing chart is not ready for blocking; resolve clarification before mutating.")
    return calls, blockers


def _review_tool_calls(brief, *, prompt, frame_start, frame_end, playblast=None, findings=None):
    subject_names = _brief_subject_names(brief)
    calls = [
        _tool_call(
            "analyze_animation_principles",
            {
                "object_names": subject_names,
                "prompt": prompt,
                "brief": brief,
                "frame_start": frame_start,
                "frame_end": frame_end,
            },
            reason="Evaluate timing, spacing, arcs, pose clarity, contact, and settle against the brief.",
        ),
        _tool_call(
            "compare_animation_to_brief",
            {
                "brief": brief,
                "prompt": prompt,
                "subject_names": subject_names,
                "frame_start": frame_start,
                "frame_end": frame_end,
            },
            reason="Run prompt-contract and sampled-state validation.",
        ),
        _tool_call(
            "capture_animation_playblast",
            {
                "frame_start": frame_start,
                "frame_end": frame_end,
                "brief": str((brief or {}).get("user_visible_interpretation") or prompt),
            },
            reason="Capture visual frame evidence in an interactive Blender session.",
        ),
    ]
    review_input = {"brief": brief, "prompt": prompt}
    if isinstance(playblast, dict):
        review_input["playblast"] = playblast
    calls.append(
        _tool_call(
            "review_playblast_against_brief",
            review_input,
            reason="Compare visual frame evidence and current animation state to the brief.",
        )
    )
    if findings:
        calls.append(
            _tool_call(
                "repair_animation_from_findings",
                {"findings": findings, "brief": brief},
                reason="Convert structured evaluator findings into targeted repair operations.",
            )
        )
        calls.append(
            _tool_call(
                "run_animation_repair_loop",
                {
                    "brief": brief,
                    "prompt": prompt,
                    "findings": findings,
                    "max_iterations": 2,
                    "max_operations": 4,
                    "apply_mutating_repairs": True,
                },
                reason="Apply bounded preview-safe repair operations and re-review.",
                mutates_scene=True,
                requires_live_preview=True,
            )
        )
    return calls


def _script_fallback_policy(brief, generation_blockers):
    clarification_needed = bool((brief or {}).get("clarification_needed"))
    allowed = not clarification_needed
    return {
        "allowed": allowed,
        "allowed_after": [
            "create_animation_brief",
            "get_animation_scene_context",
            "create_timing_chart",
            "attempt_or_rule_out_generation_helpers",
            "run_evaluator_or_playblast_review_when checking was requested",
        ],
        "preferred_before_script": [
            "set_scene_frame_range",
            "set_animation_preview_range",
            "animate_object_bounce",
            "create_turntable_animation",
            "create_reveal_animation",
            "create_pulse_animation",
            "block_key_poses",
            "run_animation_repair_loop",
        ],
        "valid_reasons": [
            "No helper can express the required secondary motion or data operation.",
            "The timing chart requires explicit transforms that the client can only construct safely in Python.",
            "A repair operation is under-specified for helpers and needs one cohesive checkpoint-backed script.",
        ],
        "not_allowed_for": [
            "Skipping the animation brief or scene routing context.",
            "Skipping validation when the user asked to check the result.",
            "Running scripts that fail static checks.",
        ],
        "current_blockers": list(generation_blockers),
    }


def plan_animation_workflow(
    context,
    *,
    prompt,
    subject_names=None,
    frame_start=None,
    frame_end=None,
    mode="full",
    selected_only=False,
    max_objects=20,
    brief=None,
    timing_chart=None,
    playblast=None,
    findings=None,
):
    prompt = str(prompt or "").strip()
    if not prompt:
        return {"ok": False, "message": "An animation prompt is required"}

    subject_names = _as_string_list(subject_names)
    mode = str(mode or "full").strip().lower()
    if mode not in {"generate", "review", "repair", "full"}:
        mode = "full"

    brief_result = None
    if isinstance(brief, dict):
        brief_data = dict(brief)
    else:
        brief_result = animation_brief.create_animation_brief(
            context,
            prompt=prompt,
            subject_names=subject_names,
            frame_start=frame_start,
            frame_end=frame_end,
        )
        if not brief_result.get("ok"):
            return brief_result
        brief_data = brief_result["brief"]
    if not subject_names:
        subject_names = _brief_subject_names(brief_data)

    frame_start, frame_end = _frame_range(context, brief_data, frame_start=frame_start, frame_end=frame_end)
    scene_context = world_model.animation_scene_context(
        context,
        object_names=subject_names,
        selected_only=bool(selected_only),
        max_objects=max_objects,
    )
    if isinstance(timing_chart, dict):
        timing_result = {"ok": True, "message": "Using caller-provided timing chart", "chart": timing_chart, "brief": brief_data}
        chart = timing_chart
    else:
        timing_result = animation_brief.create_timing_chart(
            context,
            prompt=prompt,
            brief=brief_data,
            subject_names=subject_names,
            frame_start=frame_start,
            frame_end=frame_end,
        )
        if not timing_result.get("ok"):
            return timing_result
        chart = timing_result["chart"]

    generation_calls, generation_blockers = _generation_tool_calls(
        brief_data,
        chart,
        frame_start=frame_start,
        frame_end=frame_end,
    )
    findings_list = findings if isinstance(findings, list) else []
    review_calls = _review_tool_calls(
        brief_data,
        prompt=prompt,
        frame_start=frame_start,
        frame_end=frame_end,
        playblast=playblast if isinstance(playblast, dict) else None,
        findings=findings_list,
    )

    clarification_needed = bool(brief_data.get("clarification_needed"))
    next_tool_calls = []
    if not clarification_needed:
        if mode in {"generate", "full"}:
            next_tool_calls.extend(generation_calls)
        if mode in {"review", "repair", "full"}:
            next_tool_calls.extend(review_calls)
    status = "needs_clarification" if clarification_needed else "ready"
    if generation_blockers and mode in {"generate", "full"} and not clarification_needed:
        status = "ready_with_helper_gaps"

    steps = [
        _step(
            "contract",
            "completed",
            "Create the animation brief / prompt contract",
            tool_call=_tool_call(
                "create_animation_brief",
                {
                    "prompt": prompt,
                    "subject_names": subject_names,
                    "frame_start": frame_start,
                    "frame_end": frame_end,
                },
                reason="Establish subjects, action, timing, success criteria, and ambiguity before editing.",
            ),
            result_key="brief",
        ),
        _step(
            "scene_context",
            "completed",
            "Route animation targets from scene context",
            tool_call=_tool_call(
                "get_animation_scene_context",
                {"object_names": subject_names, "selected_only": bool(selected_only), "max_objects": max_objects},
                reason="Choose object transforms, rig controls, shape keys, materials, physics, or camera targets deliberately.",
            ),
            result_key="scene_context",
        ),
        _step(
            "timing",
            "completed",
            "Create timing chart and blocking plan",
            tool_call=_tool_call(
                "create_timing_chart",
                {"prompt": prompt, "brief": brief_data, "subject_names": subject_names, "frame_start": frame_start, "frame_end": frame_end},
                reason="Plan keys, contacts, holds, breakdowns, and spacing before mutation.",
            ),
            result_key="timing_chart",
        ),
    ]
    if clarification_needed:
        steps.append(
            _step(
                "clarify",
                "needs_input",
                "Ask a concise clarifying question before generating animation",
                notes=[animation_brief.clarification_question(brief_data)],
            )
        )
    else:
        steps.append(
            _step(
                "generate",
                "recommended_next",
                "Apply helper-based generation before script fallback",
                notes=generation_blockers or ["Use the next_tool_calls generation helpers in order."],
            )
        )
        steps.append(
            _step(
                "evaluate",
                "recommended_after_generation",
                "Evaluate keyed data, playblast evidence, and prompt-contract fit",
                notes=["Use evaluator output findings as input to repair_animation_from_findings or run_animation_repair_loop."],
            )
        )

    workflow = {
        "workflow_id": str(brief_data.get("contract_id") or ""),
        "mode": mode,
        "status": status,
        "prompt": prompt,
        "brief": brief_data,
        "scene_context": scene_context,
        "timing_chart": chart,
        "steps": steps,
        "next_tool_calls": next_tool_calls,
        "generation_blockers": generation_blockers,
        "script_fallback_policy": _script_fallback_policy(brief_data, generation_blockers),
        "mcp_client_guidance": [
            "Call plan_animation_workflow first for animation generation, review, or repair tasks.",
            "Follow next_tool_calls in order; do not call draft_script before the workflow has produced brief, scene context, and timing chart.",
            "Leave helper mutations in preview state unless the user explicitly asks to commit or revert.",
            "Use draft_script only for the specific helper gaps listed in script_fallback_policy.",
        ],
    }
    return {
        "ok": True,
        "message": "Planned Milestone 7 animation workflow",
        "workflow": workflow,
        "brief_result": brief_result or {"ok": True, "message": "Using caller-provided brief", "brief": brief_data},
        "timing_result": timing_result,
    }
