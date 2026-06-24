import io, os
from openai import OpenAI
from audio import AudioCapture


class OpenAISTT:
    def __init__(self, api_key: str = None):
        self._client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self._capture = AudioCapture()
        self._language = os.getenv("THEA_LOCALE", "en-US").split("-")[0]

    def transcribe(self) -> str:
        wav = self._capture.record()
        if not wav:
            return ""
        buf = io.BytesIO(wav)
        buf.name = "recording.wav"
        result = self._client.audio.transcriptions.create(
            model="whisper-1", file=buf, response_format="text", language=self._language,
        )
        return str(result).strip()
