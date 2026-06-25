#pragma once
#include <Arduino.h>

// ============================================================================
//  DisplayConfig — tunable parameters for the OLED feedback block
// ----------------------------------------------------------------------------
//  Everything you might want to adjust without touching the drawing code lives
//  here: panel geometry, the gauge shape, animation timing and the I2C address.
//  The DisplayBlock implementation derives all pixel-space values from these.
//
//  Units:  *_MM are millimetres on the physical panel, *_MS are milliseconds,
//          *_DEG are degrees.
// ============================================================================
namespace DisplayConfig {

// --- Panel ------------------------------------------------------------------
// 7-bit I2C address of the SSD1306 controller (0x3C is the common default).
constexpr uint8_t I2C_ADDRESS_7BIT = 0x3C;

// Active area of the 0.96" 128x64 OLED, used for the mm-to-pixel conversion.
constexpr float PANEL_W_MM = 22.0f;
constexpr float PANEL_H_MM = 11.0f;

// --- Gauge geometry ---------------------------------------------------------
// SE = outer reference squircle (the lit ring lives just inside it).
// SI = inner black squircle, formed by insetting SE inward by SI_INSET_MM.
// Move the whole gauge by changing SE_CENTER_X_MM / SE_CENTER_Y_MM.
constexpr float SE_CENTER_X_MM = 11.0f;
constexpr float SE_CENTER_Y_MM = 5.5f;
constexpr float SE_W_MM        = 22.0f;
constexpr float SE_H_MM        = 11.0f;
constexpr float SE_CORNER_MM   = 5.0f;
constexpr float SI_INSET_MM    = 3.0f;

// Length of the rounded "train" that travels the ring in the thinking animation.
constexpr float TRAIN_MM = 10.0f;

// --- Gauge fill sweep -------------------------------------------------------
constexpr float GAP_DEG        = 0.0f;    // 0 -> the ring closes fully at 100%
constexpr float MIN_DEG        = 9.0f;    // short stub of light shown at 0%
constexpr float FILL_START_DEG = 172.0f;  // seam where the fill starts (left side)
constexpr int   FILL_DIR       = -1;      // sweep direction (+1 / -1)

// --- Animation timing -------------------------------------------------------
constexpr uint16_t FADE_MS       = 600;   // gauge fade-in / fade-out duration
constexpr uint16_t STAY_MS       = 6000;  // gauge hold at full brightness
constexpr uint16_t FLASH_MS      = 240;   // single full-screen flash ramp
constexpr uint16_t FLASH_GAP_MS  = 500;   // pause between the two alert flashes
constexpr uint16_t FLASH_WAIT_MS = 1000;  // pause after flashes, before the gauge
constexpr uint16_t FRAME_MS      = 33;    // ~30 fps cap for the live animations
constexpr uint32_t CHECK_MS      = 400;   // how often to probe for the I2C panel
constexpr uint16_t REDRAW_MS     = 100;   // re-send rate for static frames (see below)

// Static behaviors (gauge, alert) write the OLED only once and then animate
// only the contrast. If a single I2C transfer is corrupted, stale pixels stay
// on screen until the next behavior. Re-sending the buffer every REDRAW_MS
// heals such glitches, exactly like the continuously-redrawn VUI frames do.

}  // namespace DisplayConfig
