import io
import math
import os
import struct
import subprocess
import wave

_RATE     = 16000
_CHANNELS = 1
_BYTES_PS = 2  # S16_LE

# Card name "Q5" is stable across reboots; override with e.g. THEA_AUDIO_DEVICE=plughw:0,0
_DEVICE = os.getenv("THEA_AUDIO_DEVICE", "plughw:Q5")

# Override with e.g. THEA_SILENCE_DURATION=3.0
_SILENCE_DURATION = float(os.getenv("THEA_SILENCE_DURATION", "2.5"))


def _rms(chunk: bytes) -> float:
    n = len(chunk) // _BYTES_PS
    if n == 0:
        return 0.0
    samples = struct.unpack(f"<{n}h", chunk)
    return math.sqrt(sum(s * s for s in samples) / n)


class AudioCapture:
    def __init__(
        self,
        sample_rate: int = _RATE,
        silence_threshold: float = 400.0,
        silence_duration: float = _SILENCE_DURATION,
        max_duration: float = 10.0,
    ):
        self._rate    = sample_rate
        self._thresh  = silence_threshold
        self._sil_dur = silence_duration
        self._max_dur = max_duration

    def record(self) -> bytes:
        chunk_frames   = int(self._rate * 0.1)           # 100 ms
        chunk_bytes    = chunk_frames * _BYTES_PS * _CHANNELS
        sil_n          = int(self._sil_dur / 0.1)
        max_n          = int(self._max_dur / 0.1)

        cmd = [
            "arecord", "-D", _DEVICE,
            "-r", str(self._rate),
            "-c", str(_CHANNELS),
            "-f", "S16_LE",
            "-t", "raw", "-q",
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

        frames: list[bytes] = []
        sil_count = 0
        started   = False

        try:
            for _ in range(max_n):
                chunk = proc.stdout.read(chunk_bytes)
                if not chunk:
                    break
                rms = _rms(chunk)
                if rms > self._thresh:
                    started, sil_count = True, 0
                    frames.append(chunk)
                elif started:
                    frames.append(chunk)
                    sil_count += 1
                    if sil_count >= sil_n:
                        break
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()

        if not frames:
            return b""

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(_CHANNELS)
            wf.setsampwidth(_BYTES_PS)
            wf.setframerate(self._rate)
            wf.writeframes(b"".join(frames))
        return buf.getvalue()


class AudioPlayback:
    def play_wav(self, wav_bytes: bytes) -> None:
        if not wav_bytes:
            return
        try:
            subprocess.run(
                ["aplay", "-D", _DEVICE, "-q", "-"],
                input=wav_bytes,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            pass

    def stream_pcm(self, chunks) -> None:
        """Stream raw S16_LE 24kHz mono PCM chunks to aplay with minimal latency."""
        proc = subprocess.Popen(
            ["aplay", "-D", _DEVICE, "-f", "S16_LE", "-r", "24000",
             "-c", "1", "-t", "raw", "-q", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            for chunk in chunks:
                proc.stdin.write(chunk)
                proc.stdin.flush()
        finally:
            proc.stdin.close()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
