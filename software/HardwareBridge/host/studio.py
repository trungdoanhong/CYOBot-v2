"""Local 3D control studio. Run: python host/studio.py --open"""
from __future__ import annotations
import argparse
from collections import deque
from concurrent.futures import Future, TimeoutError as FutureTimeout
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import math
import mimetypes
from pathlib import Path
import queue
import secrets
import threading
import time
from urllib.parse import urlparse, parse_qs, quote
from urllib.request import urlopen
import webbrowser

from cyobot import Fleet, JointMap, OWNED, PWM_OK, IMU_OK, FAULT, LED_READY, SD_READY, AUDIO_READY, MEDIA_READY, led_bytes
from gait import CrawlerGait, GAITS
from media import RobotMedia, read_exact, MAX_FILE
from routines import Routine
from led_effects import LedEffect

ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT.parents[1] / "MicroPython/sd/config/robot-config.json"
UI = ROOT / "ui"


def number(value, lo, hi):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError("Value out of range")
    return value


class Studio:
    """One actor owns the UDP socket; HTTP never blocks the 100 Hz control loop."""
    def __init__(self, config=DEFAULT_CONFIG, fleet_factory=Fleet, auto_scan=True,
                 connection_log_path=ROOT.parent/'reports'/'studio-connection-events.jsonl'):
        self.mapping = JointMap.load(config)
        self.fleet_factory = fleet_factory
        self.connection_log_path = connection_log_path
        self.mailbox = queue.Queue(maxsize=128)
        self.lock = threading.Lock()
        self.stopped = threading.Event()
        self.devices = {}
        self.robot = None
        self.media = None
        self.fleet = None
        self.client = None
        self.client_at = 0
        self.mode = "hold"
        self.targets = [0] * 16
        self.current = [0] * 16
        self.test = None
        self.gait = None
        self.routine = None
        self.led_effect = None
        self.effect_at = self.effect_next = 0
        self.gait_phases = {name:CrawlerGait(name).phases for name in GAITS}
        self.motion_at = 0
        self.error = ""
        self.led_pending = None
        self.led_sent_at = 0
        self.led_attempts = 0
        self.scanning = False
        self.auto_scan = auto_scan
        self.next_scan = time.perf_counter()+10
        self.scan_addresses = ["192.168.1.8", "192.168.1.255"]
        self.snapshot = {}
        self.connection_history = deque(maxlen=150)
        self.connection_event = None
        self.next_record = self.next_diagnostics = 0
        self.max_tick_gap_ms = 0
        self.frames_sent = 0
        self.recovery = None
        self.recover_at = 0
        self.reconnections = 0
        self.browser_paused = False
        self.link_stale = False
        self.applied_sequence = None
        self.progress_at = 0
        self.worker = threading.Thread(target=self._run, name="cyobot-control", daemon=True)
        self.worker.start()
        if auto_scan:
            self.scan(["192.168.1.8", "192.168.1.255"])

    def scan(self, addresses):
        addresses = list(dict.fromkeys(str(ipaddress.IPv4Address(ip)) for ip in addresses))
        if not 1 <= len(addresses) <= 32:
            raise ValueError("Choose 1–32 addresses")
        with self.lock:
            if self.scanning:
                return
            self.scanning = True
            self.scan_addresses = list(dict.fromkeys(self.scan_addresses+addresses))[-32:]
        def discover():
            try:
                with self.fleet_factory() as scanner:
                    found = scanner.discover(addresses, timeout=.5)
                    for robot in found:
                        if hasattr(scanner, 'query_diagnostics'):
                            scanner.query_diagnostics(robot)
                    if found:
                        scanner.poll(.03)
                self.mailbox.put(("found", {"robots": found}, None), timeout=1)
            except Exception:
                self.mailbox.put(("scan_error", {}, None), timeout=1)
        threading.Thread(target=discover, name="cyobot-discovery", daemon=True).start()

    def action(self, data, timeout=2):
        future = Future()
        self.mailbox.put_nowait((data.get("action"), data, future))
        try:
            return future.result(timeout=timeout)
        except FutureTimeout:
            future.cancel()
            raise

    def state(self):
        with self.lock:
            return dict(self.snapshot, scanning=self.scanning)

    def close(self):
        self.stopped.set()
        self.worker.join(timeout=2)

    def _disconnect(self):
        self.routine = self.led_effect = None
        self.recovery = None
        self.link_stale = False
        self.mode = "hold"
        self.led_pending = None
        if self.media:
            self.media.close()
            self.media = None
        if self.robot and self.robot.session:
            try:
                self.fleet.release(self.robot)
            except OSError:
                pass
        self.robot = None
        self.client = None

    def _lose_link(self, now, detail=None):
        robot, client, client_at = self.robot, self.client, self.client_at
        self._connection_failure('telemetry_or_lease',now,detail)
        self._disconnect()
        self.recovery = dict(mac=robot.mac, client=client, boot=robot.boot)
        self.client, self.client_at = client, client_at
        self.recover_at = now+.1
        self.error = "Reconnecting · holding last angles"

    def _recover(self, now):
        if not self.recovery or now < self.recover_at:
            return
        request = self.recovery
        self.recover_at = now+.5
        try:
            # No stale targets/LED edits survive this claim. _connect reads the
            # board's actual PWM state, including all-off after a reboot.
            self._connect(request['mac'],request['client'])
        except (OSError, RuntimeError, ValueError):
            self.recovery = request
            self.client = request['client']
            self.error = "Reconnecting · holding last angles"
            return
        self.recovery = None
        self.reconnections += 1
        self.error = ("Robot rebooted · connected" if self.robot.boot != request['boot']
                      else "Reconnected · holding")

    def _connection_failure(self, reason, now, detail=None):
        robot = self.robot
        self.connection_event = dict(time=time.time(), reason=reason, detail=detail,
            mac=robot.mac if robot else None, boot=robot.boot if robot else None,
            telemetry=robot.telemetry if robot else None,
            diagnostics=robot.diagnostics if robot else None,
            history=list(self.connection_history))
        try:
            if self.connection_log_path is None:
                return
            path = Path(self.connection_log_path)
            path.parent.mkdir(exist_ok=True)
            with path.open('a',encoding='utf-8') as log:
                log.write(json.dumps(self.connection_event,ensure_ascii=False)+'\n')
        except OSError:
            pass

    def _connect(self, mac, client):
        if not isinstance(client, str) or not 8 <= len(client) <= 128:
            raise ValueError("Invalid browser session")
        if (self.robot or self.recovery) and self.client != client and time.perf_counter()-self.client_at <= .8:
            raise ValueError("Robot is active in another window")
        if mac not in self.devices:
            raise ValueError("Scan again to find the robot")
        ip = self.devices[mac]["ip"]
        self._disconnect()
        robot = None
        for _ in range(3):
            found = self.fleet.discover([ip], timeout=.2)
            robot = next((r for r in found if r.mac == mac), None)
            if robot is not None:
                break
        if robot is None:
            raise ValueError("Robot is not responding")
        self.fleet.claim(robot)
        self.robot, self.client = robot, client
        self.media = RobotMedia(robot)
        self.client_at = time.perf_counter()
        self.targets = list(robot.telemetry["ticks"])
        self.current = list(self.targets)
        self.mode, self.error = "hold", ""
        self.browser_paused = self.link_stale = False
        self.applied_sequence = robot.telemetry.get('applied_seq')
        self.progress_at = time.perf_counter()
        self.max_tick_gap_ms = self.frames_sent = 0
        self.connection_history.clear()

    def _handle(self, kind, data):
        if kind == "found":
            for robot in data["robots"]:
                self.devices[robot.mac] = dict(mac=robot.mac, ip=robot.address[0], flags=robot.flags,
                                              diagnostics=robot.diagnostics,
                                              seen=time.perf_counter(), name="Crawler · " + robot.mac[-5:].replace(":", ""))
            with self.lock:
                self.scanning = False
            return
        if kind == "scan_error":
            self.error = "No robot found. Check Wi-Fi or IP address."
            with self.lock:
                self.scanning = False
            return
        if kind == "scan":
            self.scan(data.get("addresses", ["192.168.1.8", "192.168.1.255"]))
            return
        if kind == "connect":
            self._connect(data.get("mac"), data.get("client"))
            return
        if kind == "heartbeat":
            if (self.robot or self.recovery) and data.get("client") == self.client:
                self.client_at = time.perf_counter()
                self.browser_paused = False
            return
        if kind == 'disconnect' and self.recovery and data.get('client') == self.client:
            self._disconnect()
            self.error = ""
            return
        if not self.robot or data.get("client") != self.client:
            raise ValueError("Connect a robot to control it")
        if kind not in ('disconnect','hold','off') and data.get('control_session') != self.robot.session:
            raise ValueError("Control session changed · send a new command")
        self.client_at = time.perf_counter()
        self.browser_paused = False
        if self.link_stale and kind not in ('disconnect','hold','off'):
            raise ValueError("Wait for robot feedback before sending commands")
        if kind not in ('heartbeat', 'leds'):
            self.error = ""
        if kind == "disconnect":
            self._disconnect()
        elif kind == "hold":
            self.mode = "hold"
            self.targets = list(self.current)
        elif kind == "joint":
            channel = number(data.get("channel"), 0, 15)
            if not isinstance(channel, int):
                raise ValueError("Invalid servo channel")
            angle = number(data.get("angle"), -90, 90)
            self.mode = "hold"
            self.targets[channel] = round(self.robot.minimum + (angle + 90) * (self.robot.maximum - self.robot.minimum) / 180)
        elif kind == "channel_off":
            channel = number(data.get("channel"), 0, 15)
            if not isinstance(channel, int):
                raise ValueError("Invalid servo channel")
            self.mode = "hold"
            self.targets[channel] = 0
        elif kind == "center":
            self.targets = self.mapping.ticks([0]*8, self.robot.minimum, self.robot.maximum)
            self.mode = "hold"
        elif kind == "leds":
            matrix, ring = data.get("matrix"), data.get("ring")
            led_bytes(matrix, ring)
            if not self.robot.flags & LED_READY:
                raise ValueError("Install LED-capable firmware")
            self.led_effect = None
            self.led_pending = dict(matrix=[list(p) for p in matrix], ring=[list(p) for p in ring])
            self.led_attempts, self.led_sent_at = 0, 0
            if self.error.startswith("LED"):
                self.error = ""
        elif kind == 'led_effect':
            if not self.robot.flags & LED_READY:
                raise ValueError('LED firmware support required')
            effect = LedEffect(**{k:data[k] for k in ('effect','text','color','brightness','speed') if k in data})
            self.led_effect = effect
            self.effect_at = time.perf_counter()
            self.effect_next = 0
            self.led_pending = None
        elif kind == 'led_effect_stop':
            self.led_effect = None
            self.led_pending = None
        elif kind == 'routine':
            routine = Routine(data.get('name'),self.mapping.angles(self.current,self.robot.minimum,self.robot.maximum),
                              data.get('speed',1),data.get('repeats',1))
            # Reject incompatible calibration before starting or changing targets.
            for frame in routine.frames:
                self.mapping.ticks(frame['angles'],self.robot.minimum,self.robot.maximum)
            self.routine = routine
            self.mode,self.motion_at = 'routine',time.perf_counter()
        elif kind == "test":
            channel = number(data.get("channel"), 0, 15)
            if not isinstance(channel, int):
                raise ValueError("Invalid servo channel")
            amplitude = number(data.get("amplitude", 10), 1, 45)
            period = number(data.get("period", 2), 1, 8)
            center = self._angle(self.current[channel]) if self.current[channel] else 0
            if abs(center) + amplitude > 90:
                raise ValueError("Reduce amplitude to stay within ±90°")
            self.test = dict(channel=channel, amplitude=amplitude, period=period, center=center)
            self.mode, self.motion_at = "test", time.perf_counter()
        elif kind == "walk":
            command = data.get("direction")
            if command not in GAITS:
                raise ValueError("Invalid direction")
            cycle = number(data.get("cycle", 1.5), .6, 3)
            self.gait = CrawlerGait(command, self.mapping.angles(self.current, self.robot.minimum, self.robot.maximum), cycle)
            self.mode, self.motion_at = "walk", time.perf_counter()
        elif kind == "off":
            mac, client = self.robot.mac, self.client
            self.fleet.off(self.robot)
            self._disconnect()
            # OFF confirmed, then start a fresh monitoring session with all channels off.
            self._connect(mac, client)
        else:
            raise ValueError("Invalid action")

    def _angle(self, tick):
        return (tick - self.robot.minimum) * 180 / (self.robot.maximum - self.robot.minimum) - 90 if tick else 0

    def _tick(self, now, dt):
        robot = self.robot
        if not robot:
            self._recover(now)
            return
        self.fleet.poll()
        self.max_tick_gap_ms = max(self.max_tick_gap_ms, dt*1000)
        if now >= self.next_record:
            self.connection_history.append(dict(t=now, frames_sent=self.frames_sent, seq=robot.sequence,
                gap_ms=round(dt*1000,2), max_gap_ms=round(self.max_tick_gap_ms,2),
                age_ms=round((now-robot.seen_at)*1000,2), client_age_ms=round((now-self.client_at)*1000,2),
                telemetry=dict(robot.telemetry) if robot.telemetry else None))
            self.next_record = now+.1
        if now >= self.next_diagnostics and hasattr(self.fleet,'query_diagnostics'):
            self.fleet.query_diagnostics(robot)
            self.next_diagnostics=now+1
        if (now - robot.seen_at > robot.lease_ms / 1000 or not robot.flags & OWNED or robot.flags & FAULT):
            if robot.flags & FAULT:
                self._connection_failure('hardware_fault',now)
                self._disconnect()
                self.error = "Hardware fault · check the board"
            else:
                self._lose_link(now)
            return
        applied = robot.telemetry.get('applied_seq')
        if applied != self.applied_sequence:
            self.applied_sequence, self.progress_at = applied, now
        # Downlink telemetry can stay fresh while uplink commands are lost.
        self.link_stale = max(now-robot.seen_at,now-self.progress_at) > .1
        if self.link_stale or now-self.client_at > .8 or dt > .1:
            if self.led_effect:
                self.led_effect = None
                self.led_pending = None
            # If the uplink stalls while downlink is fresh, freeze the confirmed
            # board PWM, not a submitted frame that may never have arrived.
            # Browser scheduling must stop motion, not tear down a healthy link.
            if self.mode != 'hold' or self.targets != self.current:
                if self.link_stale and now-robot.seen_at <= .1:
                    self.current = list(robot.telemetry['ticks'])
                self.targets = list(self.current)
                self.mode = 'hold'
                self.error = "Holding · send a new command to continue"
            self.browser_paused = now-self.client_at > .8
            if self.link_stale:
                self.led_pending = None
        if self.mode == "test":
            t = self.test
            angle = t["center"] + t["amplitude"] * math.sin((now-self.motion_at)*math.tau/t["period"])
            self.targets[t["channel"]] = round(robot.minimum + (angle+90)*(robot.maximum-robot.minimum)/180)
        elif self.mode == "walk":
            self.targets = self.mapping.ticks(self.gait.angles(now-self.motion_at), robot.minimum, robot.maximum)
        elif self.mode == 'routine':
            mapped = self.mapping.ticks(self.routine.angles(now-self.motion_at),robot.minimum,robot.maximum)
            for joint in self.mapping.joints:
                self.targets[joint['pin']] = mapped[joint['pin']]
            if now-self.motion_at >= self.routine.duration:
                self.mode = 'hold'
        # Smooth jumps on the PC. Servo output remains a direct hardware frame.
        limit = (robot.maximum-robot.minimum) * min(dt, .03)
        for i, target in enumerate(self.targets):
            if target == 0 or self.current[i] == 0:
                self.current[i] = target
            else:
                delta = target-self.current[i]
                self.current[i] += max(-limit, min(limit, delta))
        self.fleet.send_ticks(robot, [round(t) for t in self.current])
        self.frames_sent += 1
        # One acknowledged frame at a time. Slow/lost LED ACKs never block servo ticks.
        if self.led_effect and not self.led_pending and now>=self.effect_next:
            self.led_pending=self.led_effect.frame((now-self.effect_at)/self.led_effect.interval)
            self.led_attempts,self.led_sent_at=0,0
            self.effect_next=now+max(.1,self.led_effect.interval)
        if self.led_pending:
            if robot.leds and all(robot.leds[k] == self.led_pending[k] for k in ("matrix", "ring")):
                self.led_pending = None
            elif now-self.led_sent_at >= .08:
                if self.led_attempts >= 6:
                    self.error = "LED frame unconfirmed · retry"
                    self.led_effect = None
                    self.led_pending = None
                else:
                    self.fleet.send_leds(robot, **self.led_pending)
                    self.led_sent_at = now
                    self.led_attempts += 1

    def _publish(self):
        robot = self.robot
        telemetry = dict(robot.telemetry) if robot and robot.telemetry else None
        selected = robot.mac if robot else None
        if robot:
            self.devices[robot.mac]["seen"] = time.perf_counter()
        records = [dict(d, connected=d["mac"] == selected, online=time.perf_counter()-d["seen"] < 20)
                   for d in self.devices.values()]
        state = dict(service="cyobot-studio", robots=records, selected=selected, connected=bool(robot), mode=self.mode,
                     routine=dict(name=self.routine.name,speed=self.routine.speed,repeats=self.routine.repeats,
                         progress=min(1,max(0,(time.perf_counter()-self.motion_at)/self.routine.duration))) if self.mode=='routine' else None,
                     led_effect=self.led_effect.effect if self.led_effect else None,
                     telemetry=telemetry, owner=self.client, error=self.error,
                     control_session=robot.session if robot else None,
                     connection_stats=dict(frames_sent=self.frames_sent,max_tick_gap_ms=round(self.max_tick_gap_ms,2),
                         diagnostics=robot.diagnostics if robot else None),
                     last_disconnect={k:v for k,v in self.connection_event.items() if k!='history'} if self.connection_event else None,
                     reconnecting=bool(self.recovery), link_stale=self.link_stale,
                     reconnections=self.reconnections, browser_paused=self.browser_paused,
                     media_supported=bool(robot and robot.flags&MEDIA_READY),
                     sd_ready=bool(robot and robot.flags&SD_READY),
                     audio_ready=bool(robot and robot.flags&AUDIO_READY),
                     audio=self.media.audio.state() if self.media and self.media.audio else dict(active=False),
                     joint_channels=[j["pin"] for j in self.mapping.joints],
                     joints=[dict(pin=j["pin"], orientation=j["orientation"], offset=j["offset"]) for j in self.mapping.joints],
                     targets=[round(t) for t in self.targets], test=self.test if self.mode == "test" else None,
                     leds=robot.leds if robot else None, leds_supported=bool(robot and robot.flags & LED_READY),
                     leds_pending=bool(self.led_pending),
                     rtt_ms=round(robot.rtt_ms[-1], 1) if robot and robot.rtt_ms else None,
                     age_ms=max(0,round((time.perf_counter()-robot.seen_at)*1000)) if robot else None,
                     pwm_limits=[robot.minimum, robot.maximum] if robot else [120,600])
        state["gait_phases"] = self.gait_phases
        with self.lock:
            self.snapshot = state

    def _run(self):
        self.fleet = self.fleet_factory()
        previous = time.perf_counter()
        try:
            while not self.stopped.is_set():
                now = time.perf_counter()
                # Control ticks take priority over a busy HTTP command queue.
                try:
                    self._tick(now, now-previous)
                except Exception as exc:
                    if self.robot and isinstance(exc,OSError):
                        self._lose_link(now,repr(exc))
                    else:
                        self._connection_failure('host_exception',now,repr(exc))
                        self.error = "Connection lost · reconnect the robot"
                        self._disconnect()
                previous = now
                for _ in range(8):
                    try:
                        kind, data, future = self.mailbox.get_nowait()
                    except queue.Empty:
                        break
                    if future is not None and not future.set_running_or_notify_cancel():
                        continue
                    try:
                        self._handle(kind, data)
                        if future is not None:
                            future.set_result({"ok":True})
                    except Exception as exc:
                        self.error = str(exc)
                        if future is not None:
                            future.set_exception(exc)
                self._publish()
                if self.auto_scan and now >= self.next_scan and not self.scanning:
                    self.next_scan = now+10
                    self.scan(self.scan_addresses)
                self.stopped.wait(max(0, .01-(time.perf_counter()-now)))
        finally:
            if self.media:self.media.close()
            self.fleet.close()


