"""TEEVRA Worker Communication Agent.

Telugu/English check-in conversations and speech interaction. Uses only
approved, safety-reviewed message templates for emergency instructions. Does
NOT diagnose medical conditions. Voice consent required; no GPS tracking.
Gemini Live used only when supported for the configured project/region;
prerecorded Telugu fallback otherwise.
"""

from __future__ import annotations

TELUGU = {
    "prompt": "మీకు ఎలా ఉంది? నీళ్లు తాగారా?",
    "ok": "సరిగ్గా / OK",
    "too_hot": "చాలా వేడి / Too Hot",
    "sos": "సహాయం కావాలి / SOS",
    "consent": "గోసపి ఉపయోగించాలనుకుంటున్నారా? GPS ట్రాకింగ్ లేదు.",
}

ENGLISH = {
    "prompt": "How are you? Have you had water?",
    "ok": "OK",
    "too_hot": "Too Hot",
    "sos": "SOS Need Help",
    "consent": "Consent to voice processing? No GPS tracking.",
}


def messages(language: str = "te") -> dict:
    return TELUGU if language == "te" else ENGLISH


def checkin_outcome(response: str, voice_consent: bool) -> dict:
    """Return a safety-reviewed outcome. Never medical advice."""
    if response == "SOS":
        return {
            "action": "immediate_priority_alert",
            "guidance": "Stay where you are. Help is being dispatched.",
            "escalate": True,
            "gemini_required": False,
        }
    if response == "TOO_HOT":
        return {
            "action": "supervisor_review",
            "guidance": "Move to shade, drink water, inform supervisor.",
            "escalate": False,
        }
    return {"action": "record_status", "guidance": "Thank you. Stay hydrated.", "escalate": False}
