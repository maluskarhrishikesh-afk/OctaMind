from __future__ import annotations

from typing import Any, Dict, List, Optional


def clamp_confidence(value: Any) -> float:
    try:
        numeric = float(value)
    except Exception:
        return 0.0
    return max(0.0, min(numeric, 1.0))


def confidence_label(confidence: Any) -> str:
    score = clamp_confidence(confidence)
    if score >= 0.9:
        return "high"
    if score >= 0.75:
        return "medium"
    return "low"


def risk_label(confidence: Any, safe_to_apply: bool = True) -> str:
    if not safe_to_apply:
        return "advisory"
    label = confidence_label(confidence)
    if label == "high":
        return "low"
    if label == "medium":
        return "medium"
    return "high"


def confidence_badge(confidence: Any) -> str:
    score = clamp_confidence(confidence)
    return f"{confidence_label(score)} confidence ({score:.2f})"


def build_execution_step(
    *,
    step_id: str,
    description: str,
    confidence: float,
    why: Optional[List[str]] = None,
    safe_to_apply: bool = True,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    score = clamp_confidence(confidence)
    step: Dict[str, Any] = {
        "id": step_id,
        "description": description,
        "confidence": score,
        "confidence_label": confidence_label(score),
        "risk_level": risk_label(score, safe_to_apply=safe_to_apply),
        "safe_to_apply": bool(safe_to_apply),
        "requires_confirmation": (not safe_to_apply) or score < 0.9,
        "why": [item for item in (why or []) if str(item or "").strip()],
    }
    if isinstance(metadata, dict):
        for key, value in metadata.items():
            step[key] = value
    return step


def build_execution_plan(
    *,
    goal: str,
    steps: List[Dict[str, Any]],
    requires_confirmation: Optional[bool] = None,
) -> Dict[str, Any]:
    safe_steps = [step for step in steps if isinstance(step, dict) and step.get("safe_to_apply")]
    confidence_values = [clamp_confidence(step.get("confidence", 0.0)) for step in safe_steps]
    overall_confidence = min(confidence_values) if confidence_values else 1.0

    if requires_confirmation is None:
        requires_confirmation = any(
            str(step.get("risk_level", "") or "") in {"medium", "high"}
            for step in safe_steps
        )

    if any(str(step.get("risk_level", "") or "") == "high" for step in safe_steps):
        overall_risk = "high"
    elif requires_confirmation:
        overall_risk = "medium"
    else:
        overall_risk = "low"

    return {
        "goal": goal,
        "requires_confirmation": bool(requires_confirmation),
        "confidence": overall_confidence,
        "confidence_label": confidence_label(overall_confidence),
        "risk_level": overall_risk,
        "step_count": len(steps),
        "safe_step_count": len(safe_steps),
        "steps": steps,
    }


def format_execution_summary(
    plan: Dict[str, Any],
    *,
    heading: str = "Execution plan",
    include_step_reasons: bool = False,
    max_reasons_per_step: int = 2,
) -> str:
    lines = [
        f"{heading}:",
        f"Goal: {str(plan.get('goal', 'Complete the requested task.'))}",
        f"Confidence: {confidence_badge(plan.get('confidence', 0.0))}",
        f"Risk posture: {str(plan.get('risk_level', 'medium') or 'medium')}",
    ]
    if plan.get("requires_confirmation"):
        lines.append("Confirmation posture: confirmation recommended for medium/high-risk actions.")
    else:
        lines.append("Confirmation posture: low-risk execution path.")

    steps = plan.get("steps", []) if isinstance(plan.get("steps"), list) else []
    if steps:
        lines.append("Steps:")
        for index, step in enumerate(steps, start=1):
            lines.append(
                f"{index}. {step.get('description', '')} [{confidence_label(step.get('confidence', 0.0))} confidence | {step.get('risk_level', 'medium')} risk]"
            )
            if include_step_reasons:
                why_lines = step.get("why", []) if isinstance(step.get("why"), list) else []
                for reason in why_lines[:max_reasons_per_step]:
                    lines.append(f"   - {reason}")
    return "\n".join(lines)


def attach_execution_plan(
    result: Dict[str, Any],
    plan: Dict[str, Any],
    *,
    include_summary: bool = False,
    heading: str = "Execution plan",
    include_step_reasons: bool = False,
) -> Dict[str, Any]:
    updated = dict(result or {})
    updated["execution_plan"] = plan
    if include_summary:
        message = str(updated.get("message", "") or "").strip()
        if message:
            updated["message"] = (
                f"{message}\n\n"
                f"{format_execution_summary(plan, heading=heading, include_step_reasons=include_step_reasons)}"
            )
    return updated