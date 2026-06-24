import os
from typing import Optional
from openai import OpenAI
from audio import AudioPlayback


class OpenAITTS:
    def __init__(self, api_key: str = None, voice: str = None):
        self._client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self._voice = voice or os.getenv("THEA_TTS_VOICE", "shimmer")
        self._playback = AudioPlayback()

    def speak(self, text: Optional[str]) -> None:
        if not text:
            return
        with self._client.audio.speech.with_streaming_response.create(
            model="tts-1", voice=self._voice, input=text, response_format="pcm",
        ) as response:
            self._playback.stream_pcm(response.iter_bytes(chunk_size=4096))
