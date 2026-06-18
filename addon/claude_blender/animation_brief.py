"""Structured animation brief and prompt-contract helpers."""

from __future__ import annotations

import hashlib
import re


COUNT_WORDS = {
    "once": 1,
    "one": 1,
    "twice": 2,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}

ACTION_KEYWORDS = (
    ("bounce", "bounce"),
    ("bounces", "bounce"),
    ("bounced", "bounce"),
    ("bouncing", "bounce"),
    ("jump", "jump"),
    ("jumps", "jump"),
    ("jumped", "jump"),
    ("jumping", "jump"),
    ("leap", "jump"),
    ("leaps", "jump"),
    ("leaping", "jump"),
    ("fall", "fall"),
    ("falls", "fall"),
    ("falling", "fall"),
    ("drop", "fall"),
    ("drops", "fall"),
    ("dropped", "fall"),
    ("dropping", "fall"),
    ("orbit", "orbit"),
    ("orbits", "orbit"),
    ("orbiting", "orbit"),
    ("turntable", "turntable"),
    ("rotate", "rotate"),
    ("rotates", "rotate"),
    ("rotated", "rotate"),
    ("rotating", "rotate"),
    ("spin", "rotate"),
    ("spins", "rotate"),
    ("spinning", "rotate"),
    ("follow path", "follow path"),
    ("path", "follow path"),
    ("reveal", "reveal"),
    ("reveals", "reveal"),
    ("revealed", "reveal"),
    ("revealing", "reveal"),
    ("appear", "reveal"),
    ("appears", "reveal"),
    ("appeared", "reveal"),
    ("appearing", "reveal"),
    ("pulse", "pulse"),
    ("pulses", "pulse"),
    ("pulsing", "pulse"),
    ("flash", "pulse"),
    ("flashes", "pulse"),
    ("flashing", "pulse"),
    ("move", "move"),
    ("moves", "move"),
    ("moving", "move"),
    ("slide", "move"),
    ("slides", "move"),
    ("sliding", "move"),
)

BRIEF_INTENT_PHRASES = (
    "animation brief",
    "prompt contract",
    "success criteria",
    "validation criteria",
)

ANIMATION_EDIT_WORDS = (
    "animate",
    "animation",
    "make",
    "create",
    "add",
    "have",
    "turn",
    "block",
    "blocking",
)

READ_ONLY_ANIMATION_WORDS = (
    "what",
    "show",
    "list",
    "inspect",
    "details",
    "summary",
    "summarize",
    "summarise",
)


def _as_string_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    result = []
    for item in value:
        text = str(item).strip()
        if text:
            result.append(text)
    return result


def _optional_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _infer_count(prompt):
    text = prompt.lower()
    digit_match = re.search(r"\b(\d{1,2})\s*(?:x|times?|bounces?|jumps?|loops?|cycles?)\b", text)
    if digit_match:
        return int(digit_match.group(1))
    if re.search(r"\bonce\b", text):
        return 1
    if re.search(r"\btwice\b", text):
        return 2
    for word, count in COUNT_WORDS.items():
        if word in {"once", "twice"}:
            continue
        if re.search(rf"\b{re.escape(word)}\s+(?:times?|bounces?|jumps?|loops?|cycles?)\b", text):
            return count
    return None


def _has_action_keyword(text, keyword):
    if " " in keyword:
        return keyword in text
    return re.search(rf"\b{re.escape(keyword)}\b", text) is not None


def _infer_action(prompt, explicit_action=""):
    if explicit_action:
        return str(explicit_action).strip()
    text = prompt.lower()
    for keyword, action in ACTION_KEYWORDS:
        if _has_action_keyword(text, keyword):
            return action
    return ""


def should_create_brief(prompt):
    text = str(prompt or "").lower()
    if any(phrase in text for phrase in BRIEF_INTENT_PHRASES):
        return True
    if re.search(r"\banimate\b", text) and not any(re.search(rf"\b{word}\b", text) for word in READ_ONLY_ANIMATION_WORDS):
        return True
    action = _infer_action(text)
    if not action:
        return False
    if _infer_count(text) is not None or _infer_secondary_actions(text):
        return True
    return any(re.search(rf"\b{re.escape(word)}\b", text) for word in ANIMATION_EDIT_WORDS)


