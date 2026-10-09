"""Button gesture and non-blocking servo sweep used by the Crawler portal."""

import time


SERVO_ANGLES_DEGREES = (0, 90, 180, 150, 120, 90, 60, 30, 0, 30, 60, 90, 120, 150, 180)


class DualButtonHold:
    """Fire once after a continuous hold; release BOTH buttons to re-arm."""

    def __init__(self, hold_ms=3000, release_ms=50):
        self.hold_ms = hold_ms
        self.release_ms = release_ms
        self._started = None
        self._released = None
        self._latched = False

    def update(self, left_pressed, right_pressed, now_ms):
        if self._latched:
            if not left_pressed and not right_pressed:
                if self._released is None:
                    self._released = now_ms
                elif time.ticks_diff(now_ms, self._released) >= self.release_ms:
                    self._latched = False
                    self._started = None
            else:
                self._released = None
            return False

        if not (left_pressed and right_pressed):
            self._started = None
            return False
        if self._started is None:
            self._started = now_ms
        elif time.ticks_diff(now_ms, self._started) >= self.hold_ms:
            self._latched = True
            self._released = None
            return True
        return False


class ServoSweep:
    """One non-blocking step, so buttons and STOP remain responsive."""

    def __init__(self, hold_ms=1000):
        self.hold_ms = hold_ms
        self.reset()

    def reset(self):
        self._index = 0
        self._last_step = None
        self.angle = None

    def step(self, pca, now_ms):
        if self._last_step is not None:
            if time.ticks_diff(now_ms, self._last_step) < self.hold_ms:
                return None
        angle = SERVO_ANGLES_DEGREES[self._index]
        for channel in range(16):
            pca.set_angle(channel, angle - 90)
        self.angle = angle
        self._last_step = now_ms
        self._index = (self._index + 1) % len(SERVO_ANGLES_DEGREES)
        return angle
