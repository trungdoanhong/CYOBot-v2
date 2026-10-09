# CYOBot HardwareBridge + Studio

PC control for CYOBrain V2. The ESP32 runs hardware I/O; the PC runs motion programs, LED animation, audio processing and policy inference. Studio uses the original assembled crawler model with 115 meshes and eight joints.

## Start

Run from `software/HardwareBridge`:

```powershell
python host/studio.py --open
```

Or double-click `host/start_studio.cmd`. Open http://127.0.0.1:8765. Python uses the standard library and the UI bundles Three.js/fonts locally; no npm install is needed.

1. Open **Fleet**, scan or add the robot's IP, then open that robot.
2. Click **Connect robot** on the Robot page. PC and robot must share a LAN.
3. Select **Servo**, **IMU**, **LED**, **Audio** or **Storage** in the tool panel.
4. Use **Preview** to try motion and LED effects without sending commands. Preview disconnects any active control session.

## Motion and display

| Tool | What it does |
|---|---|
| Servo / Joint | Select a joint on the 3D model or select any of the 16 PWM channels. Adjust its commanded angle. Home pose applies calibrated logical zero to the eight crawler joints. |
| Servo / Test servo | Sweep one channel around its current command with adjustable amplitude and period. |
| Servo / Drive | Hold a direction to run the PC-side gait; release to hold the last pose. |
| Servo / Routines | Ready pose, Bow, Wave, Sway, Stretch and Bounce. Choose speed 0.5–1.5×, repeat 1–5 times, then Run routine or Preview routine. |
| LED / LED Studio | Scrolling text, pulsing heart, blinking face, rainbow and ring chase. Set color, brightness and speed. |
| LED / Manual drawing | Paint the 33-pixel matrix or 12-pixel ring, fill/clear a target, or apply a static preset. Manual drawing replaces animation. |
| IMU | Acceleration, angular velocity, gravity-based tilt, buttons, battery voltage and connection timing. |
| Audio | Listen to robot microphones, stream the PC microphone to the speaker, or play an audio file. |
| Storage | Browse microSD, upload/download, create folders, rename/move and move files to trash. Requires a FAT32 card. |

Text supports A–Z, digits, spaces and `! ? - .`, up to 32 characters. Effects use the matrix's physical 5/7/9/7/5 layout and the ring's clockwise pixel order. The font occupies the central 5×5 pixels. **Stop effect** keeps the last colors; **Clear LEDs** turns off the selected LED target.

**Hold / Space** stops motion at the last commanded pose. **Pulses off / Esc** disables servo PWM. Hiding the page, leaving the Robot workspace or losing browser heartbeat stops active motion. Link loss cancels programs; reconnecting never resumes them automatically. LEDs and audio have their own stop controls.

The 3D view displays commanded angles, not measured servo positions. It is not a collision or dynamics simulation. The new motion routines have controller and preview tests but have not been mechanically validated on the assembled robot. Review poses and calibration before physical execution. An unpowered servo has no measured starting angle.

## Developer integration

Read the [Developer Guide](docs/DEVELOPER_GUIDE.md), also accessible from the cube icon in Studio's header. It covers:

- Fleet ownership, telemetry, servo units and calibration.
- Extending the shared routine catalog and generating LED frames.
- microSD and duplex PCM audio APIs.
- Local HTTP actions and UDP/TCP protocols.
- Adapting a policy trained in NVIDIA simulation to this robot's observations and position servos.

Runnable example (preview only unless `--ip` is supplied):

```powershell
python examples/run_routine.py wave
python examples/run_routine.py wave --ip 192.168.1.8 --speed 0.5
```

**Policy Lab** shows integration readiness and exports telemetry. It does not load or run a trained AI model. The separate `host/run_policy.py` runner accepts a Python `predict(observations)` adapter; see the guide. Studio manually controls one robot at a time; the Fleet SDK supports multiple robots. Throughput for dozens of physical robots still needs measurement on the actual Wi-Fi network.

## Hardware and connection behavior

- ESP32-S3, PCA9685 servo controller, LSM6DSL IMU, 33 matrix + 12 ring LEDs.
- ES8311 speaker codec and ES7210 dual microphone input; 16 kHz PCM audio.
- UDP 4242 for servo/LED/telemetry; TCP 4243 for SD/RPC and 4244 for audio.
- Servo frames contain all 16 channels: zero means OFF, normally 120–600 ticks means enabled. PCA9685 prescaler 112 is retained from the original crawler setup, nominally about 54 Hz.
- Studio schedules control at 100 Hz. This is a scheduling target, not a guarantee of mechanical response or end-to-end latency.
- A 1,000 ms firmware command lease preserves the last PWM on expiry. Studio stops changing targets earlier when progress is stale. Power loss/reset starts with servo outputs OFF.
- Session ownership is for a trusted LAN, not encrypted authentication. Studio binds to localhost and checks request ownership/session and CSRF tokens.
- Battery voltage is not calibrated to a charge percentage. Servo angles/velocities and foot contacts are not measured.

Connection diagnostics are saved to `reports/studio-connection-events.jsonl`. See [validation history](VALIDATION.md) for measured hardware results and limitations. No physical SD card was available for the storage checks; the UI/filesystem workflow uses a test fixture.

## Build and test

The new Studio routines and effects work with the existing HardwareBridge LED-capable firmware; this UI update does not require reflashing.

```powershell
python -B -m unittest discover -s tests
node tests/test_workspace.cjs
node tests/test_routines.cjs
node tests/test_audio_worklet.cjs
python tests/serve_media_fixture.py
```

The fixture opens on port 8766 and never controls real hardware.

For a new computer, follow [Setup](../../docs/SETUP.md). To build firmware, install the pinned development tools and configure private Wi-Fi settings:

```powershell
python -m pip install -r requirements-dev.txt
python tools/configure_wifi.py
python -m platformio run
python -m platformio run --target upload --upload-port YOUR_COM_PORT
```

Replace `YOUR_COM_PORT` with the connected board's port. PlatformIO pins Espressif32 6.12.0 / Arduino ESP32 2.0.17. The build script reads ignored `wifi.local.json` (or `CYOBOT_WIFI_SSID` / `CYOBOT_WIFI_PASSWORD`) into ignored `include/wifi_config.h`; changing Wi-Fi requires rebuilding/flashing this firmware. Firmware replaces the original MicroPython app; the former two-button sweep is not part of this C++ runtime.

The previous Vietnamese README, protocol reference and original flash recovery details are preserved in [README.vi.md](README.vi.md). Historical reports retain their original language.