def _infer_secondary_actions(prompt):
    text = prompt.lower()
    secondary = []
    if any(phrase in text for phrase in ("get smaller", "gets smaller", "getting smaller", "shrink", "shrinks", "scale down")):
        secondary.append("scale decreases over the animation")
    if any(phrase in text for phrase in ("get bigger", "gets bigger", "grow", "grows", "scale up")):
        secondary.append("scale increases over the animation")
    if any(phrase in text for phrase in ("fade", "transparent", "disappear")):
        secondary.append("visibility or material alpha changes over the animation")
    if any(phrase in text for phrase in ("glow", "pulse", "flash")):
        secondary.append("emission or brightness changes over the animation")
    return secondary


def _resolve_subjects(context, names):
    resolved = []
    missing = []
    for name in names:
        obj = context.blend_data.objects.get(name)
        if obj:
            resolved.append(
                {
                    "name": obj.name,
                    "type": obj.type,
                    "selected": bool(obj.select_get()),
                    "has_animation_data": bool(getattr(obj, "animation_data", None)),
                }
            )
        else:
            missing.append(name)
    return resolved, missing


def _default_subject_names(context):
    selected = [obj.name for obj in getattr(context, "selected_objects", [])]
    if selected:
        return selected
    active = getattr(context, "active_object", None)
    return [active.name] if active else []


def clarification_question(brief):
    subject_names = brief.get("subject_names") or []
    subject_label = ", ".join(subject_names) if subject_names else "the subject"
    ambiguities = " ".join(str(item) for item in brief.get("ambiguities") or []).lower()
    if "subject" in ambiguities:
        return "Which object should I animate?"
    if "action" in ambiguities:
        return f"What action should {subject_label} perform?"
    first = next((str(item).strip() for item in brief.get("ambiguities") or [] if str(item).strip()), "")
    return first or "What should I clarify before creating this animation?"


def _note_list(notes):
    if notes is None:
        return []
    if isinstance(notes, str):
        notes = [notes]
    return [str(item) for item in notes if str(item).strip()]


def _pose(frame, label, role, notes=None, *, hold_frames=0):
    return {
        "frame": int(frame),
        "label": str(label),
        "role": str(role),
        "hold_frames": max(0, int(hold_frames or 0)),
        "notes": _note_list(notes),
    }


def _even_frame(start, end, index, steps):
    if steps <= 0:
        return int(start)
    return int(round(start + (end - start) * (index / steps)))


def _default_key_poses(brief, frame_start, frame_end):
    action = str(brief.get("action") or "").lower()
    count = brief.get("timing", {}).get("requested_count") or 1
    count = max(1, min(12, int(count)))
    secondary = brief.get("secondary_actions") or []
    secondary_notes = [f"Also show: {item}." for item in secondary]
    if action in {"bounce", "jump"}:
        poses = [_pose(frame_start, "contact_start", "contact", ["Start grounded and readable."])]
        total_segments = count * 2
        for cycle in range(count):
            apex = _even_frame(frame_start, frame_end, cycle * 2 + 1, total_segments)
            contact = _even_frame(frame_start, frame_end, cycle * 2 + 2, total_segments)
            poses.append(_pose(apex, f"apex_{cycle + 1}", "breakdown", ["Highest point of the arc.", *secondary_notes]))
            poses.append(_pose(contact, f"contact_{cycle + 1}", "contact", ["Return to contact; show weight.", *secondary_notes], hold_frames=2))
        poses.append(_pose(frame_end, "settle", "settle", ["Small settle after the final contact."]))
        return poses
    if action in {"rotate", "turntable", "orbit"}:
        return [
            _pose(frame_start, "start_angle", "key", ["Readable starting silhouette."]),
            _pose(_even_frame(frame_start, frame_end, 1, 2), "half_turn", "breakdown", ["Midpoint spacing check."]),
            _pose(frame_end, "end_angle", "key", ["Return to final readable angle."]),
        ]
    if action == "reveal":
        return [
            _pose(frame_start, "hidden", "key", ["Object starts hidden or tiny."]),
            _pose(_even_frame(frame_start, frame_end, 1, 2), "readable_breakdown", "breakdown", ["Reveal shape becomes clear."]),
            _pose(frame_end, "fully_revealed", "key", ["Final pose is readable."]),
        ]
    return [
        _pose(frame_start, "start", "key", ["Initial pose."]),
        _pose(_even_frame(frame_start, frame_end, 1, 2), "breakdown", "breakdown", ["Main spacing/readability check."]),
        _pose(frame_end, "end", "key", ["Final pose."]),
    ]


