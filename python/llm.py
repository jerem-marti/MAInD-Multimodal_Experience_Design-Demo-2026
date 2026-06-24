import json, os
from pathlib import Path
from openai import OpenAI

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "Thea-System-Prompt.md"


class OpenAILLM:
    def __init__(self, api_key: str = None, model: str = None):
        self._client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self._model = model or os.getenv("THEA_LLM_MODEL", "gpt-4o")
        self.system_prompt = _PROMPT_PATH.read_text(encoding="utf-8")

    def chat(self, system: str, history: list, turn: dict) -> dict:
        messages = [{"role": "system", "content": system}]
        messages.extend(history)
        messages.append({"role": "user", "content": json.dumps(turn, ensure_ascii=False)})
        resp = self._client.chat.completions.create(
            model=self._model, messages=messages,
            response_format={"type": "json_object"}, temperature=0.7,
        )
        return json.loads(resp.choices[0].message.content)
