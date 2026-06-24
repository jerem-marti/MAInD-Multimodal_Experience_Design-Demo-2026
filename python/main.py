import asyncio, os, subprocess, threading, time
from pathlib import Path
from fastapi import Request
from arduino.app_bricks.web_ui import WebUI
from arduino.app_utils import App, Logger

try:
    from dotenv import load_dotenv
    for cand in ("/app/.env", ".env"):
        if Path(cand).is_file():
            load_dotenv(cand)
            break
except ImportError:
    pass

# Playback volume — aplay succeeds even at 0% PCM, so without this TTS is silent.
try:
    subprocess.run(["amixer", "-c", "0", "sset", "PCM", os.getenv("THEA_PLAYBACK_VOLUME", "85%"), "unmute"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
except Exception:
    pass

from fill_engine import FillEngine
from bridge import TheaBridge
from orchestrator import Orchestrator
from present import handle_present
from validator import validate
from stt import OpenAISTT
from llm import OpenAILLM
from tts import OpenAITTS

log = Logger("thea-demo")

web_ui = WebUI()
bridge = TheaBridge()
bridge.set_signal_emitter(lambda ev, p: web_ui.send_message(ev, p))

fill = FillEngine()
stt, llm, tts = OpenAISTT(), OpenAILLM(), OpenAITTS()
orchestrator = Orchestrator(bridge, fill, stt, llm, tts, validate)

# MCU pushes button gestures up to here
bridge.register_button(lambda kind: orchestrator.on_button(kind))


async def api_present(request: Request) -> dict:
    body = await request.json()
    return await asyncio.get_event_loop().run_in_executor(
        None, lambda: handle_present(body, fill=fill, bridge=bridge, orchestrator=orchestrator, tts=tts)
    )

web_ui.expose_api("POST", "/api/present", api_present)


def _ticker():
    last = time.monotonic()
    while True:
        now = time.monotonic()
        fill.tick(now - last)
        last = now
        time.sleep(0.1)

threading.Thread(target=_ticker, daemon=True).start()

log.info("thea-demo ready — product surface on :7000/, presenter on :7000/presenter.html")
App.run()
