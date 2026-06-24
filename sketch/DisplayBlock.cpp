#include "DisplayBlock.h"
#include "DisplayConfig.h"
#include <math.h>

using namespace DisplayConfig;

// UNO Q / Zephyr toolchain fix: newlib-nano's libm expects an __errno symbol
// that the bare-metal build does not provide. Supply a minimal one.
extern "C" int *__errno(void) {
  static int e = 0;
  return &e;
}

// ============================================================================
//  Derived geometry (pixel space) and math helpers
// ----------------------------------------------------------------------------
//  All values below are computed from DisplayConfig; nothing here is meant to
//  be tuned by hand.
// ============================================================================
static const float PX_PER_MM_X = 128.0f / PANEL_W_MM;
static const float PX_PER_MM_Y = 64.0f / PANEL_H_MM;

// SE = outer squircle, SI = inner (black) squircle.
static const float SE_CX_PX = SE_CENTER_X_MM * PX_PER_MM_X;
static const float SE_CY_PX = SE_CENTER_Y_MM * PX_PER_MM_Y;
static const float SE_W_PX  = SE_W_MM * PX_PER_MM_X;
static const float SE_H_PX  = SE_H_MM * PX_PER_MM_Y;
static const float SE_R_PX  = SE_CORNER_MM * PX_PER_MM_X;
static const float SI_W_PX  = (SE_W_MM - 2.0f * SI_INSET_MM) * PX_PER_MM_X;
static const float SI_H_PX  = (SE_H_MM - 2.0f * SI_INSET_MM) * PX_PER_MM_Y;
static const float SI_R_PX  = (SE_CORNER_MM - SI_INSET_MM) * PX_PER_MM_X;

// Centre-line track the travelling segment follows (thinking animation).
static const float TRACK_W_MM  = SE_W_MM - SI_INSET_MM;
static const float TRACK_H_MM  = SE_H_MM - SI_INSET_MM;
static const float TRACK_R_MM  = SE_CORNER_MM - SI_INSET_MM * 0.5f;
static const float TRACK_AX_MM = TRACK_W_MM * 0.5f - TRACK_R_MM;
static const float TRACK_AY_MM = TRACK_H_MM * 0.5f - TRACK_R_MM;
static const float TRACK_Q_MM  = 1.5707963f * TRACK_R_MM;
static const float TRACK_LEN_MM =
    2.0f * (TRACK_W_MM - 2.0f * TRACK_R_MM) +
    2.0f * (TRACK_H_MM - 2.0f * TRACK_R_MM) +
    6.2831853f * TRACK_R_MM;

static const float DEG = 57.2957795f;  // radians -> degrees
static const float TAU = 6.2831853f;   // 2*pi

static float clampf(float v, float lo, float hi) {
  if (v < lo) return lo;
  if (v > hi) return hi;
  return v;
}

// Cosine ease used for the breathing brightness curve (0..1 -> 0..1).
static float easeInOut(float v) {
  return 0.5f - 0.5f * cosf(v * TAU);
}

// Half-cosine ease used to soften contrast steps (0..1 -> 0..1).
static float easeStep(float v) {
  return 0.5f - 0.5f * cosf(v * 3.1415927f);
}

static uint8_t lerpContrast(uint8_t a, uint8_t b, float v) {
  return (uint8_t)((float)a + ((float)b - (float)a) * easeStep(v));
}

// Piecewise contrast curve giving the speaking animation its syllabic blink.
static uint8_t speakingContrast(float phase) {
  const float   t[] = {0.00f, 0.15f, 0.30f, 0.45f, 0.60f, 0.75f, 1.00f};
  const uint8_t c[] = {0,     255,   18,    245,   0,     255,   25};
  for (uint8_t i = 0; i < 6; i++) {
    if (phase <= t[i + 1]) {
      float local = (phase - t[i]) / (t[i + 1] - t[i]);
      return lerpContrast(c[i], c[i + 1], local);
    }
  }
  return c[6];
}

// Signed-distance test for a rounded rectangle (squircle).
static bool insideRoundRect(float x, float y, float cx, float cy,
                            float w, float h, float r) {
  float safeR = clampf(r, 0.0f, 0.5f * ((w < h) ? w : h));
  float qx = fabsf(x - cx) - (w * 0.5f - safeR);
  float qy = fabsf(y - cy) - (h * 0.5f - safeR);
  float ox = (qx > 0.0f) ? qx : 0.0f;
  float oy = (qy > 0.0f) ? qy : 0.0f;
  float outside = sqrtf(ox * ox + oy * oy);
  float inside = ((qx > qy) ? qx : qy);
  if (inside > 0.0f) inside = 0.0f;
  return outside + inside <= safeR;
}

