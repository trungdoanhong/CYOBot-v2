# Continue on another computer

This fork's current application is **CYOBot Studio + HardwareBridge**. The original MicroPython Portal remains available as a separate firmware option. Do not run both controllers against the same board.

## Clone and start Studio

Install Git and Python 3.12 (the tested version), then run:

```sh
git clone https://github.com/trungdoanhong/CYOBot-v2.git
cd CYOBot-v2
python software/HardwareBridge/host/studio.py --open
```

On systems where Python is named `python3`, substitute `python3`. Windows users can also double-click `software/HardwareBridge/host/start_studio.cmd`. The Studio runtime needs no pip or npm packages. The original crawler URDF, all meshes, fonts and browser dependencies are included in Git.

Open http://127.0.0.1:8765. Use **Preview** first, or connect the PC and robot to the same Wi-Fi, open **Fleet**, scan/add its current IP and click **Connect robot**. Stop/disconnect Studio on the old PC before claiming the board from the new PC. The robot permits one control owner. Allow local-network access if your OS firewall prompts for Python; Studio's HTTP interface remains on localhost.

The board already running HardwareBridge does not need reflashing when moving the PC app. The browser's previous IP selection is not synchronized; discover the robot again if its DHCP address changes.

## Optional: build and flash firmware

```sh
cd software/HardwareBridge
python -m pip install -r requirements-dev.txt
python tools/configure_wifi.py
python -m platformio run
python -m platformio run --target upload --upload-port YOUR_SERIAL_PORT
```

Replace `YOUR_SERIAL_PORT` with the actual port (for example COM6 or /dev/ttyUSB0). Configuring Wi-Fi writes ignored `wifi.local.json`; the build generates ignored `include/wifi_config.h`. Neither is uploaded to GitHub. Alternatively copy `wifi.example.json` to `wifi.local.json` and edit locally, or set both `CYOBOT_WIFI_SSID` and `CYOBOT_WIFI_PASSWORD` environment variables. Environment settings take precedence.

Motor channel order, signs and offsets are stored in `software/MicroPython/sd/config/robot-config.json`. Its tracked Wi-Fi fields are intentionally blank. Studio and SDK use its motor settings; `studio.py --config PATH` selects another calibrated robot configuration. For the legacy MicroPython Portal, configure Wi-Fi through its onboarding flow or a private deployment configuration before use; HardwareBridge's wifi.local.json is for the C++ build only.

## Verify the checkout

Node.js is needed only for the JavaScript development tests (CI uses Node 22), not to run Studio.

```sh
python scripts/check_project.py
```

The command verifies bundled model hashes and runs both Python test suites plus the JavaScript tests when Node is installed. It does not connect to or move a robot. The GitHub Actions workflow also builds firmware using dummy Wi-Fi values; it never flashes a board.

## Project map

| Path | Purpose |
|---|---|
| `software/HardwareBridge/host/` | PC controller, SDK, local server and browser UI |
| `software/HardwareBridge/src/`, `include/`, `lib/` | ESP32-S3 C++ firmware and codec sources |
| `software/HardwareBridge/host/ui/robot/` | Original robot URDF/STL assets and checksums |
| `software/HardwareBridge/tests/` | Hardware-free controller, protocol, media and UI unit tests |
| `software/HardwareBridge/examples/` | Runnable integration examples |
| `software/MicroPython/` | Legacy MicroPython firmware, Portal and SD content |
| `hardware/` | Original electronics and mechanical designs |
| `docs/HANDOFF.md` | Current functionality, limitations and continuation notes |

Read the [application guide](../software/HardwareBridge/README.md) and [Developer Guide](../software/HardwareBridge/docs/DEVELOPER_GUIDE.md) for controls and integration APIs.

## Files intentionally not synchronized

Wi-Fi secrets, build outputs, Python caches, local connection logs, recordings/screenshots, temporary CAD work and phone-mount outputs are excluded. The pre-flash recovery binaries mentioned in historical validation notes are local backups on the previous computer and are not included. Keep them separately if full-flash rollback is needed. The current app's robot meshes and all required source files are included.
