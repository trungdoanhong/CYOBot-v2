"""Standard-library UDP client. One nonblocking socket for an entire robot fleet."""
from __future__ import annotations

import json
import math
import secrets
import select
import socket
import struct
import time
from dataclasses import dataclass, field
from pathlib import Path

PORT = 4242
DISCOVER, INFO, CLAIM, FRAME, RELEASE, OFF, STATUS = range(1, 8)
LED_FRAME, LED_STATUS, LED_READY = 8, 9, 64
SD_READY, AUDIO_READY, MEDIA_READY = 128, 256, 512
DIAG_QUERY, DIAGNOSTICS = 10, 11
DIAG_BODY = struct.Struct('<10IhH')
OWNED, HOLDING, PWM_OK, IMU_OK, FAULT, WIFI_OK = (1, 2, 4, 8, 16, 32)
HEADER = struct.Struct("<4sBBHII")
INFO_BODY = struct.Struct("<6sII6H")
STATUS_BODY = struct.Struct("<6I4HI6h16H")
FRAME_BODY = struct.Struct("<16H")
LED_BODY = struct.Struct("<135B")


def led_bytes(matrix, ring):
    for pixels, count in ((matrix, 33), (ring, 12)):
        if not isinstance(pixels, (list, tuple)) or len(pixels) != count:
            raise ValueError("Expected 33 matrix and 12 ring RGB pixels")
        if any(not isinstance(p, (list, tuple)) or len(p) != 3 or
               any(type(c) is not int or not 0 <= c <= 255 for c in p) for p in pixels):
            raise ValueError("RGB values must be integers in 0..255")
    return LED_BODY.pack(*(c for p in list(matrix)+list(ring) for c in p))


def decode_led_status(body):
    sequence, = struct.unpack_from("<I", body)
    colors = [list(body[i:i+3]) for i in range(4, 139, 3)]
    return dict(applied_seq=sequence, matrix=colors[:33], ring=colors[33:])


def packet(kind, session=0, seq=0, payload=b""):
    return HEADER.pack(b"CYO2", 1, kind, len(payload), session, seq) + payload


def unpack(data):
    if len(data) < HEADER.size:
        raise ValueError("Truncated header")
    magic, version, kind, size, session, seq = HEADER.unpack_from(data)
    if magic != b"CYO2" or version != 1 or len(data) != HEADER.size + size:
        raise ValueError("Invalid protocol/version/length")
    return kind, session, seq, data[HEADER.size:]


def is_newer(a, b):
    return 0 < ((a - b) & 0xFFFFFFFF) < 0x80000000


@dataclass
class Robot:
    mac: str
    address: tuple[str, int]
    boot: int
    challenge: int
    flags: int
    prescale: int
    minimum: int
    maximum: int
    lease_ms: int
    session: int = 0
    sequence: int = 0
    telemetry: dict | None = None
    seen_at: float = 0
    progress_at: float = 0
    sent_at: dict[int, float] = field(default_factory=dict)
    rtt_ms: list[float] = field(default_factory=list)
    _last_uptime: int | None = None
    leds: dict | None = None
    diagnostics: dict | None = None


def decode_info(body, address):
    mac, boot, challenge, flags, port, prescale, lo, hi, lease = INFO_BODY.unpack(body)
    return Robot(mac.hex(":"), (address[0], port), boot, challenge, flags, prescale, lo, hi, lease)


def decode_status(body):
    v = STATUS_BODY.unpack(body)
    return dict(uptime_us=v[0], accepted_seq=v[1], applied_seq=v[2], received=v[3],
                applied=v[4], rejected=v[5], flags=v[6], buttons=v[7], battery_v=v[8] / 1000,
                apply_us=v[9], imu_us=v[10], gyro_dps=[x * .0175 for x in v[11:14]],
                accel_g=[x * .000122 for x in v[14:17]], ticks=list(v[17:33]))


