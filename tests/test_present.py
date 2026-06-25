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
    def __init__(self): self.fired = False; self.btn = None; self.pat = None; self.was_reset = False
    def fire_reflex_alert(self): self.fired = True
    def on_button(self, kind): self.btn = kind
    def set_pattern(self, hid): self.pat = hid
    def reset(self): self.was_reset = True


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


def test_you_line_transcribes_without_tts():
    c = _ctx()
    r = handle_present({"cmd": "line", "who": "you", "text": "I'm at a friend's, they've got a dog."}, **c)
    assert r["ok"] and c["tts"].spoken == []     # presenter reads 'you' lines aloud; no TTS
    assert ("transcript", {"who": "you", "text": "I'm at a friend's, they've got a dog."}) in c["bridge"].events


def test_reset_command_resets_orchestrator():
    c = _ctx()
    r = handle_present({"cmd": "reset"}, **c)
    assert r["ok"] and c["orchestrator"].was_reset


def test_play_command_fires_pulse_and_screen():
    c = _ctx()
    r = handle_present({"cmd": "play", "hid": 3, "gid": 5}, **c)
    assert r["ok"]
    assert ("haptic", 3, 5, c["fill"].get()["fill"]) in c["bridge"].calls


def test_setfill_sets_without_firing_screen():
    c = _ctx()
    r = handle_present({"cmd": "setfill", "level": 42}, **c)
    assert r["ok"] and c["fill"].get()["fill"] == 42
    assert not any(call[0] == "display" for call in c["bridge"].calls)  # screen NOT fired


def test_button_simulates_interaction():
    c = _ctx()
    r = handle_present({"cmd": "button", "kind": "hold"}, **c)
    assert r["ok"] and c["orchestrator"].btn == "hold"


def test_setpattern_command():
    c = _ctx()
    r = handle_present({"cmd": "setpattern", "hid": 2}, **c)
    assert r["ok"] and c["orchestrator"].pat == 2


def test_unknown_command_errors():
    c = _ctx()
    r = handle_present({"cmd": "nope"}, **c)
    assert r["ok"] is False
