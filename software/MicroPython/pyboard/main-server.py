from lib.display import *
from lib.network.microWebSrv import MicroWebSrv
from lib.wireless import *
import machine
import json
import webrepl
import network
import time
import json
import gc
import _thread

ring = LEDRing()
matrix = Matrix()
ring.reset()
matrix.reset()
wifi = None
ap = None
last_wifi_ap_list = None
last_wifi_ap_scan_time = None
mPlayer = None

# -----------------------------------------------------------------------------
# Crawler (4-leg) direct control panel (no programming required)
# -----------------------------------------------------------------------------

_crawler = None
_crawler_error = None

_motion_lock = _thread.allocate_lock()
_motion_queue = []  # (cmd:str, steps:int, hold:bool)
_motion_busy = False
_motion_last = None
_motion_stop = False
_motion_thread_started = False

_CRAWLER_ALLOWED_CMDS = (
    "forward",
    "backward",
    "rotate_left",
    "rotate_right",
    "lateral_left",
    "lateral_right",
)


def _cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "*",
        "Access-Control-Allow-Headers": "*",
    }


def _get_ip_address():
    # Prefer STA IP when connected, else fall back to AP IP.
    try:
        if wifi is not None and wifi.wlan.isconnected():
            return wifi.wlan.ifconfig()[0]
    except:
        pass
    try:
        if ap is not None:
            return ap.ifconfig()[0]
    except:
        pass
    return "192.168.4.1"


def _get_crawler():
    global _crawler, _crawler_error
    if _crawler is not None:
        return _crawler
    try:
        from lib.kinematics import Crawler

        _crawler = Crawler()
        _crawler_error = None
        return _crawler
    except Exception as e:
        _crawler = None
        _crawler_error = str(e)
        return None


def _bot_request_abort(bot):
    try:
        bot.request_abort()
        return
    except:
        pass
    try:
        bot._abort = True
    except:
        pass


def _bot_clear_abort(bot):
    try:
        bot.clear_abort()
        return
    except:
        pass
    try:
        bot._abort = False
    except:
        pass


def _bot_should_abort(bot):
    try:
        return bot._should_abort()
    except:
        pass
    try:
        return bot._abort is True
    except:
        return False


def _crawler_debug_snapshot():
    bot = _get_crawler()
    if bot is None:
        return {
            "ok": False,
            "error": _crawler_error,
        }

    legs = [bot.leg0, bot.leg1, bot.leg2, bot.leg3]

    pins = {}
    orientation = {}
    offsets = {}
    angles = {}

    joints = []  # (joint_name, channel)

    for i, leg in enumerate(legs):
        leg_name = "leg{}".format(i)
        pins[leg_name] = {
            "upper": leg.upperServo,
            "lower": leg.lowerServo,
        }
        orientation[leg_name] = {
            "upper": leg.upperOrientationWRTHead,
            "lower": leg.lowerOrientationWRTHead,
        }
        offsets[leg_name] = {
            "upper": leg.centerOffsetUpper,
            "lower": leg.centerOffsetLower,
        }
        angles[leg_name] = {
            "upper": leg.currentAngleUpper,
            "lower": leg.currentAngleLower,
        }

        joints.append(("{}.upper".format(leg_name), leg.upperServo))
        joints.append(("{}.lower".format(leg_name), leg.lowerServo))

    warnings = []
    seen = {}

    for joint_name, ch in joints:
        try:
            ch_i = int(ch)
        except Exception:
            warnings.append({"type": "pin_invalid", "joint": joint_name, "value": ch})
            continue

        if ch_i < 0 or ch_i > 15:
            warnings.append({"type": "pin_out_of_range", "joint": joint_name, "channel": ch_i})

        if ch_i in seen:
            warnings.append(
                {"type": "pin_duplicate", "channel": ch_i, "joints": [seen[ch_i], joint_name]}
            )
        else:
            seen[ch_i] = joint_name

    for leg_name in ("leg0", "leg1", "leg2", "leg3"):
        for joint in ("upper", "lower"):
            ori = orientation[leg_name][joint]
            if ori not in (-1, 1):
                warnings.append(
                    {"type": "orientation_unusual", "joint": "{}.{}".format(leg_name, joint), "value": ori}
                )
            off = offsets[leg_name][joint]
            try:
                if abs(float(off)) > 90:
                    warnings.append(
                        {"type": "offset_large", "joint": "{}.{}".format(leg_name, joint), "value": off}
                    )
            except Exception:
                warnings.append(
                    {"type": "offset_invalid", "joint": "{}.{}".format(leg_name, joint), "value": off}
                )

    # Best-effort PCA parameters.
    pca = None
    try:
        pca = {"minPulse": bot.pca._min, "maxPulse": bot.pca._max}
    except Exception:
        pca = None

    return {
        "ok": True,
        "pins": pins,
        "orientation": orientation,
        "offsets": offsets,
        "angles": angles,
        "pca": pca,
        "warnings": warnings,
    }


