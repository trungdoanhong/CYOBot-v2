# CYOBot HardwareBridge — Developer Guide

Build PC applications that control CYOBrain V2 over the local network. Run all commands from `software/HardwareBridge`. Python uses the standard library; the browser UI bundles its 3D dependencies locally.

## Architecture and ownership

Robot sensors → UDP telemetry → PC controller / policy → UDP hardware frames → robot.

The ESP32 handles hardware I/O. Gaits, motion programs, LED effects, audio processing and AI inference run on the PC. Studio's actor owns its UDP socket and schedules servo frames at 100 Hz. HTTP handlers enqueue actions; file/audio TCP traffic is separate. Studio supports one manual robot session. The Python Fleet SDK supports multiple robots; throughput for dozens of physical robots has not been measured.

Choose one owner: Studio OR your SDK application. Disconnect Studio before claiming the same robot elsewhere. A session belongs to a host IP/UDP port and a session ID; changing either requires a new claim. Closing/releasing a session preserves the last servo pulses. `Fleet.off()` explicitly disables pulses and verifies an acknowledgement. LED colors are retained after release.

## Start and inspect

```powershell
python host/studio.py --open
python -B -m unittest discover -s tests
python examples/run_routine.py bow
```

The last command only prints preview angles. Add `--ip 192.168.1.8` to send the routine to that robot. Studio opens at http://127.0.0.1:8765. The Developer guide button links to this document. UI controls and controller errors are in English.

## Python SDK: connection, observations and actions

Put a script in `host/` to import `cyobot`, or add that directory to `sys.path` as in `examples/run_routine.py`.

```python
from cyobot import Fleet

with Fleet() as fleet:
    robots = fleet.discover(["192.168.1.8"])
    if len(robots) != 1:
        raise RuntimeError("Expected one robot")
    robot = robots[0]
    fleet.claim(robot)

    def controller(observations):
        observation = observations[robot.mac]
        # Identity controller: keep the current pulse values, including OFF.
        return {robot.mac: list(observation["ticks"])}

    fleet.run([robot], controller, hz=50, seconds=5)
```

`Fleet.run` calls `controller({mac: observation})`. Return `{mac: [16 integer ticks]}`. Zero disables a channel; otherwise use the board's advertised `minimum..maximum`. A missing MAC receives no frame. The SDK does not replay an old action or reclaim a lost session. `Fleet.claim_all(robots)` handles multiple claims while renewing already claimed robots.

Observation fields:

- `accel_g`: XYZ acceleration in g; `gyro_dps`: XYZ angular velocity in degrees/second.
- `imu_us`, `uptime_us`: unsigned 32-bit robot timestamps; subtract modulo 2^32.
- `ticks`: 16 commanded PWM values. These are NOT measured servo joint angles.
- `battery_v`, `buttons` (bit0 left, bit1 right), `flags`.
- `accepted_seq`, `applied_seq`: command receipt/application counters.
- `received`, `applied`, `rejected`, `apply_us`: firmware counters and last I2C write timing.
- `host_age_s`: added by `Fleet.run`; age of the latest received telemetry.

The MCU holds the last pulse values when its 1,000 ms command lease expires. Fleet fails earlier if telemetry/command progress or inference exceeds its 250 ms bound. Studio holds motion on stale progress, a browser heartbeat gap over 800 ms, or a control tick gap over 100 ms. It may reconnect for monitoring but never resumes a test, gait, routine or LED animation automatically. Check exceptions and reconnect explicitly in custom applications.

## Joint order, units and calibration

`JointMap` loads only the motor mapping from the configuration JSON. Logical order is `[leg0 upper, leg0 lower, leg1 upper, leg1 lower, leg2 upper, leg2 lower, leg3 upper, leg3 lower]`. Current channels are `[4,5,6,7,11,10,0,1]`.

```python
from cyobot import JointMap
mapping = JointMap.load("../MicroPython/sd/config/robot-config.json")
ticks = mapping.ticks([0]*8, robot.minimum, robot.maximum)
angles = mapping.angles(robot.telemetry["ticks"], robot.minimum, robot.maximum)
```

Angles are logical degrees. `physical = logical * orientation + offset`. Physical angles must remain within -90..90 degrees; invalid values raise an exception. `JointMap.ticks()` returns a complete 16-channel frame with non-crawler channels OFF. Merge the eight mapped values into an existing frame when other channels must stay enabled; see the routine example. An OFF joint has no known physical angle; `angles()` uses logical zero for that channel. Servo pulse commands and the 3D model cannot reveal mechanical stalls or actual joint position.

## Add or run a motion program

`host/ui/routines.json` is the shared catalog for the Python runner and browser preview. Entries contain a label, icon name and frames:

