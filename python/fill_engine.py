"""Scripted allergen-load fill state for the demo (Wizard-of-Oz proxy).

The agent never writes here; only the presenter (or a ramp) does. This is the
single source of the 'load' the demo narrates. No physics — a fill value, a
band, and a linear ramp.
"""


def _band(fill: int) -> str:
    if fill >= 80:
        return "critical"
    if fill >= 55:
        return "elevated"
    return "ok"


class FillEngine:
    def __init__(self) -> None:
        self._fill = 10.0
        self._target = None   # active ramp target, or None
        self._rate = 0.0      # %/sec

    def set_fill(self, level: int) -> None:
        self._fill = float(max(0, min(100, level)))
        self._target = None

    def ramp(self, target: int, rate: float) -> None:
        self._target = float(max(0, min(100, target)))
        self._rate = abs(rate)

    def tick(self, dt: float) -> None:
        if self._target is None:
            return
        if self._fill < self._target:
            self._fill = min(self._target, self._fill + self._rate * dt)
        else:
            self._fill = max(self._target, self._fill - self._rate * dt)
        if self._fill == self._target:
            self._target = None

    def trigger_critical(self) -> None:
        self._fill = 90.0
        self._target = None

    def ramping(self) -> bool:
        return self._target is not None

    def get(self) -> dict:
        f = int(round(self._fill))
        return {"fill": f, "band": _band(f)}
