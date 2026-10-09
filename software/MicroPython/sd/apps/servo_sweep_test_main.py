"""
CYOBot v2 - automatic RC servo health test.

Deploy this file as ``/sdcard/main.py``. On every boot, all 16 PCA9685
channels move through SERVO_ANGLES_DEGREES and repeat until power-off or a
KeyboardInterrupt. Angles in this file use the conventional RC-servo 0..180
degree range; the CYOBot PCA9685 driver uses -90..90 internally.
"""

import time

from lib.pca9685 import PCA9685


PCA_SDA_PIN = 17
PCA_SCL_PIN = 18
SERVO_CHANNELS = tuple(range(16))
SERVO_ANGLES_DEGREES = (
    0,
    90,
    180,
    150,
    120,
    90,
    60,
    30,
    0,
    30,
    60,
    90,
    120,
    150,
    180,
)
ANGLE_HOLD_MS = 1000


def _to_driver_angle(angle_degrees):
    """Convert a conventional 0..180 degree angle to driver -90..90."""
    return angle_degrees - 90


def _set_all_servos(pca, angle_degrees):
    driver_angle = _to_driver_angle(angle_degrees)
    for channel in SERVO_CHANNELS:
        pca.set_angle(channel, driver_angle)


def run_servo_health_test():
    pca = PCA9685(SDA=PCA_SDA_PIN, SCL=PCA_SCL_PIN)
    print("RC servo health test started on PCA9685 channels 0-15")

    try:
        while True:
            for angle in SERVO_ANGLES_DEGREES:
                print("Servo angle: {} degrees".format(angle))
                _set_all_servos(pca, angle)
                time.sleep_ms(ANGLE_HOLD_MS)
    finally:
        # Stop sending pulses when the test is interrupted or fails.
        pca.all_off()


run_servo_health_test()