```json
{"my_pose":{"label":"My pose","icon":"wave","frames":[
  {"seconds":1.5,"angles":[0,10,0,10,0,10,0,10]},
  {"seconds":1.5,"angles":[0,0,0,0,0,0,0,0]}
]}}
```

Merge an entry into the existing catalog, then restart Studio and reload the page. Each frame has eight logical angles and a positive transition duration. The runner uses smoothstep interpolation from the preceding pose. Programs run 1–5 times at 0.5–1.5× speed, then hold the final pose. Studio validates all calibrated frame angles before starting and preserves the other eight channels. Its Hold, manual motion commands, session loss and leaving the Robot workspace stop a running routine.

Bundled motion presets are Ready pose, Bow, Wave, Sway, Stretch and Bounce. Preview them on the original 3D model and tune calibration/keyframes for your assembled robot. The model is a visualization, not a collision or dynamics simulation; the new routines have automated controller/preview tests but have not been mechanically validated on the assembled robot.

## Matrix and ring LEDs

Looking at the LED side, with RESET at the top and USB at the bottom, the 33-pixel matrix rows are:

```text
        0  1  2  3  4
     5  6  7  8  9 10 11
 12 13 14 15 16 17 18 19 20
    21 22 23 24 25 26 27
       28 29 30 31 32
```

The ring has 12 pixels: index 0 at the top, increasing clockwise. The center 5×5 character grid uses `[0,1,2,3,4,6,7,8,9,10,14,15,16,17,18,22,23,24,25,26,28,29,30,31,32]`. GPIO15 drives the matrix; GPIO7 drives the ring. SDK colors are RGB bytes; firmware handles the physical GRB order.

```python
from led_effects import LedEffect
effect = LedEffect(effect="text", text="HELLO", brightness=20)
frame = effect.frame(5)
fleet.send_leds(robot, **frame)
# Continue the servo/lease loop and call fleet.poll().
# robot.leds contains the latest acknowledged matrix/ring colors.
```

Effects: `text`, `heartbeat`, `face`, `rainbow`, `chase`. Text supports A–Z, digits, spaces and `! ? - .`, at most 32 characters. Options: RGB `color`, `brightness` 0–100, `speed` 0.5–2. `effect.preview()` returns frames and an interval in seconds; it never accesses hardware.

Studio renders effects on the PC with at most 10 new frames/s and one outstanding acknowledged frame at a time. Missing acknowledgements cause up to 6 sends, at least 80 ms apart, then stop the effect with an error. Manual painting replaces the effect. Stop effect holds the last colors; Clear LEDs sends black to the selected target. Heartbeat/link failure cancels effects; reconnect does not restart them. Preview runs locally using the same frame generator through `/api/led-preview`.

## Audio and SD extensions

`RobotMedia(robot)` opens separate authenticated TCP channels using the active UDP session. It does not renew the command lease. Keep `Fleet.run()` alive and move blocking media I/O to a worker. Do not put file transfers or ASR/TTS inference in the fast control callback.

```python
from media import RobotMedia
media = RobotMedia(robot)
info = media.info()
entries = media.files("/")  # response includes entries and pagination
stream = media.start_audio()
stream.set_volume(20)
pcm = stream.read_pcm(timeout=0.04)
# Input: PCM16 little-endian, 16 kHz, 2 interleaved mic channels.
# Output: stream.write_pcm(block), mono 16 kHz, 640 bytes / 20 ms.
media.stop_audio()
media.close()
```

`media.change('mkdir', path)`, `media.change('rename', path, target)` and `media.change('trash', path)` manage files. Restore by renaming a file from `/.cyobot-trash/` to its destination. `upload(path, binary_source, byte_count)` and `download(path, binary_destination)` transfer binary data. Paths are absolute UTF-8 SD paths; traversal and overwrite are rejected. Browser transfers and SDK uploads are limited to 32 MiB; SDK downloads stream in chunks and can be larger. No SD format operation is exposed.

The board uses ES8311 output and ES7210 dual microphone input; I2S MCLK16/BCLK9/WS45/TX8/RX10, amplifier GPIO47. SD uses SPI SCK12/MISO13/MOSI11/CS14. A FAT32 card is needed. No physical card was available for validation; filesystem operations were tested with an in-memory fixture. Echo cancellation, speech recognition and synthesis are PC integration work, not firmware features.

## Integrate an Isaac Lab / simulation policy

The exported model runs on your PC. `host/run_policy.py` loads a Python file containing `predict(observations)` and expects `{mac: eight logical joint angles in degrees}`. It adds `commanded_angles_deg` to each observation and validates IMU availability/freshness (50 ms) before calling your code. Load the model once at module initialization, not inside each prediction.

