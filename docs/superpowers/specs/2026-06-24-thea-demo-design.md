# Thea Demo — Design Spec

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:writing-plans to turn this spec into an implementation plan, then superpowers:subagent-driven-development to execute it task-by-task.

**Goal:** Build one Arduino UNO Q app (`thea-demo`) that drives a continuous ~5-minute, slideless *show & tell*. The prototype exists to **narrate Thea's design choices** (behaviours, modalities) — **not** to prove the code works. Every beat is staged to make one design choice legible to an audience.

**Context:** Thea is a wearable framed as *"a new, calm sense — not a tracker, monitor, or medical-alert device."* Governing ideas the demo must surface: the **dual brain** (always-on MCU reflex layer owns sensing/light/haptics/the ACK tap; a woken MPU reflection layer owns voice — *"the reflex layer never waits for the agent"*); **the seam** (the ACK tap — Thea speaks *only after* a tap); **calm by default** (*"Thea never speaks unprompted"*, closure is ambient silence); **observations-not-state** (the agent submits observations, never sets State); **colour tracks device state** (warm-white rest → dusk engaged → terracotta critical); two voice registers (calm; caring-critical, **never alarmed**, graduated, say-it-once).

**Grading reality (why narration-first):** interaction & product design 25% + storytelling 20% vs technical prototype only 15%. The 5-minute slot is the **DEMO** (table exhibit), distinct from the 10-minute slide presentation. A live screen is allowed **as the prototype/product surface itself**, never as slides.

---

## Architecture

One app, three independently-buildable surfaces, served on **port 7000** via the `arduino:web_ui` brick:

- **`sketch/` — MCU reflex layer.** Drives the physical OLED (SSD1306 128×64, I²C 0x3C), vibration motor (L9110, D9/D10), and button (D2). Runs independent of the agent. Exposes Bridge RPC handlers; emits button events up.
- **`python/` — MPU reflection layer + orchestration.** FastAPI/Socket.IO (WebUI brick) + Bridge. Houses the live voice pipeline (STT→LLM→TTS), the scripted-fill engine, and the orchestrator state machine. Pushes render state + transcript + observations to the browser.
- **`assets/` — the product web surface + phone presenter view.** The audience-facing screen *is Thea's product render*; the phone view is the hidden presenter instrument (Wizard-of-Oz controls).

**Build provenance:** Built fresh. **No `_TESTS/` reuse** (unknown-provenance teammate code). Only `thea-vui` and `thea-haptic-display` are trusted references.

**Tech Stack:** Arduino UNO Q (`arduino:zephyr` MCU sketch + Linux/Docker Python). `arduino:web_ui` brick (Socket.IO transport, REST via `expose_api`). `Arduino_RouterBridge` (MessagePack RPC over `/var/run/arduino-router.sock`). Python 3 in container; OpenAI SDK (STT Whisper, a current chat model, streaming PCM TTS); `aplay`/`arecord` over ALSA `plughw:Q5`. MCU libs: U8g2 (OLED). Vanilla JS for both web views.

---

## The 5-Minute Arc (beats → behaviour/modality → design choice narrated)