// True when pixel (x, y) falls inside SE but outside SI — i.e. on the ring.
static bool inGaugeRing(int x, int y) {
  float px = (float)x + 0.5f;
  float py = (float)y + 0.5f;
  bool insideSE = insideRoundRect(px, py, SE_CX_PX, SE_CY_PX,
                                  SE_W_PX, SE_H_PX, SE_R_PX);
  bool insideSI = insideRoundRect(px, py, SE_CX_PX, SE_CY_PX,
                                  SI_W_PX, SI_H_PX, SI_R_PX);
  return insideSE && !insideSI;
}

// 4x4 ordered (Bayer) dither, used to fake brightness on a 1-bit panel.
static uint8_t dither4x4(int x, int y) {
  static const uint8_t bayer[16] = {
       0,  8,  2, 10,
      12,  4, 14,  6,
       3, 11,  1,  9,
      15,  7, 13,  5
  };
  return bayer[(y & 3) * 4 + (x & 3)];
}

static bool pixelAtLevel(int x, int y, uint8_t level) {
  if (level == 0) return false;
  if (level == 255) return true;
  return dither4x4(x, y) < (uint8_t)((level + 15) / 16);
}

static float wrapTrack(float s) {
  while (s < 0.0f) s += TRACK_LEN_MM;
  while (s >= TRACK_LEN_MM) s -= TRACK_LEN_MM;
  return s;
}

// Map arc length s (mm) along the rounded track to a centre-relative point.
static void trackPoint(float s, float &x, float &y) {
  s = wrapTrack(s);
  const float q = TRACK_Q_MM;
  const float top = TRACK_W_MM - 2.0f * TRACK_R_MM;
  const float side = TRACK_H_MM - 2.0f * TRACK_R_MM;
  const float leftX = -TRACK_AX_MM - TRACK_R_MM;
  const float rightX = TRACK_AX_MM + TRACK_R_MM;
  const float topY = -TRACK_AY_MM - TRACK_R_MM;
  const float bottomY = TRACK_AY_MM + TRACK_R_MM;

  if (s < TRACK_AY_MM) {
    x = leftX;
    y = -s;
    return;
  }
  s -= TRACK_AY_MM;

  if (s < q) {
    float a = 3.1415927f + s / TRACK_R_MM;
    x = -TRACK_AX_MM + cosf(a) * TRACK_R_MM;
    y = -TRACK_AY_MM + sinf(a) * TRACK_R_MM;
    return;
  }
  s -= q;

  if (s < top) {
    x = -TRACK_AX_MM + s;
    y = topY;
    return;
  }
  s -= top;

  if (s < q) {
    float a = 4.7123890f + s / TRACK_R_MM;
    x = TRACK_AX_MM + cosf(a) * TRACK_R_MM;
    y = -TRACK_AY_MM + sinf(a) * TRACK_R_MM;
    return;
  }
  s -= q;

  if (s < side) {
    x = rightX;
    y = -TRACK_AY_MM + s;
    return;
  }
  s -= side;

  if (s < q) {
    float a = s / TRACK_R_MM;
    x = TRACK_AX_MM + cosf(a) * TRACK_R_MM;
    y = TRACK_AY_MM + sinf(a) * TRACK_R_MM;
    return;
  }
  s -= q;

  if (s < top) {
    x = TRACK_AX_MM - s;
    y = bottomY;
    return;
  }
  s -= top;

  if (s < q) {
    float a = 1.5707963f + s / TRACK_R_MM;
    x = -TRACK_AX_MM + cosf(a) * TRACK_R_MM;
    y = TRACK_AY_MM + sinf(a) * TRACK_R_MM;
    return;
  }
  s -= q;

  x = leftX;
  y = TRACK_AY_MM - s;
}

// True when pixel (x, y) lies under the rounded "train" capsule whose leading
// edge is at headMm along the track.
static bool inTrainCapsule(int x, int y, float headMm) {
  float px = ((float)x + 0.5f) / PX_PER_MM_X - SE_CENTER_X_MM;
  float py = ((float)y + 0.5f) / PX_PER_MM_Y - SE_CENTER_Y_MM;
  float r = SI_INSET_MM * 0.5f;
  float r2 = r * r;
  float coreLen = TRAIN_MM - 2.0f * r;

  if (coreLen <= 0.0f) {
    float cx, cy;
    trackPoint(headMm - TRAIN_MM * 0.5f, cx, cy);
    float dx = px - cx, dy = py - cy;
    return dx * dx + dy * dy <= (TRAIN_MM * 0.5f) * (TRAIN_MM * 0.5f);
  }

  float start = headMm - TRAIN_MM + r;
  const uint8_t samples = 6;
  for (uint8_t i = 0; i <= samples; i++) {
    float s = start + coreLen * (float)i / (float)samples;
    float cx, cy;
    trackPoint(s, cx, cy);
    float dx = px - cx, dy = py - cy;
    if (dx * dx + dy * dy <= r2) return true;
  }
  return false;
}