class Fleet:
    def __init__(self, bind="0.0.0.0"):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.socket.bind((bind, 0))
        self.socket.setblocking(False)
        self.robots: dict[str, Robot] = {}
        self._addresses = {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        # Preserve the user's requested HOLD policy, including exceptions/Ctrl+C.
        for robot in self.robots.values():
            if robot.session:
                try:
                    self.release(robot)
                except OSError:
                    pass
        self.socket.close()

    def discover(self, targets=("255.255.255.255",), timeout=1.0):
        seq = secrets.randbits(32)
        payload = packet(DISCOVER, seq=seq)
        for address in targets:
            self.socket.sendto(payload, (address, PORT))
        deadline = time.perf_counter() + timeout
        found = {}
        while time.perf_counter() < deadline:
            readable, _, _ = select.select([self.socket], [], [], max(0, deadline - time.perf_counter()))
            if not readable:
                break
            for kind, sid, sequence, body, address in self._receive():
                if kind == INFO and sequence == seq and len(body) == INFO_BODY.size:
                    robot = decode_info(body, address)
                    old = self.robots.get(robot.mac)
                    if old and old.session:
                        if old.boot != robot.boot:
                            raise RuntimeError(f"Robot rebooted: {old.mac}; reconnect explicitly")
                        if robot.flags & OWNED:
                            # Do not replace active command counters during discovery.
                            old.challenge, old.flags = robot.challenge, robot.flags
                            robot = old
                        else:
                            old.session = 0
                    self.robots[robot.mac] = robot
                    self._addresses[robot.address] = robot
                    found[robot.mac] = robot
                else:
                    self._accept_status(kind, sid, sequence, body, address)
        return list(found.values())

    def _receive(self, limit=512):
        for _ in range(limit):
            try:
                data, address = self.socket.recvfrom(2048)
            except BlockingIOError:
                return
            try:
                kind, sid, seq, body = unpack(data)
            except ValueError:
                continue
            yield kind, sid, seq, body, address

    def _accept_status(self, kind, sid, seq, body, address):
        robot = self._addresses.get(address)
        if kind == DIAGNOSTICS and not sid and len(body) == DIAG_BODY.size and robot:
            values = DIAG_BODY.unpack(body)
            robot.diagnostics = dict(zip(('boot','uptime_ms','session','command_age_ms','received','rejected',
                'max_loop_us','wifi_losses','lease_expirations','send_errors','rssi','release_reason'),values))
            return
        if kind == LED_STATUS and len(body) == 139 and robot and sid == robot.session and robot.session:
            leds = decode_led_status(body)
            if robot.leds is None or is_newer(leds["applied_seq"], robot.leds["applied_seq"]):
                robot.leds = leds
            return
        if kind != STATUS or len(body) != STATUS_BODY.size or not robot or sid != robot.session:
            return
        status = decode_status(body)
        # A delayed telemetry packet must not move the observed state backwards.
        if robot._last_uptime is not None and not is_newer(status["uptime_us"], robot._last_uptime):
            return
        robot._last_uptime = status["uptime_us"]
        now = time.perf_counter()
        if robot.telemetry is None or status['applied_seq'] != robot.telemetry['applied_seq']:
            robot.progress_at = now
        robot.telemetry, robot.seen_at, robot.flags = status, now, status["flags"]
        sent = robot.sent_at.pop(status["applied_seq"], None)
        if sent is not None:
            robot.rtt_ms.append((now - sent) * 1000)
            robot.rtt_ms[:] = robot.rtt_ms[-10000:]

    def poll(self, timeout=0.0):
        if timeout:
            select.select([self.socket], [], [], timeout)
        for event in self._receive():
            self._accept_status(*event)

    def claim(self, robot, timeout=0.15):
        if robot.session:
            raise RuntimeError("Already claimed")
        if not robot.flags & PWM_OK or robot.flags & FAULT:
            raise RuntimeError("PCA unavailable or firmware fault; inspect hardware")
        robot.session = secrets.randbits(32) or 1
        robot.sequence = 1
        robot.telemetry = None
        robot.leds = None
        robot._last_uptime = None
        body = struct.pack("<II", robot.boot, robot.challenge)
        message = packet(CLAIM, robot.session, robot.sequence, body)
        deadline = time.perf_counter() + timeout
        try:
            while time.perf_counter() < deadline:
                self.socket.sendto(message, robot.address)
                self.poll(min(.025, max(0, deadline - time.perf_counter())))
                if robot.telemetry and robot.flags & OWNED:
                    return
        except BaseException:
            robot.session = 0
            raise
        robot.session = 0
        raise TimeoutError(f"Cannot claim {robot.mac}: busy, stale discovery, or unreachable")

    def query_diagnostics(self, robot):
        """Read link counters without claiming or renewing a command session."""
        self.socket.sendto(packet(DIAG_QUERY, seq=secrets.randbits(32)), robot.address)

    def claim_all(self, robots):
        # Each earlier robot receives a same-pose frame while claiming the next one.
        # This avoids expiry of the first lease during large-fleet startup.
        claimed = []
        try:
            for robot in robots:
                for existing in claimed:
                    self.send_ticks(existing, existing.telemetry["ticks"])
                self.claim(robot)
                claimed.append(robot)
        except BaseException:
            for robot in claimed:
                self.release(robot)
            raise

    def _send(self, robot, kind, body=b""):
        if not robot.session:
            raise RuntimeError("Claim the robot first")
        robot.sequence = (robot.sequence + 1) & 0xFFFFFFFF
        self.socket.sendto(packet(kind, robot.session, robot.sequence, body), robot.address)
        return robot.sequence

    def send_ticks(self, robot, ticks):
        if len(ticks) != 16 or any(type(t) is not int or (t != 0 and not robot.minimum <= t <= robot.maximum) for t in ticks):
            raise ValueError("Expected 16 integer PWM ticks: 0=off or the advertised limits")
        seq = self._send(robot, FRAME, FRAME_BODY.pack(*ticks))
        robot.sent_at[seq] = time.perf_counter()
        if len(robot.sent_at) > 512:
            robot.sent_at.pop(next(iter(robot.sent_at)))
        return seq

    def send_leds(self, robot, matrix, ring):
        """Direct RGB frame; ACK arrives in robot.leds. Does not change PWM."""
        body = led_bytes(matrix, ring)
        if not robot.flags & LED_READY:
            raise RuntimeError("Firmware does not support LED control")
        return self._send(robot, LED_FRAME, body)

    def release(self, robot):
        for _ in range(3):
            self._send(robot, RELEASE)
        robot.session = 0

    def off(self, robot, timeout=.2):
        # OFF may be lost over UDP; verify that a matching final status has no PWM.
        seq = self._send(robot, OFF)
        message = packet(OFF, robot.session, seq)
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            self.poll(.01)
            if (robot.telemetry and robot.telemetry["accepted_seq"] == seq
                    and not any(robot.telemetry["ticks"]) and not robot.flags & FAULT):
                robot.session = 0
                return
            self.socket.sendto(message, robot.address)
        raise TimeoutError("OFF not confirmed; check the robot")

    def run(self, robots, policy, hz=100, seconds=None):
        """policy(observations) -> {mac: 16 ticks}; observations include host age.

        Missing actions are NOT resent. A stalled/failed model lets leases expire.
        Never performs automatic reclaim: reacquiring requires explicit discovery.
        """
        if not 1 <= hz <= 400:
            raise ValueError("Command rate must be 1..400 Hz; benchmark your WLAN")
        robots = list(robots)
        start = next_tick = time.perf_counter()
        while seconds is None or time.perf_counter() - start < seconds:
            self.poll()
            now = time.perf_counter()
            observations = {}
            for robot in robots:
                age = now - robot.seen_at
                progress_age = now-robot.progress_at if robot.sent_at else 0
                if max(age,progress_age) > min(robot.lease_ms,250) / 1000 or not robot.flags & OWNED or robot.flags & FAULT:
                    raise TimeoutError(f"Lost control/telemetry for {robot.mac}; last pose is held")
                observations[robot.mac] = dict(robot.telemetry, host_age_s=age)
            actions = policy(observations)
            # Model inference that exceeds the lease cannot silently renew a session.
            if time.perf_counter() - now >= min(250,*(r.lease_ms for r in robots)) / 1000:
                raise TimeoutError("Policy exceeded the command lease; reconnect explicitly")
            for robot in robots:
                if robot.mac in actions:
                    self.send_ticks(robot, actions[robot.mac])
            next_tick += 1 / hz
            delay = next_tick - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            else:
                next_tick = time.perf_counter()  # no catch-up burst


class JointMap:
    """PC-side calibration, ordering: leg0 upper/lower ... leg3 upper/lower."""
    def __init__(self, config):
        self.joints = [config["motor"][f"leg{i}"][joint]
                       for i in range(4) for joint in ("upper", "lower")]
        pins = [j["pin"] for j in self.joints]
        if len(set(pins)) != 8 or any(type(p) is not int or not 0 <= p < 16 for p in pins):
            raise ValueError("Invalid/duplicate servo channels in calibration")
        if any(j["orientation"] not in (-1, 1) or not math.isfinite(j["offset"]) for j in self.joints):
            raise ValueError("Invalid orientation/offset")

    @classmethod
    def load(cls, path):
        return cls(json.loads(Path(path).read_text()))

    def ticks(self, angles, minimum=120, maximum=600):
        if len(angles) != 8:
            raise ValueError("Expected eight joint angles in degrees")
        values = [0] * 16
        for angle, joint in zip(angles, self.joints):
            physical = float(angle) * joint["orientation"] + joint["offset"]
            if not math.isfinite(physical) or not -90 <= physical <= 90:
                raise ValueError("Calibrated angle must be within -90..90 degrees")
            values[joint["pin"]] = round(minimum + (physical + 90) * (maximum - minimum) / 180)
        return values

    def angles(self, ticks, minimum=120, maximum=600):
        # Disabled joints have no known angle; use the logical center as a start.
        return [((ticks[j["pin"]] - minimum) * 180 / (maximum - minimum) - 90 - j["offset"]) / j["orientation"]
                if ticks[j["pin"]] else 0.0 for j in self.joints]
