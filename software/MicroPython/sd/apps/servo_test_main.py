"""
CYOBot v2 - Servo Test (Web UI)

This script is intended to be deployed to the board as `main.py` (via /sdcard/main.py).
It starts an AP and serves a simple web UI to directly control PCA9685 servo channels.

Web UI:
  - http://192.168.4.1/   (or http://portal.cyobot.com/ if DNS is running)

API:
  - GET  /api/status
  - POST /api/servo    {"channel":0-15, "angle":-90..90} OR {"channel":0-15, "off":true}
  - POST /api/center
  - POST /api/all_off
"""

import gc
import json
import network
import time

from lib.network.microWebSrv import MicroWebSrv


AP_SSID = "CYOBot"
NUM_CHANNELS = 16


def _cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "*",
        "Access-Control-Allow-Headers": "*",
    }


def _write_json(httpResponse, code, obj):
    httpResponse.WriteResponse(
        code=code,
        headers=_cors_headers(),
        contentType="application/json",
        contentCharset="UTF-8",
        content=json.dumps(obj),
    )


def _json_ok(httpResponse, obj):
    _write_json(httpResponse, 200, obj)


def _json_err(httpResponse, code, message):
    _write_json(httpResponse, code, {"error": message})


def _clamp_angle(angle):
    if angle < -90:
        return -90
    if angle > 90:
        return 90
    return angle


def _load_labels():
    # Best-effort: map channels to leg/joint names using /sdcard/config/robot-config.json
    try:
        with open("/sdcard/config/robot-config.json") as f:
            motor = json.load(f).get("motor", {})
        labels = {}
        for leg_name, leg_cfg in motor.items():
            for joint in ("upper", "lower"):
                try:
                    ch = int(leg_cfg[joint]["pin"])
                except Exception:
                    continue
                labels[str(ch)] = "{}.{}".format(leg_name, joint)
        return labels
    except Exception:
        return {}


def _init_ap():
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    while not ap.active():
        time.sleep(0.01)
    ap.config(
        essid=AP_SSID,
        pm=network.WLAN.PM_PERFORMANCE,
        txpower=20,
        channel=6,
    )
    return ap


def _start_dns():
    # Optional convenience: resolve portal.cyobot.com -> 192.168.4.1 in AP mode.
    try:
        from lib.network.microDNSSrv import MicroDNSSrv

        MicroDNSSrv.Create({"portal.cyobot.com": "192.168.4.1"})
        print("MicroDNSSrv started.")
    except Exception as e:
        print("MicroDNSSrv start error:", e)


# --- Servo driver init ---

PCA_INIT_ERROR = None
try:
    from lib.pca9685 import PCA9685

    pca = PCA9685(SDA=17, SCL=18)
except Exception as e:
    pca = None
    PCA_INIT_ERROR = str(e)

angles = [0 for _ in range(NUM_CHANNELS)]
is_off = [False for _ in range(NUM_CHANNELS)]


# --- API routes ---

@MicroWebSrv.route("/api/status")
def _api_status(httpClient, httpResponse):
    ip = None
    try:
        ip = network.WLAN(network.AP_IF).ifconfig()[0]
    except Exception:
        pass

    _json_ok(
        httpResponse,
        {
            "ok": pca is not None,
            "error": PCA_INIT_ERROR,
            "ip": ip,
            "channels": NUM_CHANNELS,
            "angles": angles,
            "off": is_off,
            "labels": _load_labels(),
        },
    )


@MicroWebSrv.route("/api/servo", method="OPTIONS")
def _api_servo_options(httpClient, httpResponse):
    httpResponse.WriteResponseOk(headers=_cors_headers())


@MicroWebSrv.route("/api/servo", "POST")
def _api_servo(httpClient, httpResponse):
    if pca is None:
        _json_err(httpResponse, 500, "PCA9685 init failed: {}".format(PCA_INIT_ERROR))
        return

    data = httpClient.ReadRequestContentAsJSON()
    if not isinstance(data, dict):
        _json_err(httpResponse, 400, "Invalid JSON body")
        return

    try:
        ch = int(data.get("channel"))
    except Exception:
        _json_err(httpResponse, 400, "Missing/invalid channel")
        return

    if ch < 0 or ch >= NUM_CHANNELS:
        _json_err(httpResponse, 400, "Channel out of range")
        return

    if data.get("off") is True:
        try:
            pca.off(ch)
            is_off[ch] = True
            _json_ok(httpResponse, {"channel": ch, "off": True})
        except Exception as e:
            _json_err(httpResponse, 500, str(e))
        return

    try:
        angle = float(data.get("angle"))
    except Exception:
        _json_err(httpResponse, 400, "Missing/invalid angle")
        return

    angle = _clamp_angle(angle)
    try:
        pca.set_angle(ch, angle)
        angles[ch] = angle
        is_off[ch] = False
        _json_ok(httpResponse, {"channel": ch, "angle": angle})
    except Exception as e:
        _json_err(httpResponse, 500, str(e))


@MicroWebSrv.route("/api/center", method="OPTIONS")
def _api_center_options(httpClient, httpResponse):
    httpResponse.WriteResponseOk(headers=_cors_headers())


@MicroWebSrv.route("/api/center", "POST")
def _api_center(httpClient, httpResponse):
    if pca is None:
        _json_err(httpResponse, 500, "PCA9685 init failed: {}".format(PCA_INIT_ERROR))
        return

    try:
        for i in range(NUM_CHANNELS):
            pca.set_angle(i, 0)
            angles[i] = 0
            is_off[i] = False
        _json_ok(httpResponse, {"ok": True})
    except Exception as e:
        _json_err(httpResponse, 500, str(e))


@MicroWebSrv.route("/api/all_off", method="OPTIONS")
def _api_all_off_options(httpClient, httpResponse):
    httpResponse.WriteResponseOk(headers=_cors_headers())


@MicroWebSrv.route("/api/all_off", "POST")
def _api_all_off(httpClient, httpResponse):
    if pca is None:
        _json_err(httpResponse, 500, "PCA9685 init failed: {}".format(PCA_INIT_ERROR))
        return

    try:
        pca.all_off()
        for i in range(NUM_CHANNELS):
            is_off[i] = True
        _json_ok(httpResponse, {"ok": True})
    except Exception as e:
        _json_err(httpResponse, 500, str(e))


# --- Start network + server ---

ap = _init_ap()
_start_dns()

try:
    print("Servo Test AP:", ap.ifconfig())
except Exception:
    pass

srv = MicroWebSrv(webPath="/sdcard/servo-test")
srv.Start(threaded=True)

while True:
    gc.collect()
    time.sleep(2)