```powershell
python host/run_policy.py --policy my_policy.py --ip 192.168.1.8 --robot MAC_ADDRESS=../MicroPython/sd/config/robot-config.json --hz 50
```

Replace MAC_ADDRESS with the discovered MAC. Repeat `--robot` and `--ip` for additional robots. This runner enables the eight mapped joint outputs returned by the policy; use the lower-level Fleet API for per-channel OFF behavior.

Before deployment match the training configuration: observation order, units, normalization and history; action scaling, joint order, signs and offsets; inference cadence and action hold; actuator model and control mode. A torque policy cannot be sent directly as position-servo commands. Cyobot currently has no measured joint angle/velocity feedback, base linear velocity or foot contact sensors. Do not substitute commanded angles for measured angles without designing and validating that observation model during training. Supply an exported model and its environment/I/O configuration to build the adapter. The Policy Lab page does not load or run models yet.

## Local HTTP integration

Studio binds to 127.0.0.1 and checks Host/Origin. Read `GET /api/state`. A local client can obtain the CSRF token from the `cyo-token` meta element in `GET /`; do not publish it. Send JSON to `POST /api/action` with header `X-CYO-Token` and body:

```json
{"action":"routine","client":"your-unique-client-id","control_session":123,"name":"bow","speed":1,"repeats":1}
```

First send `connect` with a discovered `mac` and your unique `client` (8–128 characters); read the new `control_session` from state. Send `heartbeat` every 200 ms while controlling. Ownership and session validation apply to actions. State is read only; merely polling it does not renew a browser heartbeat.

Actions: `scan` (addresses), `connect` (mac), `disconnect`, `heartbeat`, `hold`, `off`, `joint` (channel, angle), `channel_off` (channel), `center`, `test` (channel, amplitude, period), `walk` (direction, cycle), `routine` (name, speed, repeats), `leds` (matrix, ring), `led_effect` (effect, text, color, brightness, speed), `led_effect_stop`. `hold` stops motion; `led_effect_stop` stops animation. Session release stops both. Firmware HOLD retains the last servo angle command.

Media: `GET /api/media/info`, `/files?path=&offset=`, `/mic`, `/download?path=`; `POST /api/media/action`, `/upload?path=`, `/pcm`. Media requests require `X-CYO-Token`, `X-CYO-Client`, `X-CYO-Session`. JSON actions include matching client/session values. See `host/ui/media.js` for the complete browser client. HTTP errors return an `error` message; callers must check status before consuming payloads.

## Wire protocol and source map

- `host/cyobot.py`, `include/protocol.h`: protocol types and binary layouts; UDP 4242.
- `host/studio.py`: local HTTP API, actor, ownership, watchdog and reconnection.
- `host/routines.py`, `host/ui/routines.json`: finite motion programs.
- `host/led_effects.py`: matrix font, physical mapping and effect frames.
- `host/media.py`, `src/media_bridge.cpp`: SD RPC TCP 4243 and PCM TCP 4244.
- `host/ui/workspace.js`, `shell.css`: shared navigation, states and layout.
- `host/ui/robot/README.md`: provenance of the original 115-mesh URDF model.

Header: little-endian `4s BB H II` = magic CYO2, version 1, type, payload length, session, sequence. Types 1–11: DISCOVER, INFO, CLAIM, FRAME, RELEASE, OFF, STATUS, LED_FRAME, LED_STATUS, DIAG_QUERY, DIAGNOSTICS. FRAME is 16×u16; STATUS is 80 bytes; LED_FRAME is 135 RGB bytes; LED_STATUS adds a u32 applied sequence. Servo and LED sequences are independent within the session. Use the SDK rather than duplicating binary layouts.

Flags: OWNED=1, HOLDING=2, PWM_OK=4, IMU_OK=8, FAULT=16, WIFI_OK=32, LED_READY=64, SD_READY=128, AUDIO_READY=256, MEDIA_READY=512. `Fleet.query_diagnostics(robot)` reads diagnostics without claiming/renewing control. Diagnostic packets are not fresh sensor observations or PWM acknowledgements.

## Testing and diagnostics

```powershell
python -B -m unittest discover -s tests
node tests/test_workspace.cjs
node tests/test_routines.cjs
node tests/test_audio_worklet.cjs
python tests/serve_media_fixture.py
```

The fixture on port 8766 uses a fake robot and in-memory card; it never moves hardware. Real smoke scripts under `tools/` are separate. `reports/studio-connection-events.jsonl` records the 15 seconds before a connection failure. Check `connection_stats`, `age_ms`, `link_stale`, firmware RSSI, reset/lease counters and application errors. A 100 Hz schedule is not a measured latency guarantee; benchmark your PC/Wi-Fi and physical robot count.
