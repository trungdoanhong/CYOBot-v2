#pragma once
#include <stdint.h>
#include <string.h>

namespace cyo {
// Ownership tolerates short WLAN bursts; the PC separately freezes motion on
// stale feedback. There is no autonomous motion to continue during an outage.
constexpr uint16_t PORT = 4242, LEASE_MS = 1000;
// Preserve the old PCA driver timing and tick limits (60 Hz * 0.9 correction).
constexpr uint16_t PRESCALE = 112, MIN_TICK = 120, MAX_TICK = 600;
enum Type : uint8_t { DISCOVER=1, INFO=2, CLAIM=3, FRAME=4, RELEASE=5, OFF=6, STATUS=7, LED_FRAME=8, LED_STATUS=9, DIAG_QUERY=10, DIAGNOSTICS=11 };
enum Flags : uint16_t { OWNED=1, HOLDING=2, PWM_OK=4, IMU_OK=8, FAULT=16, WIFI_OK=32, LED_READY=64, SD_READY=128, AUDIO_READY=256, MEDIA_READY=512 };
#pragma pack(push, 1)
struct Header { char magic[4]; uint8_t version, type; uint16_t length; uint32_t session, seq; };
struct Info { uint8_t mac[6]; uint32_t boot, challenge; uint16_t flags, port, prescale, minimum, maximum, lease_ms; };
struct Claim { uint32_t boot, challenge; };
struct Frame { uint16_t ticks[16]; };
// Physical chain order, RGB on the wire: matrix 0..32, then ring 0..11.
struct LedFrame { uint8_t matrix[33][3], ring[12][3]; };
struct LedStatus { uint32_t applied_seq; LedFrame pixels; };
// Read-only, including after a lease expires. Does not renew command ownership.
struct Diagnostics {
    uint32_t boot, uptime_ms, session, command_age_ms, received, rejected;
    uint32_t max_loop_us, wifi_losses, lease_expirations, send_errors;
    int16_t rssi;
    uint16_t release_reason; // 0=none, 1=lease, 2=Wi-Fi, 3=release, 4=off, 5=I2C fault
};
struct Status {
    uint32_t uptime_us, accepted_seq, applied_seq, received, applied, rejected;
    uint16_t flags, buttons, battery_mv, apply_us;
    uint32_t imu_us;
    int16_t imu[6]; // gx, gy, gz, ax, ay, az; raw LSM6DSL counts
    uint16_t ticks[16]; // commanded PWM, NOT measured joint angles
};
#pragma pack(pop)
static_assert(sizeof(Header)==16 && sizeof(Info)==26 && sizeof(Status)==80, "Wire layout");
static_assert(sizeof(LedFrame)==135 && sizeof(LedStatus)==139, "LED wire layout");
static_assert(sizeof(Diagnostics)==44, "Diagnostics wire layout");
inline bool newer(uint32_t candidate, uint32_t previous) {
    const uint32_t delta = candidate - previous;
    return delta != 0 && delta < 0x80000000UL;
}
inline bool validFrame(const Frame& f) {
    for (auto t : f.ticks) if (t != 0 && (t < MIN_TICK || t > MAX_TICK)) return false;
    return true;
}
inline Header header(uint8_t type, uint16_t length, uint32_t session, uint32_t seq) {
    Header h = {{'C','Y','O','2'}, 1, type, length, session, seq};
    return h;
}
}