def _ensure_motion_thread():
    global _motion_thread_started
    if _motion_thread_started:
        return
    try:
        _thread.start_new_thread(_motion_worker, ())
        _motion_thread_started = True
    except Exception as e:
        print("Motion thread start error:", e)
        _motion_thread_started = False


def _request_stop():
    global _motion_stop
    _ensure_motion_thread()
    _motion_lock.acquire()
    try:
        _motion_stop = True
        _motion_queue[:] = []
    finally:
        _motion_lock.release()
    bot = _get_crawler()
    if bot is not None:
        try:
            _bot_request_abort(bot)
        except:
            pass


def _enqueue_motion(cmd, steps=1, hold=False):
    _ensure_motion_thread()
    try:
        steps = int(steps)
    except:
        steps = 1
    if steps < 1:
        steps = 1
    if steps > 20:
        steps = 20

    _motion_lock.acquire()
    try:
        if len(_motion_queue) >= 24:
            return False
        _motion_queue.append((cmd, steps, hold is True))
        return True
    finally:
        _motion_lock.release()


def _motion_worker():
    global _motion_busy, _motion_last, _motion_stop, _crawler_error
    while True:
        # Emergency stop gets priority.
        if _motion_stop:
            bot = _get_crawler()
            if bot is not None:
                try:
                    _bot_request_abort(bot)
                    bot.pca.all_off()
                    _bot_clear_abort(bot)
                except Exception as e:
                    _crawler_error = str(e)
            _motion_lock.acquire()
            try:
                _motion_stop = False
            finally:
                _motion_lock.release()
            time.sleep_ms(20)
            continue

        cmd = None
        steps = 1
        hold = False
        _motion_lock.acquire()
        try:
            if _motion_queue:
                cmd, steps, hold = _motion_queue.pop(0)
                _motion_busy = True
                _motion_last = {
                    "cmd": cmd,
                    "steps": steps,
                    "hold": hold,
                    "t": time.ticks_ms(),
                }
            else:
                _motion_busy = False
        finally:
            _motion_lock.release()

        if cmd is None:
            time.sleep_ms(30)
            continue

        bot = _get_crawler()
        if bot is None:
            time.sleep_ms(200)
            continue

        try:
            _bot_clear_abort(bot)

            if cmd == "center":
                bot.center()
                # center() ends with all_off() in current library.
            elif cmd == "all_off":
                bot.pca.all_off()
            elif cmd == "stop":
                _bot_request_abort(bot)
                bot.stop()
                _bot_clear_abort(bot)
            elif cmd in _CRAWLER_ALLOWED_CMDS:
                for i in range(steps):
                    if _bot_should_abort(bot):
                        break
                    bot.command(cmd)
                if not hold:
                    bot.pca.all_off()
            else:
                # Unknown command, ignore.
                pass
        except Exception as e:
            _crawler_error = str(e)
            try:
                bot.pca.all_off()
            except:
                pass

        try:
            gc.collect()
        except:
            pass

def startup():
    global mPlayer

    from audio import player
    mPlayer = player(None)
    mPlayer.set_vol(100)

    try:
        with open("/sdcard/config/robot-config.json") as file:
            content = json.loads(file.read())
        startup_sound = content["startup"]["sound"]
        startup_text = content["startup"]["text"]
        if startup_sound != "":
            mPlayer.play(startup_sound)
        else:
            mPlayer.play('file://sdcard/lib/data/robot-on.wav')
        if startup_text != "":    
            matrix.scroll(startup_text, red=150, green=10, blue=40, speed=0.05)
    except Exception as e:
        print("Startup error:", e)

    for i in range(12):
        ring.set_manual(i, (0, 100, 0))
        time.sleep(0.05)
    ring.reset()

    while mPlayer.get_state()['status'] == player.STATUS_RUNNING:
        time.sleep(1)