// ============================================================================
//  Panel lifecycle
// ============================================================================
void DisplayBlock::begin() {
  Wire.begin();
  initPanel();
  panelOk_ = panelPresent();
  blank();
  idle_ = true;
}

void DisplayBlock::initPanel() {
  u8g2_.setI2CAddress(I2C_ADDRESS_7BIT * 2);  // U8g2 wants the 8-bit address
  u8g2_.begin();
  Wire.setClock(400000);  // faster refresh; drop to 100000 if the bus is noisy
  u8g2_.setContrast(255);
  contrast_ = 255;
  u8g2_.setDrawColor(1);
}

bool DisplayBlock::panelPresent() {
  Wire.beginTransmission(I2C_ADDRESS_7BIT);
  return Wire.endTransmission() == 0;
}

void DisplayBlock::setContrast(uint8_t value) {
  if (value != contrast_) {
    u8g2_.setContrast(value);
    contrast_ = value;
  }
}

// ============================================================================
//  Public input
// ============================================================================
void DisplayBlock::run(uint8_t behavior, uint8_t fillPercent) {
  behavior_    = behavior;
  fillPercent_ = (fillPercent > 100) ? 100 : fillPercent;
  phase_       = 0;
  phaseStart_  = millis();
  lastFrame_   = 0;
  idle_        = false;

  switch (behavior) {
    case GAUGE:            drawGaugeFill(fillPercent_); setContrast(0); break;
    case ALERT_THEN_GAUGE: drawFullScreen();            setContrast(0); break;
    case CLEAR:            break;  // update() will blank on the next tick
    default:
      if (behavior >= LISTENING && behavior <= SPEAKING) setContrast(255);
      break;
  }
}

// ============================================================================
//  Heartbeat — call every loop()
// ============================================================================
void DisplayBlock::update() {
  uint32_t now = millis();

  // Hot-reconnect: notice the panel coming back on the I2C bus.
  if (now - lastCheck_ >= CHECK_MS) {
    lastCheck_ = now;
    bool present = panelPresent();
    if (present && !panelOk_) {
      panelOk_ = true;
      initPanel();
      u8g2_.sendBuffer();  // re-push whatever was last drawn
    } else if (!present && panelOk_) {
      panelOk_ = false;
    }
  }
  if (!panelOk_) return;

  switch (behavior_) {
    case GAUGE:            runGaugeCinematic(now, 0); refreshStatic(now); break;
    case CLEAR:            if (!idle_) { blank(); idle_ = true; } break;
    case ALERT_THEN_GAUGE: runAlertThenGauge(now); refreshStatic(now); break;
    default:
      if (behavior_ >= LISTENING && behavior_ <= SPEAKING) runLiveAnimation(now);
      break;
  }
}

// Re-push the current (static) frame buffer on a throttle, so an occasional
// corrupted I2C transfer cannot leave stale pixels stuck on screen.
void DisplayBlock::refreshStatic(uint32_t now) {
  if (idle_) return;
  if (now - lastRedraw_ < REDRAW_MS) return;
  lastRedraw_ = now;
  u8g2_.sendBuffer();
}

// ============================================================================
//  Drawing primitives
// ============================================================================
void DisplayBlock::drawGaugeFill(uint8_t percent) {
  const float fullArc = 360.0f - GAP_DEG;
  const float swept   = MIN_DEG + (percent / 100.0f) * (fullArc - MIN_DEG);

  u8g2_.clearBuffer();
  u8g2_.setDrawColor(1);
  for (int y = 0; y < 64; y++) {
    for (int x = 0; x < 128; x++) {
      if (!inGaugeRing(x, y)) continue;
      float dy = ((float)y + 0.5f) - SE_CY_PX;
      float dx = ((float)x + 0.5f) - SE_CX_PX;
      float ang = atan2f(dy, dx) * DEG;
      if (ang < 0) ang += 360.0f;
      float delta = fmodf((float)FILL_DIR * (ang - FILL_START_DEG) + 720.0f, 360.0f);
      if (delta <= swept) u8g2_.drawPixel(x, y);
    }
  }
  u8g2_.sendBuffer();
}

void DisplayBlock::drawFullRingLevel(uint8_t level) {
  u8g2_.clearBuffer();
  u8g2_.setDrawColor(1);
  for (int y = 0; y < 64; y++) {
    for (int x = 0; x < 128; x++) {
      if (inGaugeRing(x, y) && pixelAtLevel(x, y, level)) u8g2_.drawPixel(x, y);
    }
  }
}

void DisplayBlock::drawTravellingSegment(float headMm) {
  u8g2_.clearBuffer();
  u8g2_.setDrawColor(1);
  for (int y = 0; y < 64; y++) {
    for (int x = 0; x < 128; x++) {
      if (!inGaugeRing(x, y)) continue;
      if (inTrainCapsule(x, y, headMm)) u8g2_.drawPixel(x, y);
    }
  }
}

