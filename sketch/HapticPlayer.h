#pragma once
#include <Arduino.h>

// ============================================================================
//  HapticPlayer — reusable block for an L9110-driven vibration motor
// ----------------------------------------------------------------------------
//  Encoding of the 7 behaviors (1 + 3 + 3), addressed by a single id 0..6:
//
//    rate of change -> number of pulses   (none / slow / medium / quick)
//    direction      -> playback order     (up = as listed, down = reversed)
//    each pulse     -> ramp up + hold + ramp down + optional brake kick
//
//    0 NO_CHANGE
//    1 UP_SLOW     2 UP_MEDIUM     3 UP_QUICK
//    4 DOWN_SLOW   5 DOWN_MEDIUM   6 DOWN_QUICK
//
//  Two ways to drive it:
//
//    Blocking (simplest):
//      HapticPlayer haptics;
//      haptics.begin(9, 10);                   // IA pin, IB pin
//      haptics.play(HapticPlayer::UP_MEDIUM);  // returns when the pattern ends
//
//    Non-blocking (for orchestrators that also do other work):
//      haptics.start(HapticPlayer::UP_MEDIUM);
//      ...
//      haptics.update();    // call every loop() tick
//      haptics.isBusy();    // true while a pattern is playing
// ============================================================================
class HapticPlayer {
 public:
  enum Behavior {
    NO_CHANGE = 0,
    UP_SLOW, UP_MEDIUM, UP_QUICK,
    DOWN_SLOW, DOWN_MEDIUM, DOWN_QUICK,
    BEHAVIOR_COUNT  // == 7
  };

  // Configure the two L9110 control pins and leave the motor stopped.
  void begin(int iaPin, int ibPin);

  // Blocking convenience: start a behavior and spin until it finishes.
  // Accepts a Behavior or its raw int id (0..6); out-of-range ids are ignored.
  void play(int behavior);

  // Start a behavior without blocking. Returns false if the id is invalid or
  // another pattern is still running.
  bool start(int behavior);

  // Advance the running pattern. Safe (and cheap) to call when idle.
  void update();

  bool isBusy() const { return busy_; }

  // Stop immediately and release the motor.
  void stop();

 private:
  static constexpr int MIN_SPIN  = 60;   // below this the motor barely turns
  static constexpr int BRAKE_PWM = 200;  // reverse drive used as a brake kick

  enum Stage : uint8_t {
    STAGE_IDLE = 0,
    STAGE_RAMP_UP,
    STAGE_HOLD,
    STAGE_RAMP_DOWN,
    STAGE_BRAKE,
    STAGE_GAP,
  };

  // One vibration "shape", replayed once per pulse.
  struct Pattern {
    int pulses;
    int rampUpMs, holdMs, rampDownMs, brakeMs, gapMs;
    int speeds[4];
  };

  // The four rate presets (no-change / slow / medium / quick).
  static const Pattern *presets();

  int      iaPin_       = 9;
  int      ibPin_       = 10;
  bool     busy_        = false;
  bool     up_          = true;
  int      rate_        = 0;
  int      targetSpeed_ = 0;
  uint8_t  pulseIndex_  = 0;
  Stage    stage_       = STAGE_IDLE;
  uint32_t stageStart_  = 0;

  int  clampSpeed(int v) const;
  void coast();
  void driveForward(int speed);
  void enterStage(Stage stage);
  void beginPulse();
  void finish();
};