def create_timing_chart(
    context,
    *,
    prompt="",
    brief=None,
    subject_names=None,
    frame_start=None,
    frame_end=None,
    beats=None,
):
    if not isinstance(brief, dict):
        brief_result = create_animation_brief(
            context,
            prompt=prompt,
            subject_names=subject_names,
            frame_start=frame_start,
            frame_end=frame_end,
        )
        if not brief_result.get("ok"):
            return brief_result
        brief = brief_result["brief"]
    timing = brief.get("timing") or {}
    frame_start = _optional_int(frame_start, timing.get("frame_start", context.scene.frame_start))
    frame_end = _optional_int(frame_end, timing.get("frame_end", context.scene.frame_end))
    if frame_end <= frame_start:
        frame_end = frame_start + 24
    key_poses = []
    for beat in beats or []:
        if not isinstance(beat, dict):
            continue
        key_poses.append(
            _pose(
                _optional_int(beat.get("frame"), frame_start),
                beat.get("label") or f"pose_{len(key_poses) + 1}",
                beat.get("role") or "key",
                beat.get("notes") or [],
                hold_frames=beat.get("hold_frames", 0),
            )
        )
    if not key_poses:
        key_poses = _default_key_poses(brief, frame_start, frame_end)
    key_poses = sorted(key_poses, key=lambda item: (item["frame"], item["label"]))
    chart = {
        "brief_contract_id": brief.get("contract_id", ""),
        "subject_names": brief.get("subject_names") or [],
        "action": brief.get("action", ""),
        "frame_start": frame_start,
        "frame_end": frame_end,
        "key_poses": key_poses,
        "spacing_notes": [
            "Block key/contact poses first; polish interpolation only after the pose plan reads clearly.",
            "Use holds for contact/readability, then add breakdowns for spacing and arcs.",
        ],
        "ready_for_blocking": bool(brief.get("ready_for_generation")) and bool(key_poses),
        "clarification_needed": bool(brief.get("clarification_needed")),
        "clarification_question": clarification_question(brief) if brief.get("clarification_needed") else "",
    }
    return {"ok": True, "message": "Created animation timing chart", "chart": chart, "brief": brief}


