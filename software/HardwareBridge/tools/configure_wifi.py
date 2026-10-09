"""Create private build settings without putting Wi-Fi credentials in Git."""
import getpass
import json
from pathlib import Path


def main():
    ssid = input('Wi-Fi name: ').strip()
    if not ssid:
        raise SystemExit('Wi-Fi name cannot be empty')
    password = getpass.getpass('Wi-Fi password (hidden; empty for open network): ')
    target = Path(__file__).resolve().parents[1] / 'wifi.local.json'
    target.write_text(json.dumps(dict(ssid=ssid, password=password), indent=2) + '\n', encoding='utf-8')
    print('Saved ignored wifi.local.json. Build the firmware to apply these settings.')


if __name__ == '__main__':
    main()
