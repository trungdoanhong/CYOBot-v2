"""Original Crawler keyframes, with time-based interpolation entirely on the PC."""
import math

GAITS = {
    "forward": ([-20, -15, -20, 20, 30, 20, 30, -15], [1, 1, 1, 1]),
    "backward": ([20, -15, 20, 20, -30, 20, -30, -15], [1, 1, 1, 1]),
    "rotate_left": ([-30, -30, -30, 0, 30, 20, 30, 0], [-1, -1, 1, 1]),
    "rotate_right": ([-30, -30, -30, 0, 30, 20, 30, 0], [1, 1, -1, -1]),
    "lateral_left": ([-30, -30, -30, 0, 30, 20, 30, 0], [-1, 1, -1, 1]),
    "lateral_right": ([-30, -30, -30, 0, 30, 20, 30, 0], [1, -1, 1, -1]),
}


class CrawlerGait:
    def __init__(self, command, initial_angles=None, cycle_seconds=1.0):
        if not math.isfinite(cycle_seconds) or cycle_seconds <= 0:
            raise ValueError("cycle_seconds must be positive")
        gait, order = GAITS[command]
        self.phases = []
        for phase in range(4):
            values = []
            for leg in range(4):
                index = ((phase + (2 if leg % 2 else 0)) * 2) % 8
                values.extend((gait[index] * order[leg], gait[index + 1]))
            self.phases.append(values)
        self.initial = list(initial_angles or [0] * 8)
        if len(self.initial) != 8:
            raise ValueError("Eight starting angles required")
        self.phase_seconds = cycle_seconds / 4

    def angles(self, elapsed):
        position = max(0, elapsed) / self.phase_seconds
        step = int(position)
        fraction = position - step
        before = self.initial if step == 0 else self.phases[(step - 1) % 4]
        after = self.phases[step % 4]
        return [a + (b - a) * fraction for a, b in zip(before, after)]