def create_server(studio, port=8765):
    token = secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def _local_request(self):
            if self.headers.get("Host") not in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"):
                self._send(403, b'{"error":"Local access only"}')
                return False
            return True

        def _send(self, code, content, mime="application/json"):
            try:
                self.send_response(code)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "no-store" if mime.startswith("application/json") else "no-cache")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(content)
            except ConnectionError:
                # Navigation/pagehide can close the HTTP socket after an action succeeds.
                pass

        def do_GET(self):
            if not self._local_request():
                return
            path = urlparse(self.path).path
            if path == '/developer-guide':
                self._send(200,(ROOT.parent/'docs'/'DEVELOPER_GUIDE.md').read_bytes(),'text/plain; charset=utf-8')
                return
            if path == '/api/led-preview':
                try:
                    query=parse_qs(urlparse(self.path).query)
                    effect=LedEffect(effect=query.get('effect',['text'])[0],text=query.get('text',['HELLO'])[0],
                        color=[int(c) for c in query.get('color',['83,217,155'])[0].split(',')],
                        brightness=float(query.get('brightness',['20'])[0]),speed=float(query.get('speed',['1'])[0]))
                    self._send(200,json.dumps(effect.preview()).encode())
                except (ValueError,TypeError):
                    self._send(400,b'{"error":"Invalid LED preview options"}')
                return
            if path.startswith('/api/media/'):
                self._media_get(path)
                return
            if path == "/api/state":
                self._send(200, json.dumps(studio.state(), allow_nan=False).encode())
                return
            file = (UI / ("index.html" if path == "/" else path.lstrip("/"))).resolve()
            if not file.is_relative_to(UI.resolve()) or not file.is_file():
                self._send(404, b'{"error":"Not found"}')
                return
            content = file.read_bytes()
            if file.name == "index.html":
                content = content.replace(b"__CYO_TOKEN__", token.encode())
            mime = "text/javascript" if file.suffix == ".js" else mimetypes.guess_type(file.name)[0] or "application/octet-stream"
            self._send(200, content, mime + ("; charset=utf-8" if mime.startswith("text/") else ""))

        def do_POST(self):
            if not self._local_request():
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if urlparse(self.path).path in ('/api/media/upload','/api/media/pcm'):
                    self._media_binary(length)
                    return
                if not 0 < length <= 8192:
                    raise ValueError("Request too large")
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError("Invalid request")
                received = self.headers.get("X-CYO-Token", data.pop("token", ""))
                if not isinstance(received,str) or not hmac.compare_digest(received, token):
                    self._send(403, b'{"error":"Invalid local token"}')
                    return
                if self.path == '/api/media/action':
                    media=self._media(data)
                    op=data.get('op')
                    if op=='audio_start':result=media.start_audio().state()
                    elif op=='audio_stop':media.stop_audio();result=dict(active=False)
                    elif op=='volume':
                        if not media.audio or not media.audio.alive:raise ValueError('Open the audio stream first')
                        media.audio.set_volume(data.get('value'));result=media.audio.state()
                    elif op=='speaker_stop':
                        if media.audio:media.audio.clear_speaker()
                        result=dict(ok=True)
                    elif op=='mount':result=media.info(mount=True)
                    else:result=media.change(op,data.get('path'),data.get('target'))
                    self._send(200,json.dumps(result).encode());return
                if self.path != "/api/action":
                    self._send(404, b'{"error":"Not found"}')
                    return
                result = studio.action(data)
                self._send(200, json.dumps(result).encode())
            except (ValueError, KeyError, TypeError) as exc:
                self._send(400, json.dumps({"error":str(exc)}).encode())
            except (queue.Full, FutureTimeout):
                self._send(503, b'{"error":"Try again"}')
            except Exception as exc:
                self._send(409, json.dumps({"error":str(exc)}).encode())

        def _media(self,data):
            state=studio.state();media=studio.media
            if not state.get('connected') or data.get('client')!=state.get('owner') or not media:
                raise ValueError('Connect the robot in this window first')
            if str(data.get('control_session'))!=str(media.session):raise ValueError('Control session changed')
            if not state.get('media_supported'):raise ValueError('Install media-capable firmware')
            return media

        def _media_headers(self):
            received=self.headers.get('X-CYO-Token','')
            if not hmac.compare_digest(received,token):raise ValueError('Invalid browser session')
            return self._media(dict(client=self.headers.get('X-CYO-Client'),
                control_session=self.headers.get('X-CYO-Session')))

        def _media_get(self,path):
            started=False
            try:
                media=self._media_headers();query=parse_qs(urlparse(self.path).query)
                if path=='/api/media/info':result=media.info()
                elif path=='/api/media/files':result=media.files(query.get('path',['/'])[0],int(query.get('offset',['0'])[0]))
                elif path=='/api/media/mic':
                    if not media.audio or not media.audio.alive:raise ValueError('Audio stream stopped')
                    self._send(200,media.audio.read_available(),'application/octet-stream');return
                elif path=='/api/media/download':
                    file_path=query.get('path',[''])[0]
                    from media import validate_path
                    validate_path(file_path)
                    with media.request('download',path=file_path) as (_,stream,result):
                        size=result.get('size')
                        if type(size) is not int or size<0:raise ValueError('Invalid file size')
                        self.send_response(200);self.send_header('Content-Type','application/octet-stream')
                        self.send_header('Content-Length',str(size));self.send_header('Cache-Control','no-store')
                        self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+quote(file_path.rsplit('/',1)[-1]))
                        self.end_headers();started=True
                        while size:
                            data=read_exact(stream,min(4096,size));self.wfile.write(data);size-=len(data)
                    return
                else:raise ValueError('Invalid API request')
                self._send(200,json.dumps(result).encode())
            except Exception as exc:
                if not started:self._send(409,json.dumps(dict(error=str(exc))).encode())
                else:self.close_connection=True

        def _media_binary(self,length):
            media=self._media_headers();path=urlparse(self.path).path
            if path=='/api/media/pcm':
                if not 0<length<=3840:raise ValueError('PCM packet is too large')
                if not media.audio or not media.audio.alive:raise ValueError('Audio stream stopped')
                media.audio.write_pcm(read_exact(self.rfile,length));result=dict(ok=True)
            else:
                if not 0<=length<=MAX_FILE:raise ValueError('Files must be at most 32 MiB')
                file_path=parse_qs(urlparse(self.path).query).get('path',[''])[0]
                self.connection.settimeout(10)
                result=media.upload(file_path,self.rfile,length)
            self._send(200,json.dumps(result).encode())
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--open", action="store_true")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    studio = Studio(args.config)
    try:
        server = create_server(studio, args.port)
    except OSError:
        studio.close()
        if args.open:
            url = f"http://127.0.0.1:{args.port}"
            try:
                with urlopen(url+"/api/state", timeout=1) as response:
                    existing = json.load(response)
                if existing.get("service") == "cyobot-studio":
                    webbrowser.open(url)
                    return
            except Exception:
                pass
        raise
    url = "http://127.0.0.1:%s" % server.server_port
    print("CYOBot Studio · " + url, flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        studio.close()


if __name__ == "__main__":
    main()