| # | Beat | Behaviour & modalities | Live / Sim | Design choice narrated |
|---|------|------------------------|-----------|------------------------|
| 1 | **Onboarding** | *Acknowledged in narration only — not built.* | — | Mental model: *a sense, not an alarm.* |
| 2 | **Status read (low, slow)** | Single **button tap** → OLED low gauge + web warm-white loop breathing + one mild haptic. **No voice.** | OLED/haptic/button live; fill simulated | Calm sense; perception-on-request is **wordless**; the sense works without the agent. |
| 3 | **Add an info (R3)** | **Button hold** opens voice. Thea replies **calm** (didn't self-start). User: *"I'm at a friend's place, they've got a dog."* Thea logs an **observation**, says she'll factor it in; **never sets state**. | Live voice + hardware; state simulated | Tell Thea what she can't sense; **observations-not-state**; never self-activates; trust earned. |
| 4 | **Notification (high, fast)** | Presenter ramps fill fast (the invisible dog allergen). At the edge the **reflex fires autonomously**: web → **terracotta**, strong haptic, alert tone — **Thea silent**. | Haptic/OLED/web live; ramp simulated (WoZ) | Dual-brain reflex; the value of R3 made visible; rare & discrete alert; colour = device state. |
| 5 | **Critical Action Window** | **The seam:** user **taps to ACK**. Only then Thea speaks **caring-critical**: plain status + 1–2 options + *"which feels better?"*. User chooses; Thea supports, **says it once**. Then light **eases to warm white in silence**. | Live (button + voice + render) | The ACK seam; caring-critical ≠ alarmed; **offer-don't-command**; graduated/say-it-once; **presence-not-personhood**; **ambient closure**. |

**One button, three context-sensitive meanings:** tap-in-idle = status read · hold = open voice · tap-when-terracotta = acknowledge the seam. (Hardware already distinguishes click vs ≥1.5 s hold.)

**What is simulated, and why it's legitimate:** only the bucket **fill level** is simulated — the detection algorithm is explicitly a Wizard-of-Oz proxy in the project's own Phase-1 plan. Everything the audience touches (button, haptics, OLED, **and live voice**) is real.

---

## Components (units with one purpose, clear interfaces, testable in isolation)

### MCU sketch (`sketch/`)
- **Button** — debounced; emits distinct events upward: `tap` (short click), `hold` (≥1.5 s), and is read context-free (Python decides meaning by state). Produces: button events to Python via Bridge.
- **Haptic patterns** — three named patterns: `mild` (status read), `strong` (critical alert), `settling` (closure). Driven via L9110 PWM on D9/D10.
- **OLED behaviours** — `low_gauge(fill)`, `alert_then_gauge(fill)`, `listening`, `thinking`, `speaking`, `clear`. Rendered with U8g2 on the SSD1306.
- **Bridge handlers** — `provide_safe` for display/haptic (touch hardware in loop context); `provide` for cheap button reads. Consumes commands from Python; produces button events.

### Fill engine (`python/`)
- Holds one `fill` value (0–100) and an `aw_state` band (rest/elevated/critical). Supports `set(level)`, `ramp(target, rate)`, `trigger_critical()`. **Simple scripted — no physics.** Presenter-driven. Produces: current fill + band on demand and on change.

### Voice pipeline (`python/`)
- STT (Whisper) → LLM (system-prompt v7 + validator + observation extraction) → streaming PCM TTS, all over ALSA `plughw:Q5`. Reuses `thea-vui`'s proven structure. Produces: spoken output + `register` + extracted `observations`. **Never sets state.**

### Orchestrator (`python/`)
- State machine: `idle → status_read → vui_access → reflex_alert(silent) → seam_ack → caw → ambient_closure → idle`. Maps button events (by current state) to transitions; gates voice strictly behind the ACK in critical state. Emits render state, transcript turns, and observations over Socket.IO. Consumes: fill engine state, button events, voice pipeline output.

### Product web surface (`assets/index.html`)
- Full-bleed **ambient colour field** (warm-white `#f2ead9` → dusk `#3c6b82` → terracotta `#bb5327`); the **bare-loop avatar** animating by **motion only** (breath / listening / thinking / speaking / critical / resting); a quiet **felt-state line** in plain language (**no numbers**); a **live voice transcript**. Brand: dawn palette on warm ground `#fafaf7`, Sentient (headlines) + Supreme (UI). Consumes Socket.IO render/transcript/observation events. Audience-facing; reads as product, not a dashboard.
- Colour logic is the design rule: **colour tracks device state, not voice.**

### Phone presenter view (`assets/presenter.html`)
- Hidden-from-audience controls on a second device: `set fill`, `ramp (low/slow, high/fast)`, `trigger critical`, and a **fallback canned-line** button (plays a pre-written Thea line if live voice stalls). Drives the demo so the exhibit screen stays pure product.

---

## Data Flow

`Phone presenter → REST/WS → Fill engine / Orchestrator → Bridge → MCU (OLED/haptic)` and `→ Socket.IO → Product screen (colour/avatar/felt-state)`.
`Button (MCU) → Bridge → Orchestrator → (in idle: status render) / (in idle+hold: open voice) / (in critical: ACK → voice)`.
`Voice: Orchestrator → STT → LLM(v7+validator) → TTS(ALSA); observations → Socket.IO → screen.`

---

## Error Handling & Graceful Degradation

- **Voice failure or high latency** → phone **fallback canned-line** continues the arc; pipeline pre-warmed before the demo.
- **MCU disconnect** → the product web render alone still carries every beat (colour, avatar, felt-state, transcript).
- **ALSA `plughw:Q5`** validated as the first build step; browser-audio kept as an emergency fallback path.
- **Single-app constraint** (only one UNO Q app runs at a time): running `thea-demo` requires **stopping `thea-haptic-display`** — a gated ask at integration time, never silent.
- **Missing OpenAI key** → blocks only the voice beats; everything else proceeds.

---

## Testing Approach (matches the team's superpowers practice)

- **TDD** (`superpowers:test-driven-development`) for Python logic: fill engine (`set`/`ramp`/`trigger_critical`), orchestrator transitions and the voice-gating-behind-ACK invariant, observation extraction, validator wiring.
- **Manual on-hardware verification** for MCU firmware (button tap/hold, haptic patterns feel distinct, OLED behaviours render) and for the web/phone surfaces.
- **`superpowers:verification-before-completion`** gate on the full dry-run, against the acceptance bar below.

### Acceptance bar
1. Full arc runs **≤ 5:00**, rehearsed end-to-end; single app on `:7000`; **zero `_TESTS` dependency**.
2. Each of the 5 beats **visibly lands its named design choice**.
3. **The seam is reliable:** in critical state Thea stays silent until the real button tap; the tap reliably opens the voice.
4. **Live voice** works at acceptable latency in beats 3 & 5; **fallback canned-line** tested.
5. Colour transitions warm-white → dusk → terracotta → warm-white are correct, legible, brand-accurate; **no numbers spoken, no alarm phrasing**.
6. Haptic patterns distinct; OLED gauge/animations correct.
7. **Graceful degradation** proven: voice-off → fallback continues; MCU-off → web render carries the arc.

---

## Global Constraints

- **No `_TESTS/` code** is read or reused. References limited to `thea-vui` and `thea-haptic-display`.
- **No board-level action without a gated ask** (stopping `thea-haptic-display`, deploying/restarting `thea-demo`, attaching the serial monitor).
- The OpenAI key lives only in `thea-demo/.env` (git-ignored); **never committed, never printed**.
- Voice **never speaks unprompted**; in critical state, voice is **gated strictly behind the ACK tap**.
- The agent **never sets State** — only the fill engine owns it; the agent emits observations.
- **No spoken numbers; no alarm phrasing.** Caring-critical register is plain, warm, never anxious; the serious step is **said once**.
- Closure is **ambient silence** — no spoken sign-off.

---

## File Summary (anticipated; finalized in the plan)

| Path | Purpose |
|------|---------|
| `app.yaml` | App manifest: `arduino:web_ui` brick, port 7000. |
| `.env.example` / `.env` | OpenAI key + audio/locale config (`.env` git-ignored). |
| `sketch/sketch.ino` (+ blocks/headers) | MCU: button, haptics, OLED, Bridge handlers. |
| `sketch/sketch.yaml` | Sketch libs (U8g2). |
| `python/main.py` | Wiring: WebUI, Bridge, fill engine, orchestrator, endpoints; `App.run()` last. |
| `python/fill_engine.py` | Scripted fill state (set/ramp/trigger_critical). |
| `python/orchestrator.py` | State machine; voice-gating-behind-ACK. |
| `python/voice/…` | STT/LLM/TTS pipeline (system-prompt v7 + validator + observations). |
| `python/bridge.py` | Bridge wrapper + signal emit to browser. |
| `assets/index.html` | Product web surface (colour field, loop avatar, felt-state, transcript). |
| `assets/presenter.html` | Phone presenter controls + fallback line. |
| `docs/superpowers/specs/2026-06-24-thea-demo-design.md` | This spec. |
| `docs/superpowers/plans/2026-06-24-thea-demo.md` | Implementation plan (next step). |
| `tests/…` | Python TDD tests (fill engine, orchestrator, observations, validator). |

---

## Out of Scope (YAGNI)

- Onboarding flow (narration only).
- Full bucket physics / multi-input detection model (scripted fill only).
- Real sensor input, calibration/learning pipeline, profile persistence beyond what a single demo run needs.
- The `thea-vui` debug page and any feature not on the 5-beat critical path.
