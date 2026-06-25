#include "HapticPlayer.h"

// Speeds always climb to 255 on the last pulse; "down" behaviors replay them
// reversed. A function-local static keeps the table out of RAM until first use.
const HapticPlayer::Pattern *HapticPlayer::presets() {
  //                  pulses rampUp hold rampDn brake  gap   speeds
  static const Pattern P[4] = {
      { 1,   100,  400,  500,   0,    0, { 190,   0,   0,   0 } },  // 0 no change
      { 2,   200,  300,  200,   0,  300, { 170, 255,   0,   0 } },  // 1 slow
      { 3,   200,  400,    0,  30,  260, { 140, 200, 255,   0 } },  // 2 medium
      { 4,     0,  350,    0,  30,  180, { 145, 185, 225, 255 } },  // 3 quick
  };
  return P;
}

void HapticPlayer::begin(int iaPin, int ibPin) {
  iaPin_ = iaPin;
  ibPin_ = ibPin;
  pinMode(iaPin_, OUTPUT);
  pinMode(ibPin_, OUTPUT);
  stop();
}

void HapticPlayer::play(int behavior) {
  if (!start(behavior)) return;
  while (isBusy()) {
    update();
    delay(1);
  }
}

bool HapticPlayer::start(int behavior) {
  if (behavior < 0 || behavior >= BEHAVIOR_COUNT || busy_) return false;

  if (behavior == NO_CHANGE) {
    rate_ = 0;
    up_   = true;
  } else if (behavior <= UP_QUICK) {
    rate_ = behavior;
    up_   = true;
  } else {
    rate_ = behavior - 3;
    up_   = false;
  }

  pulseIndex_ = 0;
  busy_       = true;
  beginPulse();
  return true;
}

void HapticPlayer::update() {
  if (!busy_) return;

  const Pattern &p = presets()[rate_];
  const uint32_t now = millis();

  // The guard bounds how many stages can advance in a single call so that
  // zero-duration stages cannot spin forever.
  for (uint8_t guard = 0; guard < 8 && busy_; guard++) {
    const uint32_t elapsed = now - stageStart_;

    switch (stage_) {
      case STAGE_RAMP_UP:
        if (p.rampUpMs <= 0 || elapsed >= (uint32_t)p.rampUpMs) {
          driveForward(targetSpeed_);
          enterStage(STAGE_HOLD);
        } else {
          driveForward((targetSpeed_ * (int)elapsed) / p.rampUpMs);
          return;
        }
        break;

      case STAGE_HOLD:
        driveForward(targetSpeed_);
        if (p.holdMs <= 0 || elapsed >= (uint32_t)p.holdMs) {
          enterStage(STAGE_RAMP_DOWN);
        } else {
          return;
        }
        break;

      case STAGE_RAMP_DOWN:
        if (p.rampDownMs <= 0 || elapsed >= (uint32_t)p.rampDownMs) {
          coast();
          enterStage(STAGE_BRAKE);
        } else {
          const int speed = targetSpeed_ + ((0 - targetSpeed_) * (int)elapsed) / p.rampDownMs;
          if (speed > 0) driveForward(speed); else coast();
          return;
        }
        break;

      case STAGE_BRAKE:
        if (p.brakeMs <= 0 || elapsed >= (uint32_t)p.brakeMs) {
          coast();
          enterStage(STAGE_GAP);
        } else {
          analogWrite(iaPin_, 0);
          analogWrite(ibPin_, BRAKE_PWM);
          return;
        }
        break;

      case STAGE_GAP:
        if (pulseIndex_ >= p.pulses) {
          finish();
        } else if (p.gapMs <= 0 || elapsed >= (uint32_t)p.gapMs) {
          beginPulse();
        } else {
          return;
        }
        break;

      default:
        finish();
        break;
    }
  }
}

void HapticPlayer::stop() {
  coast();
  busy_  = false;
  stage_ = STAGE_IDLE;
}

int HapticPlayer::clampSpeed(int v) const {
  if (v <= 0)       return 0;
  if (v < MIN_SPIN) return MIN_SPIN;
  if (v > 255)      return 255;
  return v;
}

void HapticPlayer::coast() {
  analogWrite(iaPin_, 0);
  analogWrite(ibPin_, 0);
}

void HapticPlayer::driveForward(int speed) {
  analogWrite(ibPin_, 0);
  analogWrite(iaPin_, clampSpeed(speed));
}

void HapticPlayer::enterStage(Stage stage) {
  stage_ = stage;
  stageStart_ = millis();
}

void HapticPlayer::beginPulse() {
  const Pattern &p = presets()[rate_];
  if (pulseIndex_ >= p.pulses) {
    finish();
    return;
  }

  const int idx = up_ ? pulseIndex_ : (p.pulses - 1 - pulseIndex_);
  targetSpeed_ = clampSpeed(p.speeds[idx]);
  pulseIndex_++;
  coast();
  enterStage(STAGE_RAMP_UP);
}

void HapticPlayer::finish() {
  stop();
}
