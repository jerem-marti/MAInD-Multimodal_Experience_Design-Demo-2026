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
    orc._action_thread.join(2)
    assert orc.state == "idle"
    assert ("haptic", 0, 0, 10) in b.calls          # NO_CHANGE + GAUGE at fill 10
    assert ("render", {"color": "rest", "motion": "rest",
                       "felt": orc._felt()}) in b.events
    assert tts.spoken == [] and llm.calls == 0       # wordless


def test_idle_hold_runs_calm_voice_session():
    orc, b, tts, llm = _make(stt_lines=["I'm at a friend's, they've got a dog", ""])
    orc.on_button("hold")
    orc._session_thread.join(2)
    assert llm.calls >= 1
    assert tts.spoken and tts.spoken[0].startswith("Okay")
    assert orc.state == "idle"                       # closes back to idle


def test_exposure_observation_ramps_load():
    orc, b, tts, llm = _make(stt_lines=["there's a dog here", ""])
    orc.on_button("hold")
    orc._session_thread.join(2)
    fe = orc._fill                      # the LLM mock logs an 'exposure' observation
    before = fe.get()["fill"]
    for _ in range(20):
        fe.tick(1.0)
    assert fe.get()["fill"] > before   # detection system ramped the load up


def test_autonomy_fires_on_headroom_margin():
    orc, b, tts, llm = _make()
    orc._last_auto_fill = 10
    orc._fill.set_fill(25)            # +15 >= margin 10
    orc.autonomy_tick()
    assert ("haptic", 1, 0, 25) in b.calls   # UP_SLOW + GAUGE at fill 25


def test_autonomy_waits_for_settle():
    orc, b, tts, llm = _make()
    orc._last_auto_fill = 10
    orc._fill.ramp(85, 5.0)          # actively ramping
    orc._fill.tick(2.0)              # ~20, still moving
    n0 = len(b.calls)
    orc.autonomy_tick()
    assert len(b.calls) == n0        # silent while ramping
    for _ in range(20):
        orc._fill.tick(1.0)          # ramp completes -> settled
    orc.autonomy_tick()
    assert any(c[0] == "haptic" for c in b.calls)   # one update on settle


def test_autonomy_autofires_alert_at_edge():
    orc, b, tts, llm = _make()
    orc._fill.set_fill(90)
    orc.autonomy_tick()
    assert orc.state == "alert"        # crossed the edge -> reflex fired by itself
    # does not re-fire while still critical (simulate returning to idle, fill still 90)
    orc.state = "idle"
    orc.autonomy_tick()
    assert orc.state == "idle"         # latch prevents immediate re-fire
    # re-arms after the load drops, fires again on a new crossing
    orc._fill.set_fill(40); orc.autonomy_tick()
    orc._fill.set_fill(95); orc.autonomy_tick()
    assert orc.state == "alert"


def test_autonomy_silent_during_session():
    orc, b, tts, llm = _make()
    orc.state = "vui"                 # a voice session is running (not idle, not alert)
    orc._last_auto_fill = 10
    orc._fill.set_fill(60)
    before = len(b.calls)
    orc.autonomy_tick()
    assert len(b.calls) == before    # no autonomous status while a session is active


def test_set_pattern_fires_update():
    orc, b, tts, llm = _make()
    orc.set_pattern(2)
    assert any(c[0] == "haptic" and c[1] == 2 and c[2] == 0 for c in b.calls)  # pattern 2 + GAUGE


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
    orc._session_thread.join(2)
    assert llm.calls > llm_before and tts.spoken      # voice ran only after ACK
    assert orc.state == "idle"                        # ambient closure
    assert ("render", {"color": "rest", "motion": "rest", "felt": "easing"}) in b.events


def test_alert_hold_dismisses_alarm():
    orc, b, tts, llm = _make()
    orc.fire_reflex_alert()
    orc.on_button("hold")                             # long press quits the alarm (no CAW)
    orc._action_thread.join(2)
    assert orc.state == "idle" and tts.spoken == []   # dismissed; Thea never spoke


def test_session_hold_signals_abort():
    orc, b, tts, llm = _make()
    orc.state = "caw"; orc._busy = True
    orc.on_button("hold")
    assert orc._abort is True          # long press during a session signals abort


def test_session_abort_resets_to_beat1():
    orc, b, tts, llm = _make()
    orc._fill.set_fill(95)
    orc._abort = True                  # abort already signaled
    orc._session_run("caw")            # loop sees abort -> breaks -> resets
    assert orc.state == "idle" and orc._fill.get()["fill"] == 10 and orc._abort is False


def test_alert_reasserts_while_waiting():
    orc, b, tts, llm = _make()
    orc.fire_reflex_alert()
    orc._last_reassert = 0.0          # force the re-assert interval to have elapsed
    n0 = len(b.calls)
    orc.autonomy_tick()
    assert len(b.calls) > n0          # a gentle re-assert fired
    assert orc.state == "alert"       # still waiting — no auto-exit


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
    orc._session_thread.join(2)
    # Session exits; non-clobbering guard must preserve the "alert" state
    assert orc.state == "alert", f"Expected 'alert', got '{orc.state}'"