def test_connect_wifi():
    global wifi
    global mPlayer

    wifi = WiFi()

    try:
        with open("/sdcard/config/robot-config.json") as file:
            content = json.loads(file.read())
        if content["wifi"]["ssid"] != "":
            if mPlayer is None:
                from audio import player
                mPlayer = player(None)
                mPlayer.set_vol(100)
            mPlayer.play('file://sdcard/lib/data/wifi-connecting.wav')
            print("Connecting to WiFi:", content["wifi"]["ssid"], content["wifi"]["password"])
            wifi.connect(content["wifi"]["ssid"], content["wifi"]["password"], verbose=True)
    except Exception as e:
        print("WiFi check and connect error:", e)
        pass

    if wifi.wlan.isconnected():
        if mPlayer is None:
            from audio import player
            mPlayer = player(None)
            mPlayer.set_vol(100)
        mPlayer.play('file://sdcard/lib/data/wifi-connected.wav')
        time.sleep(2)

def check_and_connect_wifi():
    global wifi

    wifi = WiFi()

    try:
        with open("/sdcard/config/robot-config.json") as file:
            content = json.loads(file.read())
        if content["wifi"]["ssid"] != "":
            print("Connecting to WiFi:", content["wifi"]["ssid"], content["wifi"]["password"])
            wifi.connect(content["wifi"]["ssid"], content["wifi"]["password"], verbose=True)
    except Exception as e:
        print("WiFi check and connect error:", e)
        pass

    if wifi.wlan.isconnected():
        with open("/sdcard/config/portal-config.json") as file:
            content = json.loads(file.read())
        content["pythonWebREPL"]["endpoint"] = "ws://{}:8266".format(wifi.wlan.ifconfig()[0])
        content["onboarding"]["hasProvidedWifiCredentials"] = True
        
        with open("/sdcard/config/portal-config.json", "w") as outfile:
            outfile.write(json.dumps(content))
    else:
        with open("/sdcard/config/portal-config.json") as file:
            content = json.loads(file.read())
        content["pythonWebREPL"]["endpoint"] = "ws://192.168.4.1:8266"
        content["onboarding"]["hasProvidedWifiCredentials"] = False
        
        with open("/sdcard/config/portal-config.json", "w") as outfile:
            outfile.write(json.dumps(content))

def init_ap():
    global ap

    ssid = 'CYOBot'
    ap = network.WLAN(network.AP_IF)
    ap.active(True)

    while ap.active() == False:
        time.sleep(0.01)

    ap.config(essid=ssid, pm=network.WLAN.PM_PERFORMANCE, txpower=20, channel=6)

    print('Access point created successfully')
    print(ap.config('essid'), ap.ifconfig())

def start_dns():
    global wifi

    if not wifi.wlan.isconnected():
        from lib.network.microDNSSrv import MicroDNSSrv
        if MicroDNSSrv.Create({"portal.cyobot.com": "192.168.4.1"}):
            print("MicroDNSSrv started.")
        else :
            print("Error to starts MicroDNSSrv...")

def getWiFiAPList():
    global wifi
    global ap

    def signal_strength(x):
        if x < -80:
            return 0
        elif x < -60:
            return 1
        elif x < -40:
            return 2
        else:
            return 3
    
    try:
        ap_list = wifi.wlan.scan()
    except:
        try:
            ap_list = ap.scan()
        except:
            pass
    content = [{"ssid": x[0].decode('ascii'), "strength": signal_strength(x[3])} for x in ap_list]
    return content

@MicroWebSrv.route('/api/config')
def _httpHandlerGetConfig(httpClient, httpResponse):
    httpResponse.WriteResponseFile("/sdcard/config/portal-config.json", contentType="application/json", headers={
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': '*',
        'Access-Control-Allow-Headers': '*'
    })

