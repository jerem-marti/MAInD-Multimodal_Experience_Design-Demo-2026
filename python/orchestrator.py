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
NO_CHANGE, UP_QUICK, DOWN_SLOW = 0, 3, 4

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

    def _felt(self) -> str:
        return _FELT[self._fill.get()["band"]]

    # ── button entry point ──────────────────────────────────────────────
    def on_button(self, kind: str) -> None:
        self._b.send("button", {"kind": kind})
        if self.state == "idle" and kind == "tap":
            self._status_read()
        elif self.state == "idle" and kind == "hold":
            with self._lock:
                if self._busy:
                    log.debug("on_button hold ignored: session active")
                    return
                self._busy = True
            try:
                self._run_session("vui")
            finally:
                with self._lock:
                    self._busy = False
        elif self.state == "alert" and kind == "tap":
            with self._lock:
                if self._busy:
                    log.debug("on_button tap ignored: session active")
                    return
                self._busy = True
            try:
                self._run_session("caw")
                self._closure()
            finally:
                with self._lock:
                    self._busy = False
        # alert + hold, or anything else: ignored

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
            for obs in validated.get("observations", []):
                self._b.send("observation", obs)
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
            self._b.send("render", {"color": "rest", "motion": "rest", "felt": self._felt()})
