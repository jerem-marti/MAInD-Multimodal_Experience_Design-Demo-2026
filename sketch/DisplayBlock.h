#pragma once
#include <Arduino.h>
#include <Wire.h>
#include <U8g2lib.h>

// ============================================================================
//  DisplayBlock — self-contained OLED feedback block
//  (UNO Q + 0.96" 128x64 SSD1306 on the Wire bus, header SDA/SCL)
// ----------------------------------------------------------------------------
//  Orchestrator contract:
//    - call begin()  once in setup()
//    - call update() on every loop() tick   (advances animations + reconnects)
//    - call run(behavior, fillPercent)       when the displayed state changes
//
//  The block owns all of its timing, I2C reconnect handling, drawing geometry,
//  brightness animation and private state. It never calls into other blocks.
//
//  Geometry: SE is the outer rounded squircle; SI is SE inset inward. Every
//  gauge / VUI drawing lives in the elongated ring between SE and SI.
//  Tune the shape and timing in DisplayConfig.h.
// ============================================================================
class DisplayBlock {
 public:
  // Behaviors selected through run(). Numeric values are the wire protocol
  // shared with the MPU control panel, so keep them stable.
  enum Behavior : uint8_t {
    GAUGE            = 0,  // fade-in, 6 s hold, fade-out of a radial fill gauge
    CLEAR            = 1,  // blank the panel
    LISTENING        = 2,  // full ring breathes in brightness
    THINKING         = 3,  // a rounded 10 mm segment travels around the ring
    SPEAKING         = 4,  // full ring blinks with a syllabic rhythm
    ALERT_THEN_GAUGE = 5,  // two full-screen flashes, a pause, then the gauge
  };

  void begin();
  void run(uint8_t behavior, uint8_t fillPercent);  // request a state change
  void update();                                    // call every loop()
  bool isIdle() const { return idle_; }

 private:
  U8G2_SSD1306_128X64_NONAME_F_HW_I2C u8g2_ =
      U8G2_SSD1306_128X64_NONAME_F_HW_I2C(U8G2_R0, U8X8_PIN_NONE);

  // Active behavior and its parameters.
  uint8_t  behavior_   = CLEAR;
  uint8_t  fillPercent_ = 0;

  // Animation sequencing.
  uint8_t  phase_      = 0;
  uint32_t phaseStart_ = 0;
  uint32_t lastFrame_  = 0;
  bool     idle_       = true;

  // Panel state.
  uint8_t  contrast_   = 255;
  uint32_t lastCheck_  = 0;
  uint32_t lastRedraw_ = 0;
  bool     panelOk_    = false;

  // --- Panel lifecycle ---
  void initPanel();
  bool panelPresent();
  void setContrast(uint8_t value);

  // --- Drawing primitives ---
  void drawGaugeFill(uint8_t percent);      // radial SE/SI fill (behaviors 0/5)
  void drawFullRingLevel(uint8_t level);    // dithered SE/SI ring
  void drawTravellingSegment(float headMm); // moving rounded segment
  void drawFullScreen();                    // all pixels on
  void blank();                             // all pixels off

  // --- Animation drivers (called from update()) ---
  void runGaugeCinematic(uint32_t now, uint8_t basePhase);  // fade-in/hold/out
  void runAlertThenGauge(uint32_t now);                     // behavior 5
  void runLiveAnimation(uint32_t now);                      // behaviors 2/3/4
  void refreshStatic(uint32_t now);  // re-send static frames to heal I2C glitches
};