@MicroWebSrv.route('/api/internet')
def _httpHandlerGetWiFiConnectivity(httpClient, httpResponse):
    if wifi.wlan.isconnected():
        httpResponse.WriteResponseJSONOk(obj=json.loads('{"status": "connected"}'), headers={
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': '*',
            'Access-Control-Allow-Headers': '*'
        })
    else:
        httpResponse.WriteResponseJSONOk(obj=json.loads('{"status": "disconnected"}'), headers={
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': '*',
            'Access-Control-Allow-Headers': '*'
        })

@MicroWebSrv.route('/api/wifi')
def _httpHandlerGetWiFi(httpClient, httpResponse):
    global last_wifi_ap_list
    global last_wifi_ap_scan_time
    if time.time() - last_wifi_ap_scan_time > 10:
        last_wifi_ap_list = getWiFiAPList()
        last_wifi_ap_scan_time = time.time()
    httpResponse.WriteResponseJSONOk(obj=last_wifi_ap_list, headers={
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': '*',
        'Access-Control-Allow-Headers': '*'
    })

@MicroWebSrv.route('/api/wifi', method='OPTIONS')
def _httpHandlerOptionWiFiCredential(httpClient, httpResponse):
    httpResponse.WriteResponseOk(headers={
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': '*',
        'Access-Control-Allow-Headers': '*'
    })

@MicroWebSrv.route('/api/wifi', 'POST')
def _httpHandlerPostWiFiCredential(httpClient, httpResponse):
    # receive credentials from portal
    # attempt to connect
    # if successful, update config.json (pythonwebrepl --> ws://<NEW IP>:8266) AND onboarding.hasProvidedWifiCredentials --> True
    # if not, do not need to update
    # return "success" or "fail" to client
    data = httpClient.ReadRequestContentAsJSON()
    global mPlayer

    # try 4 times (5 seconds/time)
    if mPlayer is None:
        from audio import player
        mPlayer = player(None)
        mPlayer.set_vol(100)
    mPlayer.play('file://sdcard/lib/data/wifi-connecting.wav')
    for i in range(4):
        wifi.connect(data["ssid"], data["password"], verbose=True)
        if wifi.wlan.isconnected():
            mPlayer.play('file://sdcard/lib/data/wifi-connected.wav')
            time.sleep(2)
            break

    #! TODO: also store this credential in INTERNAL config so that we can connect in the future auto
    if wifi.wlan.isconnected():
        with open("/sdcard/config/portal-config.json") as file:
            content = json.loads(file.read())
        content["pythonWebREPL"]["endpoint"] = "ws://{}:8266".format(wifi.wlan.ifconfig()[0])
        content["onboarding"]["hasProvidedWifiCredentials"] = True
        
        with open("/sdcard/config/portal-config.json", "w") as outfile:
            outfile.write(json.dumps(content))

        with open("/sdcard/config/robot-config.json") as file:
            content = json.loads(file.read())
        content["wifi"]["ssid"] = data["ssid"]
        content["wifi"]["password"] = data["password"]

        with open("/sdcard/config/robot-config.json", "w") as outfile:
            outfile.write(json.dumps(content))

        httpResponse.WriteResponseJSONOk(obj=json.dumps("success"), headers={
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': '*',
            'Access-Control-Allow-Headers': '*'
        })
        
        time.sleep(2)
        with open("state", "w") as file:
            file.write("2")
        import machine
        machine.reset()

    else:
        httpResponse.WriteResponseJSONOk(obj=json.dumps("fail"), headers={
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': '*',
            'Access-Control-Allow-Headers': '*'
        })

@MicroWebSrv.route('/api/config', 'POST')
def _httpHandlerPostConfig(httpClient, httpResponse):
    data = httpClient.ReadRequestContentAsJSON()
    print(data)
    
    try:
        with open("/sdcard/config/portal-config.json") as file:
            content = json.loads(file.read())
        content["pythonWebREPL"]["endpoint"] = data["wsEndpoint"]
        
        with open("/sdcard/config/portal-config.json", "w") as outfile:
            outfile.write(json.dumps(content))
        
        httpResponse.WriteResponseOk(headers={
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': '*',
            'Access-Control-Allow-Headers': '*'
        })
    except Exception as e:
        print(e)
        httpResponse.WriteReponseError(500, headers={
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': '*',
            'Access-Control-Allow-Headers': '*'
        })

