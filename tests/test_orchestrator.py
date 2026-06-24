import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
from orchestrator import Orchestrator
from fill_engine import FillEngine


class _Bridge:
    def __init__(self): self.calls = []; self.events = []
    def display(self, gid, fill): self.calls.append(("display", gid, fill))
    def haptic_display(self, hid, gid, fill): self.calls.append(("haptic", hid, gid, fill))
    def send(self, ev, p): self.events.append((ev, p))


class _STT:
    def __init__(self, lines): self._lines = list(lines)
    def transcribe(self): return self._lines.pop(0) if self._lines else ""


class _LLM:
    system_prompt = "SYS"
    def __init__(self): self.calls = 0
    def chat(self, system, history, turn):
        self.calls += 1
        return {"speech": "Okay, I've factored the dog in.", "register": "calm",
                "observations": [{"type": "exposure", "value": "dog", "validated": False}]}


class _TTS:
    def __init__(self): self.spoken = []
    def speak(self, text): self.spoken.append(text)


def _validator(response, band, channel_open):
    return response  # pass-through for the state-machine tests


def _make(stt_lines=("",)):
    b, fe, tts, llm = _Bridge(), FillEngine(), _TTS(), _LLM()
    orc = Orchestrator(b, fe, _STT(stt_lines), llm, tts, _validator)
    return orc, b, tts, llm


def test_idle_tap_is_status_read_no_voice():
    orc, b, tts, llm = _make()
    orc.on_button("tap")
    assert orc.state == "idle"
    assert ("haptic", 0, 0, 10) in b.calls          # NO_CHANGE + GAUGE at fill 10
    assert ("render", {"color": "rest", "motion": "rest",
                       "felt": orc._felt()}) in b.events
    assert tts.spoken == [] and llm.calls == 0       # wordless


def test_idle_hold_runs_calm_voice_session():
    orc, b, tts, llm = _make(stt_lines=["I'm at a friend's, they've got a dog", ""])
    orc.on_button("hold")
    assert llm.calls >= 1
    assert tts.spoken and tts.spoken[0].startswith("Okay")
    assert orc.state == "idle"                       # closes back to idle


def test_reflex_alert_is_silent_until_ack():
    orc, b, tts, llm = _make(stt_lines=["I'm okay", ""])
    orc.fire_reflex_alert()
    assert orc.state == "alert"
    # terracotta + strong haptic + alert display fired, but NO voice yet
    assert ("render", {"color": "critical", "motion": "critical",
                       "felt": orc._felt()}) in b.events
    assert any(c[0] == "haptic" and c[1] == 3 and c[2] == 5 for c in b.calls)  # UP_QUICK + ALERT_THEN_GAUGE
    assert tts.spoken == [] and llm.calls == 0       # THE INVARIANT: silent before ACK


def test_alert_tap_acks_and_speaks_then_closes():
    orc, b, tts, llm = _make(stt_lines=["My throat feels tight", ""])
    orc.fire_reflex_alert()
    llm_before = llm.calls
    orc.on_button("tap")                              # the seam
    assert llm.calls > llm_before and tts.spoken      # voice ran only after ACK
    assert orc.state == "idle"                        # ambient closure
    assert ("render", {"color": "rest", "motion": "rest", "felt": "easing"}) in b.events


def test_alert_hold_does_not_ack():
    orc, b, tts, llm = _make()
    orc.fire_reflex_alert()
    orc.on_button("hold")                             # only a tap ACKs
    assert orc.state == "alert" and tts.spoken == []


def test_on_button_emits_button_event():
    orc, b, tts, llm = _make()
    orc.on_button("tap")
    assert ("button", {"kind": "tap"}) in b.events
    # also fires for hold in idle
    orc2, b2, tts2, llm2 = _make(stt_lines=[""])
    orc2.on_button("hold")
    assert ("button", {"kind": "hold"}) in b2.events


def test_vui_exit_does_not_clobber_alert_state():
    """fire_reflex_alert() mid-VUI-session must survive session exit unchanged."""
    b, fe, tts, llm = _Bridge(), FillEngine(), _TTS(), _LLM()
    orc_ref = [None]

    class _STTFiresAlert:
        def __init__(self): self._calls = 0
        def transcribe(self):
            self._calls += 1
            if self._calls == 1:
                # Simulate alert arriving on another thread while VUI session loops
                orc_ref[0].fire_reflex_alert()
                return "I feel okay"
            return ""  # silence → ends session

    orc = Orchestrator(b, fe, _STTFiresAlert(), llm, tts, _validator)
    orc_ref[0] = orc
    orc.on_button("hold")                             # starts vui session
    # Session exits; non-clobbering guard must preserve the "alert" state
    assert orc.state == "alert", f"Expected 'alert', got '{orc.state}'"
