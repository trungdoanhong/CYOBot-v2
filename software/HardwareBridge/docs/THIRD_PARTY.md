# Bundled dependencies

Studio serves its runtime assets locally so a fresh checkout does not depend on CDNs.

| Component | Source/version | License location |
|---|---|---|
| Three.js runtime and OrbitControls | Three.js r170 | `host/ui/vendor/LICENSE` (MIT) |
| STLLoader | Three.js 0.186.1 export, adapted to the local runtime | `host/ui/vendor/STLLoader-LICENSE.txt` (MIT) |
| URDFLoader | 0.13.1, local STL import adapter | `host/ui/vendor/urdf/LICENSE.txt` (Apache-2.0) |
| Nunito | Copyright 2014 The Nunito Project Authors | `host/ui/Nunito-LICENSE.txt` (SIL OFL 1.1) |
| ES8311 / ES7210 codec code | Espressif ESP-ADF v2.7 | `lib/esp_codec_dev/LICENSE`; source hashes in `SOURCE.json` |

The Nunito notice matches the bundled font metadata. The license copy is from the [font project's OFL.txt](https://github.com/googlefonts/nunito/blob/main/OFL.txt).

PlatformIO resolves the firmware dependencies pinned in `platformio.ini`. Their licenses remain with those packages. The original crawler export's provenance and asset hashes are in `host/ui/robot/README.md` and `manifest.json`.