void DisplayBlock::drawFullScreen() {
  u8g2_.clearBuffer();
  u8g2_.setDrawColor(1);
  u8g2_.drawBox(0, 0, 128, 64);
  u8g2_.sendBuffer();
}

void DisplayBlock::blank() {
  u8g2_.clearBuffer();
  u8g2_.sendBuffer();
}

// ============================================================================
//  Animation drivers
// ============================================================================
// Gauge cinematic: fade-in -> hold -> fade-out, then idle.
void DisplayBlock::runGaugeCinematic(uint32_t now, uint8_t basePhase) {
  uint8_t  localPhase = phase_ - basePhase;
  uint32_t elapsed    = now - phaseStart_;
  switch (localPhase) {
    case 0:  // FADE IN
      setContrast(elapsed >= FADE_MS ? 255 : (uint8_t)(255UL * elapsed / FADE_MS));
      if (elapsed >= FADE_MS) { phase_ = basePhase + 1; phaseStart_ = now; }
      break;
    case 1:  // HOLD at full brightness
      setContrast(255);
      if (elapsed >= STAY_MS) { phase_ = basePhase + 2; phaseStart_ = now; }
      break;
    case 2:  // FADE OUT
      setContrast(elapsed >= FADE_MS ? 0 : (uint8_t)(255UL - 255UL * elapsed / FADE_MS));
      if (elapsed >= FADE_MS) {
        phase_ = basePhase + 3;
        phaseStart_ = now;
        blank();
        setContrast(255);
      }
      break;
    default:  // DONE
      idle_ = true;
      break;
  }
}

// Behavior 5: two full-screen flashes, a pause, then the gauge cinematic.
void DisplayBlock::runAlertThenGauge(uint32_t now) {
  uint32_t elapsed = now - phaseStart_;
  switch (phase_) {
    case 0:  // flash 1 up
      setContrast(elapsed >= FLASH_MS ? 255 : (uint8_t)(255UL * elapsed / FLASH_MS));
      if (elapsed >= FLASH_MS) { phase_ = 1; phaseStart_ = now; }
      break;
    case 1:  // flash 1 down
      setContrast(elapsed >= FLASH_MS ? 0 : (uint8_t)(255UL - 255UL * elapsed / FLASH_MS));
      if (elapsed >= FLASH_MS) { phase_ = 2; phaseStart_ = now; }
      break;
    case 2:  // gap
      if (elapsed >= FLASH_GAP_MS) { phase_ = 3; phaseStart_ = now; }
      break;
    case 3:  // flash 2 up
      setContrast(elapsed >= FLASH_MS ? 255 : (uint8_t)(255UL * elapsed / FLASH_MS));
      if (elapsed >= FLASH_MS) { phase_ = 4; phaseStart_ = now; }
      break;
    case 4:  // flash 2 down
      setContrast(elapsed >= FLASH_MS ? 0 : (uint8_t)(255UL - 255UL * elapsed / FLASH_MS));
      if (elapsed >= FLASH_MS) {
        blank();
        setContrast(255);
        phase_ = 5;
        phaseStart_ = now;
      }
      break;
    case 5:  // wait, then draw the gauge dark and hand over to the cinematic
      if (elapsed >= FLASH_WAIT_MS) {
        drawGaugeFill(fillPercent_);
        setContrast(0);
        phase_ = 6;
        phaseStart_ = now;
      }
      break;
    default:  // gauge fade-in / hold / fade-out (phases 6..9)
      runGaugeCinematic(now, 6);
      break;
  }
}

// Behaviors 2/3/4: continuously redrawn live animations (throttled to FRAME_MS).
void DisplayBlock::runLiveAnimation(uint32_t now) {
  if (now - lastFrame_ < FRAME_MS) return;
  lastFrame_ = now;
  float t = (now - phaseStart_) / 1000.0f;

  u8g2_.clearBuffer();
  u8g2_.setDrawColor(1);

  if (behavior_ == LISTENING) {  // full ring breathing in brightness
    float phase = fmodf(t / 3.0f, 1.0f);
    setContrast(255);
    drawFullRingLevel((uint8_t)(255.0f * easeInOut(phase)));
  } else if (behavior_ == THINKING) {  // a 10 mm segment travels the ring
    setContrast(255);
    float head = fmodf((t * 1000.0f / 2200.0f) * TRACK_LEN_MM, TRACK_LEN_MM);
    drawTravellingSegment(head);
  } else if (behavior_ == SPEAKING) {  // full ring with a syllabic blink
    setContrast(255);
    drawFullRingLevel(speakingContrast(fmodf(t / 1.35f, 1.0f)));
  }

  u8g2_.sendBuffer();
}
