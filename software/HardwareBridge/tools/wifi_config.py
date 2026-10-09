"""Generate an ignored Wi-Fi header from local settings or environment variables."""
import json
import os
from pathlib import Path

Import("env")
root = Path(env.subst("$PROJECT_DIR"))
if 'CYOBOT_WIFI_SSID' in os.environ or 'CYOBOT_WIFI_PASSWORD' in os.environ:
    wifi = dict(ssid=os.environ.get('CYOBOT_WIFI_SSID'), password=os.environ.get('CYOBOT_WIFI_PASSWORD'))
else:
    private = root / 'wifi.local.json'
    if not private.exists():
        raise RuntimeError('Configure Wi-Fi first: python tools/configure_wifi.py')
    wifi = json.loads(private.read_text(encoding='utf-8-sig'))
if (not isinstance(wifi, dict) or not isinstance(wifi.get('ssid'), str) or not wifi['ssid']
        or not isinstance(wifi.get('password'), str)):
    raise ValueError('Wi-Fi requires a non-empty ssid and a password string (empty for an open network)')
target = root / "include/wifi_config.h"
target.parent.mkdir(exist_ok=True)
content = "#pragma once\n#define WIFI_SSID %s\n#define WIFI_PASSWORD %s\n" % (
    json.dumps(wifi["ssid"], ensure_ascii=True), json.dumps(wifi["password"], ensure_ascii=True))
if not target.exists() or target.read_text() != content:
    target.write_text(content)
