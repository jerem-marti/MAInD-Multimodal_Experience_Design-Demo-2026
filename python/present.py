"""Presenter command vocabulary — the generic Wizard channel the phone drives.
The 5-beat demo is presets over this; later test scenarios reuse it unchanged.
"""
GAUGE, CLEAR = 0, 1


def handle_present(body: dict, *, fill, bridge, orchestrator, tts) -> dict:
    cmd = body.get("cmd")
    try:
        if cmd == "fill":
            fill.set_fill(int(body["level"]))
            g = fill.get()
            bridge.display(GAUGE, g["fill"])
            bridge.send("render", {"color": "rest", "motion": "rest", "felt": _felt(g["band"])})
        elif cmd == "ramp":
            fill.ramp(int(body["target"]), float(body["rate"]))
        elif cmd == "critical":
            fill.trigger_critical()
            orchestrator.fire_reflex_alert()
        elif cmd == "screen":
            bridge.display(int(body["gid"]), fill.get()["fill"])
        elif cmd == "haptic":
            bridge.haptic_display(int(body["hid"]), CLEAR, fill.get()["fill"])
        elif cmd == "line":
            text = str(body["text"])
            bridge.send("transcript", {"who": "thea", "text": text})
            tts.speak(text)
        else:
            return {"ok": False, "error": f"unknown cmd: {cmd}"}
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


_FELT = {"ok": "plenty of headroom — a calm day",
         "elevated": "your window is narrowing",
         "critical": "you're right at your edge"}


def _felt(band: str) -> str:
    return _FELT.get(band, "")
