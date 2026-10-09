"""Host-side tests; no serial connection and no physical servo movement.

Run: python -m unittest discover -s software/MicroPython/tests -v
"""

import ast
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("servo_test", ROOT / "sd/lib/servo_test.py")
servo_test = importlib.util.module_from_spec(spec)
spec.loader.exec_module(servo_test)


class EndWorker(BaseException):
    pass


class Clock:
    def __init__(self):
        self.now = 0
        self.limit = None
        self.on_sleep = lambda: None

    def ticks_ms(self):
        return self.now % (1 << 30)

    @staticmethod
    def ticks_diff(a, b):
        return ((a - b + (1 << 29)) % (1 << 30)) - (1 << 29)

    def sleep_ms(self, duration):
        self.now += duration
        self.on_sleep()
        if self.limit is not None and self.now >= self.limit:
            raise EndWorker()


class Display:
    def __init__(self):
        self.color = None

    def reset(self):
        self.color = None

    def set_all(self, color):
        self.color = color

    def set_manual(self, index, color):
        self.color = color


class PCA:
    def __init__(self):
        self.events = []
        self.fail = False

    def set_angle(self, channel, angle):
        if self.fail:
            raise OSError("I2C unavailable")
        self.events.append((channel, angle))

    def all_off(self):
        self.events.append("off")
        if self.fail:
            raise OSError("I2C unavailable")


class Leg:
    def setCurrentAngle(self, lower, upper):
        self.angles = (lower, upper)


class Bot:
    def __init__(self):
        self.pca = PCA()
        self.leg0, self.leg1, self.leg2, self.leg3 = [Leg() for _ in range(4)]
        self._abort = False
        self.commands = []
        self.on_command = lambda: None

    def request_abort(self):
        self._abort = True

    def clear_abort(self):
        self._abort = False

    def _should_abort(self):
        return self._abort

    def command(self, cmd):
        self.commands.append(cmd)
        self.on_command()

    def center(self):
        self.commands.append("center")


def module(name, **values):
    result = types.ModuleType(name)
    result.__dict__.update(values)
    return result


def fake_modules():
    server = types.SimpleNamespace(route=lambda *args, **kwargs: lambda func: func)
    return {
        "lib": module("lib"),
        "lib.servo_test": servo_test,
        "lib.display": module("lib.display", LEDRing=Display, Matrix=Display),
        "lib.network": module("lib.network"),
        "lib.network.microWebSrv": module("lib.network.microWebSrv", MicroWebSrv=server),
        "lib.wireless": module("lib.wireless"),
        "machine": module("machine"),
        "webrepl": module("webrepl"),
        "network": module("network"),
    }


class ServoModeTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.time_patch = patch.object(servo_test, "time", self.clock)
        self.time_patch.start()
        self.addCleanup(self.time_patch.stop)

    def controller(self):
        # Execute the actual application definitions, stopping before server startup.
        source = (ROOT / "pyboard/main.py").read_text(encoding="utf-8")
        source = source.split("\nsrv = MicroWebSrv(")[0]
        ns = {}
        with patch.dict(sys.modules, fake_modules()):
            exec(compile(source, "main.py", "exec"), ns)
        ns["time"] = self.clock
        ns["_motion_thread_started"] = True
        ns["_crawler"] = Bot()
        return ns

    def run_worker(self, ns, duration):
        self.clock.limit = self.clock.now + duration
        with self.assertRaises(EndWorker):
            ns["_motion_worker"]()

    def test_hold_requires_three_continuous_seconds(self):
        hold = servo_test.DualButtonHold()
        self.assertFalse(hold.update(True, False, 0))
        self.assertFalse(hold.update(True, True, 1000))
        self.assertFalse(hold.update(True, True, 3999))
        self.assertTrue(hold.update(True, True, 4000))
        self.assertFalse(hold.update(True, True, 14000))

    def test_short_press_restarts_timer(self):
        hold = servo_test.DualButtonHold()
        hold.update(True, True, 0)
        hold.update(False, True, 2999)
        self.assertFalse(hold.update(True, True, 3000))
        self.assertFalse(hold.update(True, True, 5999))
        self.assertTrue(hold.update(True, True, 6000))

    def test_rearm_needs_both_buttons_released_and_debounced(self):
        hold = servo_test.DualButtonHold()
        hold.update(True, True, 0)
        self.assertTrue(hold.update(True, True, 3000))
        hold.update(False, True, 4000)
        self.assertFalse(hold.update(True, True, 8000))
        hold.update(False, False, 9000)
        hold.update(True, True, 9040)  # release bounce must not re-arm
        self.assertFalse(hold.update(True, True, 13000))
        hold.update(False, False, 14000)
        hold.update(False, False, 14050)
        hold.update(True, True, 15000)
        self.assertTrue(hold.update(True, True, 18000))

    def test_hold_and_sweep_survive_tick_wraparound(self):
        period = 1 << 30
        hold = servo_test.DualButtonHold()
        hold.update(True, True, period - 1000)
        self.assertFalse(hold.update(True, True, 1999))
        self.assertTrue(hold.update(True, True, 2000))
        sweep, pca = servo_test.ServoSweep(), PCA()
        self.assertEqual(sweep.step(pca, period - 500), 0)
        self.assertIsNone(sweep.step(pca, 499))
        self.assertEqual(sweep.step(pca, 500), 90)

    def test_sweep_all_channels_timing_and_repeat(self):
        sweep, pca = servo_test.ServoSweep(), PCA()
        for index, angle in enumerate(servo_test.SERVO_ANGLES_DEGREES + (0,)):
            self.assertEqual(sweep.step(pca, index * 1000), angle)
            self.assertEqual(pca.events[-16:], [(ch, angle - 90) for ch in range(16)])
            count = len(pca.events)
            self.assertIsNone(sweep.step(pca, index * 1000 + 999))
            self.assertEqual(len(pca.events), count)

    def test_boot_stays_idle_until_explicit_mode_or_motion(self):
        ns = self.controller()
        self.run_worker(ns, 200)
        self.assertFalse(ns["_servo_test_active"])
        self.assertEqual(ns["_crawler"].pca.events, [])
        self.assertEqual(ns["_crawler"].commands, [])

    def test_button_worker_toggles_without_browser(self):
        ns = self.controller()
        events = []
        ns["_toggle_servo_test"] = lambda: events.append(self.clock.now)
        class Pin:
            IN = 0
            def __init__(inner, pin, mode):
                pass
            def value(inner):
                return int(6500 <= self.clock.now < 6600)
        ns["machine"] = types.SimpleNamespace(Pin=Pin)
        self.clock.limit = 10000
        with self.assertRaises(EndWorker):
            ns["_button_worker"]()
        self.assertEqual(events, [3000, 9600])

    def test_mode_roundtrip_blocks_motion_and_returns_idle(self):
        ns = self.controller()
        ns["_enqueue_motion"]("forward")
        ns["_toggle_servo_test"]()
        self.assertEqual(ns["_motion_queue"], [])
        self.assertFalse(ns["_enqueue_motion"]("backward"))
        self.assertFalse(ns["_queue_center"]())
        self.run_worker(ns, 1100)
        bot = ns["_crawler"]
        self.assertEqual(bot.commands, [])
        self.assertTrue(ns["_servo_test_active"])
        self.assertEqual(ns["_servo_sweep"].angle, 90)
        self.assertEqual(bot.leg0.angles, (0, 0))
        ns["_toggle_servo_test"]()
        self.run_worker(ns, 100)
        self.assertFalse(ns["_servo_test_active"])
        self.assertEqual(bot.pca.events[-1], "off")
        before = list(bot.pca.events)
        self.run_worker(ns, 100)
        self.assertEqual(bot.pca.events, before)
        self.assertTrue(ns["_enqueue_motion"]("backward"))
        self.run_worker(ns, 100)
        self.assertEqual(bot.commands, ["backward"])

    def test_toggle_during_crawler_motion_aborts_remaining_steps(self):
        ns = self.controller()
        bot = ns["_crawler"]
        bot.on_command = ns["_toggle_servo_test"]
        ns["_enqueue_motion"]("forward", steps=20)
        ns["_enqueue_motion"]("backward")
        self.run_worker(ns, 100)
        self.assertEqual(bot.commands, ["forward"])
        self.assertTrue(ns["_servo_test_active"])
        self.assertEqual(ns["_motion_queue"], [])
        first_angle = next(i for i, event in enumerate(bot.pca.events) if event != "off")
        self.assertIn("off", bot.pca.events[:first_angle])

    def test_stop_ends_test_and_does_not_resume_sweep(self):
        ns = self.controller()
        ns["_toggle_servo_test"]()
        self.run_worker(ns, 100)
        ns["_request_stop"]()
        self.run_worker(ns, 2000)
        self.assertFalse(ns["_servo_test_active"])
        self.assertFalse(ns["_servo_test_requested"])
        self.assertEqual(len([e for e in ns["_crawler"].pca.events if e != "off"]), 16)

    def test_api_rejects_crawler_commands_during_test(self):
        ns = self.controller()
        ns["_toggle_servo_test"]()
        responses = []
        response = types.SimpleNamespace(
            WriteResponseJSONError=lambda status, **kwargs: responses.append(status),
            WriteResponseJSONOk=lambda **kwargs: responses.append(200),
        )
        client = types.SimpleNamespace(ReadRequestContentAsJSON=lambda: {"cmd": "forward"})
        ns["_httpHandlerCrawlerCmd"](client, response)
        ns["_httpHandlerCrawlerCenter"](client, response)
        self.assertEqual(responses, [409, 409])
        self.assertEqual(ns["_motion_queue"], [])
        ns["_httpHandlerCrawlerAllOff"](client, response)
        self.assertFalse(ns["_servo_test_requested"])
        self.assertEqual(responses[-1], 200)

    def test_i2c_failure_leaves_test_and_does_not_retry_forever(self):
        ns = self.controller()
        ns["_toggle_servo_test"]()
        self.run_worker(ns, 100)
        ns["_crawler"].pca.fail = True
        self.run_worker(ns, 2000)
        self.assertFalse(ns["_servo_test_active"])
        self.assertFalse(ns["_servo_test_requested"])
        self.assertIn("I2C unavailable", ns["_crawler_error"])
        self.assertLess(len(ns["_crawler"].pca.events), 20)

    def test_recovery_only_accepts_left_button_alone(self):
        tree = ast.parse((ROOT / "pyboard/boot.py").read_text(encoding="utf-8"))
        helper = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_recovery_requested")
        ns = {"time": self.clock}
        ns["left"] = types.SimpleNamespace(value=lambda: 0)
        ns["right"] = types.SimpleNamespace(value=lambda: 0)
        exec(compile(ast.Module(body=[helper], type_ignores=[]), "boot.py", "exec"), ns)
        with patch.dict(sys.modules, fake_modules()):
            self.assertFalse(ns["_recovery_requested"]())
            ns["right"].value = lambda: int(self.clock.now < 1000)
            self.assertFalse(ns["_recovery_requested"]())
            self.assertEqual(self.clock.now, 1000)
            ns["right"].value = lambda: 1
            self.assertTrue(ns["_recovery_requested"]())
            self.assertEqual(self.clock.now, 4000)

    def test_portal_recovery_copy_matches_main(self):
        self.assertEqual((ROOT / "pyboard/main.py").read_bytes(), (ROOT / "pyboard/main-server.py").read_bytes())


if __name__ == "__main__":
    unittest.main()
