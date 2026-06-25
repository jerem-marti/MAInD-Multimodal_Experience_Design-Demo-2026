"""Thin Bridge wrapper. Forwards display/haptic commands to the MCU (when the
hardware Bridge is present) and mirrors every action to the browser via an
injected emitter. Hardware-optional so it imports and runs under pytest.
"""
import os
from typing import Callable, Optional

_WOZ = os.getenv("THEA_MODE", "hardware") == "woz"
try:
    from arduino.app_utils import Bridge as _HWBridge  # type: ignore
    _HW = True
except Exception:
    _HW = False


class TheaBridge:
    def __init__(self) -> None:
        self._emit: Optional[Callable[[str, dict], None]] = None

    def set_signal_emitter(self, fn: Callable[[str, dict], None]) -> None:
        self._emit = fn

    def send(self, event: str, payload: dict) -> None:
        if self._emit:
            try:
                self._emit(event, payload)
            except Exception:
                pass

    def display(self, gid: int, fill: int) -> None:
        self.send("render-raw", {"gid": gid, "fill": fill})
        if _HW and not _WOZ:
            try:
                _HWBridge.call("playDisplay", gid, fill)
            except Exception:
                pass

    def haptic_display(self, hid: int, gid: int, fill: int) -> None:
        self.send("render-raw", {"hid": hid, "gid": gid, "fill": fill})
        if _HW and not _WOZ:
            try:
                _HWBridge.call("playHapticAndDisplay", hid, gid, fill)
            except Exception:
                pass

    def register_button(self, handler: Callable[[str], None]) -> None:
        if _HW and not _WOZ:
            _HWBridge.provide("on_button", handler)
