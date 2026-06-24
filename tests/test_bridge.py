import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
from bridge import TheaBridge


def test_display_emits_signal_without_hardware():
    b = TheaBridge()
    seen = []
    b.set_signal_emitter(lambda ev, p: seen.append((ev, p)))
    b.display(gid=0, fill=10)
    assert ("render-raw", {"gid": 0, "fill": 10}) in seen


def test_haptic_display_emits_signal():
    b = TheaBridge()
    seen = []
    b.set_signal_emitter(lambda ev, p: seen.append((ev, p)))
    b.haptic_display(hid=3, gid=5, fill=90)
    assert ("render-raw", {"hid": 3, "gid": 5, "fill": 90}) in seen


def test_send_passes_through_to_emitter():
    b = TheaBridge()
    seen = []
    b.set_signal_emitter(lambda ev, p: seen.append((ev, p)))
    b.send("render", {"color": "rest"})
    assert ("render", {"color": "rest"}) in seen


def test_no_emitter_does_not_raise():
    b = TheaBridge()      # no emitter set
    b.display(0, 10)      # must not raise
    b.haptic_display(0, 0, 0)
    b.send("render", {})
