import json
import math
from pathlib import Path
import socket
import struct
import sys
import time
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "host"))
from cyobot import *
from gait import CrawlerGait, GAITS


def robot(index=1):
    return Robot(f"00:00:00:00:00:{index:02x}", (f"127.0.0.{index}", PORT),
                 123, 456, PWM_OK | IMU_OK, 112, 120, 600, 250)


def status_body(uptime=100, seq=2, flags=OWNED | PWM_OK | IMU_OK, ticks=None):
    return STATUS_BODY.pack(uptime, seq, seq, 1, 1, 0, flags, 3, 7400, 1500, uptime,
                            100, -100, 0, 8197, 0, -8197, *(ticks or [0]*16))


class ProtocolTests(unittest.TestCase):
    def test_led_frame_physical_order_and_validation(self):
        matrix=[[i,0,255-i] for i in range(33)]
        ring=[[0,255,i] for i in range(12)]
        raw=led_bytes(matrix,ring)
        self.assertEqual(len(raw),135)
        self.assertEqual(raw[:3],bytes([0,0,255]))
        self.assertEqual(raw[96:102],bytes([32,0,223,0,255,0]))
        self.assertEqual(decode_led_status(struct.pack('<I',42)+raw),dict(applied_seq=42,matrix=matrix,ring=ring))
        for invalid in (matrix[:-1], [[True,0,0]]*33, [[256,0,0]]*33, [[1.2,0,0]]*33):
            with self.assertRaises(ValueError):led_bytes(invalid,ring)

    def test_led_ack_session_reordering_does_not_refresh_servo_telemetry(self):
        with Fleet(bind='127.0.0.1') as f:
            r=robot();r.session=12;r.flags|=LED_READY
            f._addresses[r.address]=r
            body=struct.pack('<I',8)+led_bytes([[10,20,30]]*33,[[40,50,60]]*12)
            f._accept_status(LED_STATUS,13,8,body,r.address)
            self.assertIsNone(r.leds)
            f._accept_status(LED_STATUS,12,8,body,r.address)
            self.assertEqual(r.leds['matrix'][32],[10,20,30])
            self.assertEqual(r.seen_at,0)
            for invalid in (struct.pack('<I',7)+body[4:],body[:-1]):
                f._accept_status(LED_STATUS,12,7,invalid,r.address)
            self.assertEqual(r.leds['applied_seq'],8)

    def test_golden_discovery_header(self):
        self.assertEqual(packet(DISCOVER, seq=0x12345678).hex(),
                         "43594f32010100000000000078563412")

    def test_reject_truncated_appended_and_wrong_version(self):
        valid = packet(FRAME, 1, 2, FRAME_BODY.pack(*([360]*16)))
        for bad in (valid[:4], valid[:-1], valid+b"x", valid[:4]+b"\x02"+valid[5:]):
            with self.assertRaises(ValueError):
                unpack(bad)
        self.assertEqual(unpack(valid)[3], FRAME_BODY.pack(*([360]*16)))

    def test_sequence_wrap_reordering_and_duplicates(self):
        self.assertTrue(is_newer(0, 0xFFFFFFFF))
        self.assertFalse(is_newer(5, 5))
        self.assertFalse(is_newer(0xFFFFFFFF, 0))
        self.assertFalse(is_newer(0x80000000, 0))

    def test_telemetry_units_and_signed_axes(self):
        s = decode_status(status_body())
        self.assertAlmostEqual(s["battery_v"], 7.4)
        self.assertAlmostEqual(s["gyro_dps"][1], -1.75)
        self.assertAlmostEqual(s["accel_g"][0], 1, places=3)
        self.assertEqual(s["buttons"], 3)
        self.assertEqual(len(s["ticks"]), 16)

    def test_30_robot_telemetry_routing_and_session_isolation(self):
        with Fleet(bind="127.0.0.1") as f:
            robots = [robot(i) for i in range(1,31)]
            for r in robots:
                r.session = 99
                f.robots[r.mac] = r
                f._addresses[r.address] = r
            for i, r in enumerate(reversed(robots)):
                f._accept_status(STATUS, 99, 2, status_body(uptime=100+i), r.address)
            self.assertTrue(all(r.telemetry for r in robots))
            r = robots[0]
            previous = r.telemetry
            f._accept_status(STATUS, 100, 2, status_body(uptime=500), r.address)
            f._accept_status(STATUS, 99, 2, status_body(uptime=1), r.address)
            self.assertIs(r.telemetry, previous)
            f._accept_status(STATUS, 99, 2, status_body(uptime=501), r.address)
            self.assertEqual(r.telemetry["uptime_us"], 501)

    def test_invalid_actions_never_send(self):
        with Fleet(bind="127.0.0.1") as f:
            r = robot()
            r.session = 1
            f._send = Mock()
            for values in ([0]*15, [119]*16, [601]*16, [float("nan")]*16, [True]*16):
                with self.assertRaises(ValueError):
                    f.send_ticks(r, values)
            f._send.assert_not_called()

    def test_expired_observations_stop_policy(self):
        with Fleet(bind="127.0.0.1") as f:
            r = robot()
            r.lease_ms = 1000
            r.session = 1
            r.flags |= OWNED
            r.telemetry = decode_status(status_body())
            r.seen_at = time.perf_counter() - .3
            policy = Mock()
            with self.assertRaises(TimeoutError):
                f.run([r], policy, seconds=.1)
            policy.assert_not_called()

    def test_diagnostic_reply_is_read_only_and_cannot_refresh_telemetry(self):
        with Fleet(bind='127.0.0.1') as f:
            r=robot(); f._addresses[r.address]=r
            body=DIAG_BODY.pack(123,4000,0,1100,30,2,6000,0,1,0,-65,1)
            f._accept_status(DIAGNOSTICS,0,12,body,r.address)
            self.assertEqual(r.diagnostics['release_reason'],1)
            self.assertEqual(r.diagnostics['rssi'],-65)
            self.assertEqual(r.session,0)
            self.assertEqual(r.seen_at,0)
            self.assertIsNone(r.telemetry)

    def test_stalled_uplink_stops_ai_even_with_fresh_downlink(self):
        with Fleet(bind='127.0.0.1') as f:
            r=robot();r.lease_ms=1000;r.session=10;r.flags|=OWNED
            r.telemetry=decode_status(status_body())
            r.seen_at=time.perf_counter();r.progress_at=r.seen_at-.3
            r.sent_at[3]=r.seen_at-.3
            policy=Mock()
            with self.assertRaises(TimeoutError):f.run([r],policy,seconds=.1)
            policy.assert_not_called()

    def test_missing_policy_action_does_not_replay(self):
        with Fleet(bind="127.0.0.1") as f:
            r = robot()
            r.session, r.flags, r.seen_at = 1, OWNED | PWM_OK, time.perf_counter()
            r.telemetry = decode_status(status_body())
            f.send_ticks = Mock()
            f.run([r], lambda _: {}, seconds=.03)
            f.send_ticks.assert_not_called()


class CalibrationTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((Path(__file__).resolve().parents[2] / "MicroPython/sd/config/robot-config.json").read_text())
        self.mapping = JointMap(self.config)

    def test_center_and_unused_channels(self):
        ticks = self.mapping.ticks([0]*8)
        self.assertEqual(sum(v != 0 for v in ticks), 8)
        self.assertEqual(ticks[4], 360)
        self.assertEqual(ticks[2], 0)

    def test_orientation_offset_and_roundtrip(self):
        self.config["motor"]["leg0"]["upper"]["offset"] = 5
        mapping = JointMap(self.config)
        angles = [30, 0, 0, 0, 0, 0, 0, 0]
        ticks = mapping.ticks(angles)
        self.assertEqual(ticks[4], round(120+65*480/180))
        self.assertAlmostEqual(mapping.angles(ticks)[0], 30, delta=.2)

    def test_reject_nonfinite_and_out_of_bounds(self):
        for angle in (91, -91, math.inf, math.nan):
            with self.assertRaises(ValueError):
                self.mapping.ticks([angle]*8)

    def test_duplicate_channel(self):
        self.config["motor"]["leg0"]["upper"]["pin"] = self.config["motor"]["leg0"]["lower"]["pin"]
        with self.assertRaises(ValueError):
            JointMap(self.config)

    def test_gait_original_phase_and_smooth_boundary(self):
        gait = CrawlerGait("forward", cycle_seconds=1)
        self.assertEqual(gait.angles(0), [0]*8)
        self.assertEqual(gait.angles(.25), [-20, -15, 30, 20, -20, -15, 30, 20])
        before, after = gait.angles(.999999), gait.angles(1.000001)
        self.assertLess(max(abs(a-b) for a,b in zip(before,after)), .01)
        for cmd in GAITS:
            for step in range(100):
                self.mapping.ticks(CrawlerGait(cmd).angles(step/100))


if __name__ == "__main__":
    unittest.main()