def create_animation_brief(
    context,
    *,
    prompt,
    subject_names=None,
    action="",
    style="",
    camera="",
    frame_start=None,
    frame_end=None,
    constraints=None,
    success_criteria=None,
):
    prompt = str(prompt or "").strip()
    if not prompt:
        return {"ok": False, "message": "An animation prompt is required to create a brief"}

    scene = context.scene
    explicit_subjects = _as_string_list(subject_names)
    subject_names = explicit_subjects or _default_subject_names(context)
    subjects, missing_subjects = _resolve_subjects(context, subject_names)
    frame_start = _optional_int(frame_start, scene.frame_start)
    frame_end = _optional_int(frame_end, scene.frame_end)
    if frame_end <= frame_start:
        frame_end = frame_start + 24
    fps = int(getattr(scene.render, "fps", 24) or 24)
    duration_frames = max(1, frame_end - frame_start)
    count = _infer_count(prompt)
    action = _infer_action(prompt, action)
    style = str(style or "").strip()
    camera = str(camera or (scene.camera.name if scene.camera else "")).strip()
    constraints = _as_string_list(constraints)
    user_criteria = _as_string_list(success_criteria)
    secondary_actions = _infer_secondary_actions(prompt)

    assumptions = []
    ambiguities = []
    if subject_names and not explicit_subjects:
        assumptions.append("Using the current Blender selection as the animation subject.")
    if not subjects:
        ambiguities.append("No existing Blender object is resolved as the animation subject.")
    if missing_subjects:
        ambiguities.append(f"Subject objects were not found: {', '.join(missing_subjects)}.")
    if not action:
        ambiguities.append("The main animation action is not explicit enough to choose a helper.")
    if not camera:
        assumptions.append("No active scene camera is available; camera framing must be planned before visual review.")
    else:
        assumptions.append(f"Use camera '{camera}' for staging/framing checks.")
    if frame_start == scene.frame_start and frame_end == scene.frame_end:
        assumptions.append("Using the current scene frame range for timing.")

    requirements = [
        {
            "id": "subject",
            "text": "Animate the resolved subject object(s).",
            "subjects": [item["name"] for item in subjects],
        },
        {
            "id": "action",
            "text": f"Primary action: {action or 'unspecified'}.",
            "action": action,
        },
        {
            "id": "timing",
            "text": f"Animation runs from frame {frame_start} to {frame_end}.",
            "frame_start": frame_start,
            "frame_end": frame_end,
            "duration_frames": duration_frames,
            "duration_seconds": round(duration_frames / max(1, fps), 3),
        },
    ]
    if count is not None:
        requirements.append({"id": "count", "text": f"Requested count: {count}.", "count": count})
    for index, secondary in enumerate(secondary_actions, start=1):
        requirements.append({"id": f"secondary_{index}", "text": secondary})
    if style:
        requirements.append({"id": "style", "text": f"Style/read: {style}.", "style": style})
    if constraints:
        requirements.append({"id": "constraints", "text": "Respect explicit constraints.", "constraints": constraints})

    criteria = list(user_criteria)
    if subjects:
        criteria.append("Subject object remains identifiable throughout the shot.")
    if action:
        criteria.append(f"Visible motion clearly reads as {action}.")
    if count is not None:
        criteria.append(f"The requested action count is exactly {count}.")
    criteria.extend(f"Secondary requirement is visible: {secondary}." for secondary in secondary_actions)
    if camera:
        criteria.append("Camera keeps the subject framed during the required action.")
    if action in {"bounce", "jump", "fall"}:
        criteria.append("Contact, weight, and settle are physically plausible for the scene scale.")

    contract_seed = "|".join(
        [
            prompt,
            ",".join(subject_names),
            action,
            str(frame_start),
            str(frame_end),
            str(count or ""),
        ]
    )
    contract_id = "anim-" + hashlib.sha1(contract_seed.encode("utf-8")).hexdigest()[:12]
    subject_label = ", ".join(item["name"] for item in subjects) or "unresolved subject"
    interpretation = f"Animate {subject_label} to {action or 'perform the requested action'} from frame {frame_start} to {frame_end}."
    if count is not None:
        interpretation += f" The action should happen {count} time(s)."

    brief = {
        "contract_id": contract_id,
        "prompt": prompt,
        "subject_names": subject_names,
        "subjects": subjects,
        "missing_subjects": missing_subjects,
        "action": action,
        "secondary_actions": secondary_actions,
        "style": style,
        "camera": camera,
        "timing": {
            "frame_start": frame_start,
            "frame_end": frame_end,
            "duration_frames": duration_frames,
            "fps": fps,
            "duration_seconds": round(duration_frames / max(1, fps), 3),
            "requested_count": count,
        },
        "constraints": constraints,
        "requirements": requirements,
        "success_criteria": criteria,
        "assumptions": assumptions,
        "ambiguities": ambiguities,
        "clarification_needed": bool(ambiguities),
        "ready_for_generation": not bool(ambiguities),
        "user_visible_interpretation": interpretation,
        "validation_plan": {
            "check_subject_visibility": bool(subjects),
            "check_action_count": count is not None,
            "check_camera_framing": bool(camera),
            "check_contact_physics": action in {"bounce", "jump", "fall"},
            "compare_against_prompt": True,
        },
    }
    return {
        "ok": True,
        "message": "Created animation brief prompt contract",
        "brief": brief,
    }
