# Development handoff — 2026-10-09

## Current application

Use `software/HardwareBridge`, not the legacy Portal, for the PC-controlled crawler. Studio runs at localhost:8765, in English. It has Fleet, Robot and Policy Lab workspaces; the Robot panel groups Servo, IMU, LED, Audio and Storage. The original 115-mesh crawler model is bundled locally.

- Six PC-side motion routines: Ready pose, Bow, Wave, Sway, Stretch and Bounce, with speed/repeat controls and 3D preview.
- Individual servo control, calibrated home pose, servo sweep and directional crawler gaits.
- 33-pixel matrix / 12-pixel ring painting and text, heart, face, rainbow and chase effects.
- IMU/button/battery telemetry, duplex microphone/speaker PCM, and microSD file management.
- Reconnection diagnostics and watchdogs. Communication loss holds the last servo command; recovery does not resume a motion program or LED effect.

The Python SDK supports multiple robot identities. Studio manually controls one robot at a time. Stop the old controller before using a new PC.

## AI objective

The intended controller is a model trained in NVIDIA simulation, with inference on the PC and lightweight hardware control on each robot. Policy Lab currently shows integration readiness and exports telemetry; it does not load a trained model. `host/run_policy.py` provides the Python adapter interface.

Next integration work needs the exported policy and its training environment/I/O specification. Match joint order, normalization, observations, actuator model and action rate. Position-servo commands are not torque commands. The robot does not supply measured joint angles/velocities or foot contacts. See the Developer Guide before creating an adapter.

## Validation boundaries

- Automated tests cover protocol/session behavior, timeouts, routine interpolation/calibration, LED generation, simulated SD/media and UI helpers.
- Studio previews were checked in desktop and narrow layouts. New routines have not been mechanically validated on the assembled robot.
- Earlier firmware/connection/audio work includes real-board checks in `software/HardwareBridge/VALIDATION.md`. The referenced local recordings, screenshots and raw reports are not in Git.
- No physical microSD card was available; actual-card read/write validation remains outstanding.
- Capacity for dozens of physical robots has not been measured on the real Wi-Fi network.

## Workspace scope

This handoff includes app/firmware, documentation and the robot model used by Studio. Phone-mount CAD, temporary mechanical work and the locally modified crawler connector 3MF are intentionally excluded from this publication. Their existing files remain on the original PC.

Wi-Fi credentials are private local settings; see [SETUP.md](SETUP.md). Firmware is built, not stored as a binary in Git. The source includes third-party dependency licenses and model provenance.
