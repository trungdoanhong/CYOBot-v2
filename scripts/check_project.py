"""Validate a portable checkout without accessing robot hardware."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / 'software/HardwareBridge'


def main():
    model = BRIDGE / 'host/ui/robot'
    manifest = json.loads((model / 'manifest.json').read_text(encoding='utf-8'))
    for entry in manifest['files']:
        path = model / entry['path']
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            raise SystemExit(f'Missing or changed model asset: {entry["path"]}')
    print(f'Model manifest: {len(manifest["files"])} files verified', flush=True)
    for folder in (BRIDGE, ROOT / 'software/MicroPython'):
        subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests'], cwd=folder, check=True)
    node = shutil.which('node')
    if node:
        for name in ('test_workspace.cjs', 'test_routines.cjs', 'test_audio_worklet.cjs'):
            subprocess.run([node, str(BRIDGE / 'tests' / name)], cwd=BRIDGE, check=True)
    else:
        print('SKIP JavaScript tests: install Node.js to run them (not needed for Studio).')


if __name__ == '__main__':
    main()