@MicroWebSrv.route('/api/deploy', 'POST')
def _httpHandlerPostConfig(httpClient, httpResponse):
    data = httpClient.ReadRequestContentAsJSON()
    with open("/sdcard/main.py", "w") as outfile:
        outfile.write(data["code"])
    import machine
    machine.reset()
    try:
        httpResponse.WriteResponseOk(headers={
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': '*',
            'Access-Control-Allow-Headers': '*'
        })
    except Exception as e:
        print(e)
        httpResponse.WriteReponseError(500, headers={
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': '*',
            'Access-Control-Allow-Headers': '*'
        })

# --- Crawler control APIs ---

@MicroWebSrv.route('/crawler-control')
def _httpHandlerCrawlerControlPage(httpClient, httpResponse):
    # Serve the control panel page (MicroWebSrv does not auto-serve index.html in subfolders).
    httpResponse.WriteResponseFile(
        "/sdcard/portal/crawler-control/index.html",
        contentType="text/html",
        headers=_cors_headers(),
    )


@MicroWebSrv.route('/api/crawler/status')
def _httpHandlerCrawlerStatus(httpClient, httpResponse):
    _ensure_motion_thread()
    _motion_lock.acquire()
    try:
        qlen = len(_motion_queue)
        busy = _motion_busy
        last = _motion_last
        stop = _motion_stop
    finally:
        _motion_lock.release()

    crawler = _crawler_debug_snapshot()

    httpResponse.WriteResponseJSONOk(obj={
        "ok": True,
        "ip": _get_ip_address(),
        "queueLen": qlen,
        "busy": busy,
        "stopRequested": stop,
        "last": last,
        "error": _crawler_error,
        "crawler": crawler,
    }, headers=_cors_headers())


@MicroWebSrv.route('/api/crawler/cmd', method='OPTIONS')
def _httpHandlerCrawlerCmdOptions(httpClient, httpResponse):
    httpResponse.WriteResponseOk(headers=_cors_headers())


@MicroWebSrv.route('/api/crawler/cmd', 'POST')
def _httpHandlerCrawlerCmd(httpClient, httpResponse):
    data = httpClient.ReadRequestContentAsJSON()
    if not isinstance(data, dict):
        httpResponse.WriteResponseJSONError(400, obj={"error": "Invalid JSON body"})
        return

    cmd = data.get("cmd", "")
    steps = data.get("steps", 1)
    hold = data.get("hold", False)

    if cmd == "stop":
        _request_stop()
        httpResponse.WriteResponseJSONOk(obj={"ok": True}, headers=_cors_headers())
        return

    if cmd not in _CRAWLER_ALLOWED_CMDS:
        httpResponse.WriteResponseJSONError(400, obj={"error": "Invalid cmd"},)
        return

    ok = _enqueue_motion(cmd, steps=steps, hold=hold is True)
    if not ok:
        httpResponse.WriteResponseJSONError(429, obj={"error": "Queue full"})
        return

    httpResponse.WriteResponseJSONOk(obj={"ok": True}, headers=_cors_headers())


@MicroWebSrv.route('/api/crawler/stop', method='OPTIONS')
def _httpHandlerCrawlerStopOptions(httpClient, httpResponse):
    httpResponse.WriteResponseOk(headers=_cors_headers())


@MicroWebSrv.route('/api/crawler/stop', 'POST')
def _httpHandlerCrawlerStop(httpClient, httpResponse):
    _request_stop()
    httpResponse.WriteResponseJSONOk(obj={"ok": True}, headers=_cors_headers())


@MicroWebSrv.route('/api/crawler/center', method='OPTIONS')
def _httpHandlerCrawlerCenterOptions(httpClient, httpResponse):
    httpResponse.WriteResponseOk(headers=_cors_headers())


