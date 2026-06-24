"""The reflection-layer state machine. Interprets button gestures by state,
runs the live voice sessions, and gates voice strictly behind the ACK tap in
the critical window. Never sets fill state; only reads it.
"""
import json
import logging
import threading

log = logging.getLogger("thea.orchestrator")

# Display gids / haptic hids (see plan Contract)
GAUGE, CLEAR, LISTENING, THINKING, SPEAKING, ALERT_THEN_GAUGE = 0, 1, 2, 3, 4, 5
NO_CHANGE, UP_SLOW, UP_MEDIUM, UP_QUICK, DOWN_SLOW, DOWN_MEDIUM, DOWN_QUICK = 0, 1, 2, 3, 4, 5, 6

_FELT = {
    "ok": "plenty of headroom — a calm day",
    "elevated": "your window is narrowing",
    "critical": "you're right at your edge",
}


class Orchestrator:
    def __init__(self, bridge, fill, stt, llm, tts, validator_fn):
        self._b = bridge
        self._fill = fill
        self._stt = stt
        self._llm = llm
        self._tts = tts
        self._validate = validator_fn
        self.state = "idle"
        self._lock = threading.Lock()
        self._busy = False
        self._session_thread = None
        self._action_thread = None
        self._auto_pattern = NO_CHANGE
        self._last_auto_fill = fill.get()["fill"]
        self._alerted = False   # critical-edge alert latch (re-arms when load drops below 90)

    def _felt(self) -> str:
        return _FELT[self._fill.get()["band"]]

    # ── button entry point ──────────────────────────────────────────────
    def on_button(self, kind: str) -> None:
        log.info("button press: kind=%s state=%s", kind, self.state)
        self._b.send("button", {"kind": kind})
        if self.state == "idle" and kind == "tap":
            # Off-thread: the status read calls into the MCU (a blocking haptic),
            # which must NOT stall on_button — else the release ('up') is delayed
            # and the on-screen finger stays stuck down.
            self._action_thread = threading.Thread(target=self._status_read, daemon=True)
            self._action_thread.start()
        elif self.state == "idle" and kind == "hold":
            self._start_session("vui")
        elif self.state == "alert" and kind == "tap":
            self._start_session("caw")
        # alert + hold, or anything else: ignored

    def _start_session(self, mode: str) -> None:
        # Run the voice session OFF the button/RPC thread so on_button returns
        # immediately — the reflex layer never waits for the agent. This is what
        # lets the release ('up') reach the UI the instant the button is let go.
        with self._lock:
            if self._busy:
                log.debug("session ignored: already active")
                return
            self._busy = True
        self._session_thread = threading.Thread(
            target=self._session_run, args=(mode,), daemon=True)
        self._session_thread.start()

    def _session_run(self, mode: str) -> None:
        try:
            self._run_session(mode)
            if mode == "caw":
                self._closure()
        finally:
            with self._lock:
                self._busy = False

    # ── beats ───────────────────────────────────────────────────────────
    def _status_read(self) -> None:
        fill = self._fill.get()["fill"]
        self._b.haptic_display(NO_CHANGE, GAUGE, fill)
        self._b.send("render", {"color": "rest", "motion": "rest", "felt": self._felt()})

    def fire_reflex_alert(self) -> None:
        self.state = "alert"
        fill = self._fill.get()["fill"]
        self._b.send("render", {"color": "critical", "motion": "critical", "felt": self._felt()})
        self._b.haptic_display(UP_QUICK, ALERT_THEN_GAUGE, fill)

    def _closure(self) -> None:
        fill = self._fill.get()["fill"]
        self._b.haptic_display(DOWN_SLOW, CLEAR, fill)
        self._b.send("render", {"color": "rest", "motion": "rest", "felt": "easing"})
        self.state = "idle"
        self._last_auto_fill = fill   # re-baseline so autonomy doesn't immediately re-fire

    # ── autonomous sensing loop ──────────────────────────────────────────
    def set_pattern(self, hid: int) -> None:
        # Presenter sets the active delta pattern → device updates the user now.
        self._auto_pattern = hid
        self._auto_fire()

    def _auto_fire(self) -> None:
        f = self._fill.get()["fill"]
        self._b.haptic_display(self._auto_pattern, GAUGE, f)
        self._b.send("render", {"color": "rest", "motion": "rest", "felt": self._felt()})
        self._last_auto_fill = f

    def autonomy_tick(self) -> None:
        # Called ~10x/s. Auto-fires the critical alert at the edge; otherwise
        # settle-only status updates (quiet while moving, one update on settle).
        if self.state != "idle":
            return
        f = self._fill.get()["fill"]
        # Critical edge → the reflex fires the alert (CAW) by itself, once per crossing.
        if f >= 90:
            if not self._alerted:
                self._alerted = True
                self.fire_reflex_alert()
            return
        self._alerted = False   # re-arm once the load eases back below the edge
        # Settle-only status updates below the edge.
        if self._fill.ramping():
            return
        margin = 5 if f >= 70 else 10
        d = f - self._last_auto_fill
        if abs(d) < margin:
            return
        if d > 0:   # narrowing
            self._auto_pattern = UP_QUICK if f >= 70 else (UP_MEDIUM if f >= 45 else UP_SLOW)
        else:       # recovering
            self._auto_pattern = DOWN_SLOW
        self._auto_fire()

    # ── voice session ───────────────────────────────────────────────────
    def _run_session(self, mode: str) -> None:
        self.state = "vui" if mode == "vui" else "caw"
        color = "engaged" if mode == "vui" else "critical"
        history = []
        while True:
            self._b.send("render", {"color": color, "motion": "listening", "felt": self._felt()})
            self._b.display(LISTENING, self._fill.get()["fill"])
            try:
                user_text = self._stt.transcribe()
            except Exception as e:
                log.error("STT error: %s", e); break
            if not user_text.strip():
                break
            self._b.send("transcript", {"who": "user", "text": user_text})
            self._b.send("render", {"color": color, "motion": "thinking", "felt": self._felt()})
            self._b.display(THINKING, self._fill.get()["fill"])

            band = self._fill.get()["band"]
            turn = {
                "state": {"aw_state": "critical" if mode == "caw" else band,
                          "headroom": band, "contributors": []},
                "channel": {"open": True, "mode": "caw" if mode == "caw" else "vui_access"},
                "locale": "en-US", "user": user_text,
            }
            try:
                raw = self._llm.chat(self._llm.system_prompt, history, turn)
                validated = self._validate(raw, band, True)
            except Exception as e:
                log.error("LLM/validate error: %s", e); break

            speech = validated.get("speech")
            obs_list = validated.get("observations", [])
            for obs in obs_list:
                self._b.send("observation", obs)
            # Detection system folds a declared exposure (e.g. the dog) into the forecast →
            # the load climbs. The agent only emitted the observation; the FillEngine owns state.
            if any(o.get("type") == "exposure" for o in obs_list):
                self._fill.ramp(85, 5.0)
            if speech:
                self._b.send("render", {"color": color, "motion": "speaking", "felt": self._felt()})
                self._b.display(SPEAKING, self._fill.get()["fill"])
                self._b.send("transcript", {"who": "thea", "text": speech})
                try:
                    self._tts.speak(speech)
                except Exception as e:
                    log.error("TTS error: %s", e)
            history.append({"role": "user", "content": json.dumps(turn)})
            history.append({"role": "assistant", "content": json.dumps(validated)})
            if not speech or "?" not in speech:
                break
        if mode == "vui" and self.state == "vui":
            self.state = "idle"
            self._b.display(CLEAR, self._fill.get()["fill"])   # return the device screen to rest (was stuck in SPEAKING)
            self._b.send("render", {"color": "rest", "motion": "rest", "felt": self._felt()})
