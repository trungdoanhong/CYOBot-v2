"""Install the Portal on an already-flashed CYOBot, with backups and hash checks.

Requires mpremote. Does not erase/flash firmware or start servo movement.
Example: python tools/deploy_portal.py --port COM6 --backup-dir <directory>
"""

import argparse
import hashlib
from pathlib import Path

from mpremote.transport_serial import SerialTransport


ROOT = Path(__file__).resolve().parents[1]


def deploy(port, backup_dir):
    backup_dir.mkdir(parents=True, exist_ok=True)
    transport = SerialTransport(port)
    try:
        transport.enter_raw_repl(soft_reset=False)
        print(transport.exec("import os,sys; print(os.uname()); print('SD:',os.statvfs('/sdcard'))").decode(), flush=True)
        # The initial firmware boot mounts the card. Never format it here.
        sd_files = sorted(path for path in (ROOT / "sd").rglob("*")
                          if path.is_file() and "__pycache__" not in path.parts
                          and path.suffix != ".pyc")
        files = [(path, "/sdcard/" + path.relative_to(ROOT / "sd").as_posix()) for path in sd_files]
        # Install startup files last, after their dependencies and assets.
        files += [(ROOT / "pyboard" / name, "/" + name)
                  for name in ("webrepl_cfg.py", "state", "main-server.py", "main.py", "boot.py")]
        made_dirs = {"/", "/sdcard"}
        written = 0
        verified = 0
        for index, (source, target) in enumerate(files, 1):
            exists = transport.fs_exists(target)
            # Preserve an existing owner's calibration and Wi-Fi setup.
            if exists and target.startswith("/sdcard/config/"):
                print("PRESERVED", target, flush=True)
                continue
            data = source.read_bytes()
            expected = hashlib.sha256(data).digest()
            if exists and transport.fs_hashfile(target, "sha256", chunk_size=4096) == expected:
                verified += 1
                print("VERIFIED", target, flush=True)
                continue
            if exists:
                saved = backup_dir / target.lstrip("/")
                saved.parent.mkdir(parents=True, exist_ok=True)
                if not saved.exists():
                    saved.write_bytes(transport.fs_readfile(target, chunk_size=4096))
            parent = target.rsplit("/", 1)[0] or "/"
            current = ""
            for part in parent.strip("/").split("/"):
                if not part:
                    continue
                current += "/" + part
                if current not in made_dirs:
                    if not transport.fs_exists(current):
                        transport.fs_mkdir(current)
                    made_dirs.add(current)
            staged = target + ".upload"
            print("COPY {}/{} {} ({} bytes)".format(index, len(files), target, len(data)), flush=True)
            transport.fs_writefile(staged, data, chunk_size=4096)
            actual = transport.fs_hashfile(staged, "sha256", chunk_size=4096)
            if actual != expected:
                raise RuntimeError("SHA256 mismatch for " + staged)
            # FAT does not support replacing an existing destination via rename.
            if exists:
                transport.fs_rmfile(target)
            transport.exec("os.rename({!r}, {!r}); os.sync()".format(staged, target))
            written += 1
            verified += 1
        # Prevent an older SD-card deployment from overriding the installed main.py.
        pending = "/sdcard/main.py"
        if transport.fs_exists(pending):
            saved = backup_dir / "pending-sdcard-main.py"
            if saved.exists():
                raise RuntimeError("Pending-program backup already exists: " + str(saved))
            saved.write_bytes(transport.fs_readfile(pending, chunk_size=4096))
            transport.fs_rmfile(pending)
        print("DONE: {} files written, {} SHA256 checks passed".format(written, verified), flush=True)
        print("Files installed. Hard-reset the board to start the Portal.", flush=True)
    finally:
        transport.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--backup-dir", required=True, type=Path)
    args = parser.parse_args()
    deploy(args.port, args.backup_dir)
