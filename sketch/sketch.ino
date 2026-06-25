#include "Arduino_RouterBridge.h"
#include "DisplayBlock.h"
#include "HapticPlayer.h"

// L9110 motor driver inputs.
constexpr int HAPTIC_PIN_IA = 9;   // IA -> D9
constexpr int HAPTIC_PIN_IB = 10;  // IB -> D10

// Hardware push button (to GND, internal pull-up): idles HIGH, LOW when pressed.
constexpr int      BUTTON_PIN         = 2;
constexpr uint32_t BUTTON_DEBOUNCE_MS = 25;
constexpr uint32_t HOLD_MS            = 1500;  // >= this while down => "hold"

DisplayBlock  display;
HapticPlayer  haptics;

// ── Button state (debounced) + tap/hold classification ──────────────────
int      btnStable     = HIGH;      // debounced level
int      btnRawLast    = HIGH;
uint32_t btnChangedAt  = 0;
uint32_t btnPressStart = 0;
bool     btnDown       = false;
bool     holdFired     = false;     // hold already emitted for this press

// ── DOWN handlers (run in loop() context: touch Wire/analogWrite/delay) ──
void playHapticAndDisplay(int hid, int gid, int fill) {
  fill = constrain(fill, 0, 100);
  haptics.start(hid);                      // non-blocking: advanced by haptics.update() in loop()
  display.run((uint8_t)gid, (uint8_t)fill);
}

void playDisplay(int gid, int fill) {
  fill = constrain(fill, 0, 100);
  haptics.stop();                          // a screen-only change (e.g. tap→CAW) cuts any
  display.run((uint8_t)gid, (uint8_t)fill); // in-flight buzz, so haptic ends with the animation
}

void setup() {
  display.begin();
  haptics.begin(HAPTIC_PIN_IA, HAPTIC_PIN_IB);
  pinMode(BUTTON_PIN, INPUT_PULLUP);

  Bridge.begin();
  Bridge.provide_safe("playHapticAndDisplay", playHapticAndDisplay);
  Bridge.provide_safe("playDisplay", playDisplay);
}

void updateButton() {
  int raw = digitalRead(BUTTON_PIN);
  if (raw != btnRawLast) {
    btnRawLast = raw;
    btnChangedAt = millis();
  } else if (millis() - btnChangedAt >= BUTTON_DEBOUNCE_MS && raw != btnStable) {
    btnStable = raw;
    if (btnStable == LOW) {              // press begins
      btnDown = true;
      holdFired = false;
      btnPressStart = millis();
      Bridge.call("on_button", "down");  // raw press-down — drives the on-screen finger
    } else {                             // release
      if (btnDown && !holdFired) {
        Bridge.call("on_button", "tap"); // short press => tap (gesture logic)
      }
      btnDown = false;
      Bridge.call("on_button", "up");    // raw release — retracts the on-screen finger
    }
  }
  // long press fires "hold" once, without waiting for release
  if (btnDown && !holdFired && millis() - btnPressStart >= HOLD_MS) {
    holdFired = true;
    Bridge.call("on_button", "hold");
  }
}

void loop() {
  display.update();
  haptics.update();   // advance the (non-blocking) buzz so loop() never stalls on it
  updateButton();
}
