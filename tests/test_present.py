import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
from present import handle_present
from fill_engine import FillEngine


class _Bridge:
    def __init__(self): self.calls = []; self.events = []
    def display(self, gid, fill): self.calls.append(("display", gid, fill))
    def haptic_display(self, hid, gid, fill): self.calls.append(("haptic", hid, gid, fill))
    def send(self, ev, p): self.events.append((ev, p))


class _Orc:
    def __init__(self): self.fired = False
    def fire_reflex_alert(self): self.fired = True


class _TTS:
    def __init__(self): self.spoken = []
    def speak(self, text): self.spoken.append(text)


def _ctx():
    return dict(fill=FillEngine(), bridge=_Bridge(), orchestrator=_Orc(), tts=_TTS())


def test_fill_command_sets_and_renders():
    c = _ctx()
    r = handle_present({"cmd": "fill", "level": 55}, **c)
    assert r["ok"] and c["fill"].get()["fill"] == 55
    assert any(ev == "render" for ev, _ in c["bridge"].events)


def test_ramp_command():
    c = _ctx()
    r = handle_present({"cmd": "ramp", "target": 80, "rate": 10.0}, **c)
    assert r["ok"]
    c["fill"].tick(8.0)
    assert c["fill"].get()["fill"] == 80


def test_critical_fires_alert():
    c = _ctx()
    r = handle_present({"cmd": "critical"}, **c)
    assert r["ok"] and c["orchestrator"].fired and c["fill"].get()["band"] == "critical"


def test_line_speaks_and_transcribes():
    c = _ctx()
    r = handle_present({"cmd": "line", "text": "You're right at your edge now."}, **c)
    assert r["ok"] and c["tts"].spoken == ["You're right at your edge now."]
    assert ("transcript", {"who": "thea", "text": "You're right at your edge now."}) in c["bridge"].events


def test_unknown_command_errors():
    c = _ctx()
    r = handle_present({"cmd": "nope"}, **c)
    assert r["ok"] is False