@MicroWebSrv.route('/api/crawler/center', 'POST')
def _httpHandlerCrawlerCenter(httpClient, httpResponse):
    global _motion_stop
    # Abort current motion and clear queue, then center.
    bot = _get_crawler()
    if bot is not None:
        try:
            _bot_request_abort(bot)
        except:
            pass

    _motion_lock.acquire()
    try:
        _motion_queue[:] = []
        _motion_stop = False
    finally:
        _motion_lock.release()

    ok = _enqueue_motion("center", steps=1, hold=True)
    if not ok:
        httpResponse.WriteResponseJSONError(429, obj={"error": "Queue full"})
        return
    httpResponse.WriteResponseJSONOk(obj={"ok": True}, headers=_cors_headers())


@MicroWebSrv.route('/api/crawler/all_off', method='OPTIONS')
def _httpHandlerCrawlerAllOffOptions(httpClient, httpResponse):
    httpResponse.WriteResponseOk(headers=_cors_headers())


@MicroWebSrv.route('/api/crawler/all_off', 'POST')
def _httpHandlerCrawlerAllOff(httpClient, httpResponse):
    global _motion_stop
    # Abort current motion and clear queue, then all_off.
    bot = _get_crawler()
    if bot is not None:
        try:
            _bot_request_abort(bot)
        except:
            pass

    _motion_lock.acquire()
    try:
        _motion_queue[:] = []
        _motion_stop = False
    finally:
        _motion_lock.release()

    ok = _enqueue_motion("all_off", steps=1, hold=True)
    if not ok:
        httpResponse.WriteResponseJSONError(429, obj={"error": "Queue full"})
        return
    httpResponse.WriteResponseJSONOk(obj={"ok": True}, headers=_cors_headers())


srv = MicroWebSrv(webPath='/sdcard/portal/')
srv.Start(threaded=True)

def wait_for_websocket():
    global wifi
    global matrix
    global ring

    if wifi.wlan.isconnected():
        # display IP address on screen
        left = machine.Pin(4, machine.Pin.IN)
        right = machine.Pin(38, machine.Pin.IN)
        ip_address = wifi.wlan.ifconfig()[0]
        character_list = [char for char in ip_address]
        offset_list = [(-7*i) for i in range(len(character_list))]
        
        matrix.reset()
        for i in range(len(character_list)):
            if offset_list[i] <= 6 and offset_list[i] >=-6:
                matrix.set_character(character_list[i], offset = offset_list[i] // 1, multiplex = True, blue = 100)
        matrix.np.write()
        
        redraw = False
        
        while webrepl.client_s is None:
            redraw = False

            if left.value() != 0 and right.value() == 0:
                for i in range(len(offset_list)):
                    offset_list.append(offset_list.pop(0) + 0.1)
                redraw = True
            elif right.value() != 0 and left.value() == 0:
                for i in range(len(offset_list)):
                    offset_list.append(offset_list.pop(0) - 0.1)
                redraw = True
            
            if redraw:
                matrix.reset()
                for i in range(len(character_list)):
                    if offset_list[i] <= 6 and offset_list[i] >=-6:
                        matrix.set_character(character_list[i], offset = offset_list[i] // 1, multiplex = True, blue = 100)
                matrix.np.write()
            else:
                time.sleep(1.0)
    else:
        on=True
        while webrepl.client_s is None:
            if on:
                matrix.reset()
                on = False
            else:
                matrix.set_manual(16, (100, 0, 100))
                on = True
            time.sleep(1.0)

    matrix.reset()

with open("state") as file:
    state = file.read()

if state == "0": # startup sequence
    with open("state", "w") as file:
        file.write("1")
    
    startup()
    machine.reset()

elif state == "1": # AP mode
    with open("state", "w") as file:
        file.write("0")
    
    # check_and_connect_wifi()
    test_connect_wifi()
    if wifi.wlan.isconnected():
        with open("state", "w") as file:
            file.write("2")
        machine.reset()
    
    init_ap()
    start_dns()
    last_wifi_ap_list = getWiFiAPList()
    last_wifi_ap_scan_time = time.time()
    wait_for_websocket()

elif state == "2": # WiFi mode
    with open("state", "w") as file:
        file.write("0")
    
    check_and_connect_wifi()
    init_ap()
    start_dns()
    last_wifi_ap_list = getWiFiAPList()
    last_wifi_ap_scan_time = time.time()
    wait_for_websocket()
