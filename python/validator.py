import copy
import logging
import re

log = logging.getLogger("thea.validator")

_DIGIT_RE = re.compile(r'\b\d+(?:\.\d+)?%?|\b\d+/\d+\b')
_PROTECTED = frozenset([
    "ethnic", "race", "racial", "gender", "religion", "nationality",
    "disability", "pregnancy", "sexual orientation",
])
_COMMAND_RE = re.compile(
    r'\b(take|avoid|stop|start|use|apply|consult|see a doctor|call|go to)\b',
    re.IGNORECASE,
)


class ValidationError(Exception):
    pass


def validate(
    response: dict,
    band: str,
    channel_open: bool,
) -> dict:
    r = copy.deepcopy(response)

    # Guard 1: channel closed → speech null
    if not channel_open:
        r["speech"] = None

    # Guard 2: normalize `register`.
    # If band is critical the register must be caring-critical — override and log if wrong.
    # If register is missing (LLM forgot), default to calm for ok/elevated state.
    if band == "critical":
        if r.get("register") != "caring-critical":
            log.warning("Guard 2: forcing caring-critical for critical band (was %r)", r.get("register"))
            r["register"] = "caring-critical"
    elif "register" not in r:
        r["register"] = "calm"

    # Early type check: speech must be str or None before any processing
    speech_val = r.get("speech")
    if speech_val is not None and not isinstance(speech_val, str):
        raise ValidationError(f"speech is not str or null: {type(speech_val)!r}")

    # Guard 3: strip digits and percentages from speech (only when channel is open)
    if r.get("speech"):
        r["speech"] = re.sub(r' +', ' ', _DIGIT_RE.sub("", r["speech"])).strip()

    # Guard 4: observations append-only, validated=false, no protected classes
    clean = []
    for obs in r.get("observations", []):
        obs = copy.deepcopy(obs)
        obs["validated"] = False
        if any(term in str(obs.get("value", "")).lower() for term in _PROTECTED):
            log.warning("Guard 4: protected class in observation, stripped: %r", obs.get("value"))
            continue
        clean.append(obs)
    r["observations"] = clean

    # Guard 5: strip locale mutation fields.
    # `language` is intentionally kept inert here — TTS provider does not yet
    # act on it, so passing it through would be misleading. Enable when TTS
    # language switching is wired end-to-end.
    r.pop("locale", None)
    r.pop("language", None)

    # Guard 6: redact embedded commands in observation values
    for obs in r.get("observations", []):
        obs["value"] = _COMMAND_RE.sub("[redacted]", str(obs.get("value", "")))

    # Guard 7: feedback always stripped (no candidate tracking in demo)
    r.pop("feedback", None)

    return r
