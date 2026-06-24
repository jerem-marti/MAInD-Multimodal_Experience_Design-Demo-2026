import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
from fill_engine import FillEngine


def test_starts_low_and_ok():
    fe = FillEngine()
    assert fe.get() == {"fill": 10, "band": "ok"}


def test_set_fill_clamps():
    fe = FillEngine()
    fe.set_fill(150)
    assert fe.get()["fill"] == 100
    fe.set_fill(-5)
    assert fe.get()["fill"] == 0


def test_band_thresholds():
    fe = FillEngine()
    fe.set_fill(54);  assert fe.get()["band"] == "ok"
    fe.set_fill(55);  assert fe.get()["band"] == "elevated"
    fe.set_fill(79);  assert fe.get()["band"] == "elevated"
    fe.set_fill(80);  assert fe.get()["band"] == "critical"


def test_tick_advances_toward_target_and_stops():
    fe = FillEngine()
    fe.set_fill(10)
    fe.ramp(target=80, rate=10.0)   # 10 %/sec
    fe.tick(1.0); assert fe.get()["fill"] == 20
    fe.tick(10.0); assert fe.get()["fill"] == 80   # clamps at target
    fe.tick(1.0); assert fe.get()["fill"] == 80   # no overshoot


def test_trigger_critical():
    fe = FillEngine()
    fe.trigger_critical()
    g = fe.get()
    assert g["fill"] == 90 and g["band"] == "critical"
