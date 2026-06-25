import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import audio
from audio import AudioPlayback, AudioCapture


class _FakeStdin:
    def __init__(self, proc): self._proc = proc
    def write(self, b):
        if self._proc.killed: raise BrokenPipeError()
        self._proc.written.append(b)
    def flush(self):
        if self._proc.killed: raise BrokenPipeError()
    def close(self): pass


class _FakeProc:
    def __init__(self): self.killed = False; self.written = []; self.stdin = _FakeStdin(self)
    def kill(self): self.killed = True
    def wait(self, timeout=None): return 0


def _patch(monkeypatch):
    procs = []
    monkeypatch.setattr(audio.subprocess, "Popen", lambda *a, **k: procs.append(_FakeProc()) or procs[-1])
    return procs


def test_stream_pcm_writes_all_chunks(monkeypatch):
    procs = _patch(monkeypatch)
    AudioPlayback().stream_pcm([b"a", b"b", b"c"])
    assert procs[0].written == [b"a", b"b", b"c"]


def test_stop_cuts_playback_mid_clip(monkeypatch):
    procs = _patch(monkeypatch)
    pb = AudioPlayback()

    def chunks():
        yield b"a"
        pb.stop()          # long-press abort lands mid-clip
        yield b"b"

    pb.stream_pcm(chunks())
    assert procs[0].killed is True
    assert procs[0].written == [b"a"]      # cut off — 'b' never reached aplay


def test_stop_before_start_plays_nothing_until_reset(monkeypatch):
    procs = _patch(monkeypatch)
    pb = AudioPlayback()
    pb.stop()                              # aborted during 'thinking', before this clip
    pb.stream_pcm([b"a", b"b"])
    assert procs == []                     # aplay never spawned
    pb.reset()                             # next session re-enables playback
    pb.stream_pcm([b"a"])
    assert len(procs) == 1 and procs[0].written == [b"a"]


class _FakeCapProc:
    def __init__(self): self.terminated = False; self.killed = False
    class _Out:
        def read(self, n): return b""        # silence -> record loop ends with no frames
    stdout = _Out()
    def terminate(self): self.terminated = True
    def kill(self): self.killed = True
    def wait(self, timeout=None): return 0


def test_capture_stop_skips_arecord_until_reset(monkeypatch):
    procs = []
    monkeypatch.setattr(audio.subprocess, "Popen",
                        lambda *a, **k: procs.append(_FakeCapProc()) or procs[-1])
    cap = AudioCapture()
    cap.stop()
    assert cap.record() == b"" and procs == []     # aborted: arecord never spawned
    cap.reset()
    assert cap.record() == b"" and len(procs) == 1  # re-enabled: it records again
