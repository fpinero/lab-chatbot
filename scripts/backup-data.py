"""Create authenticated encrypted offline snapshots and restore into an empty directory only."""

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

MAGIC = b"LABCHATBOT-BACKUP-1\n"
CHUNK = 1024 * 1024
MAXIMUM = 12 * 1024**3


def key_bytes(path):
    if path.is_symlink() or path.stat().st_mode & 0o077:
        raise ValueError("Backup key must be a private regular file with mode 0600.")
    value = path.read_bytes()
    if len(value) != 32:
        raise ValueError("Backup encryption requires a 32-byte random key file.")
    return value


def checksum(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(CHUNK):
            digest.update(block)
    return digest.hexdigest()


def encrypt(source, target, key):
    nonce = os.urandom(12)
    header = MAGIC + nonce
    cipher = Cipher(algorithms.AES256(key), modes.GCM(nonce)).encryptor()
    cipher.authenticate_additional_data(header)
    with source.open("rb") as incoming, target.open("xb") as outgoing:
        os.chmod(target, 0o600)
        outgoing.write(header)
        while block := incoming.read(CHUNK):
            outgoing.write(cipher.update(block))
        outgoing.write(cipher.finalize())
        outgoing.write(cipher.tag)


def decrypt(source, target, key):
    size = source.stat().st_size
    if not len(MAGIC) + 28 <= size <= MAXIMUM:
        raise ValueError("Invalid encrypted backup size.")
    with source.open("rb") as incoming:
        header = incoming.read(len(MAGIC) + 12)
        if not header.startswith(MAGIC):
            raise ValueError("Unknown backup format.")
        incoming.seek(-16, 2)
        tag = incoming.read(16)
        incoming.seek(len(header))
        cipher = Cipher(
            algorithms.AES256(key), modes.GCM(header[-12:], tag)
        ).decryptor()
        cipher.authenticate_additional_data(header)
        remaining = size - len(header) - 16
        with target.open("xb") as outgoing:
            while remaining:
                block = incoming.read(min(CHUNK, remaining))
                if not block:
                    raise ValueError("Truncated encrypted backup.")
                outgoing.write(cipher.update(block))
                remaining -= len(block)
            outgoing.write(cipher.finalize())


def backup(data, output, key, offline):
    data = data.resolve()
    output = output.parent.resolve() / output.name
    if not offline:
        raise ValueError(
            "Stop every application writer and explicitly acknowledge --offline."
        )
    if output.is_relative_to(data) or not (data / "lab.db").is_file():
        raise ValueError(
            "Use a backup destination outside an existing application data directory."
        )
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if output.exists() or output.is_symlink():
        raise ValueError("Backups never overwrite existing files.")
    with tempfile.TemporaryDirectory(
        prefix="lab-backup-", dir=output.parent
    ) as temporary:
        staging = Path(temporary) / "data"
        staging.mkdir(mode=0o700)
        with (
            sqlite3.connect(f"file:{data / 'lab.db'}?mode=ro", uri=True) as source,
            sqlite3.connect(staging / "lab.db") as target,
        ):
            source.backup(target)
            if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("SQLite integrity check failed.")
        for path in data.rglob("*"):
            relative = path.relative_to(data)
            if path.is_symlink():
                raise ValueError("Data snapshots reject symlinks.")
            if relative.parts[0] in {
                "lab.db",
                "lab.db-wal",
                "lab.db-shm",
                "backup-manifest.json",
            }:
                continue
            destination = staging / relative
            if path.is_dir():
                destination.mkdir(parents=True, exist_ok=True, mode=0o700)
            elif path.is_file():
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                shutil.copyfile(path, destination)
                os.chmod(destination, 0o600)
        files = {
            str(p.relative_to(staging)): checksum(p)
            for p in staging.rglob("*")
            if p.is_file()
        }
        (staging / "backup-manifest.json").write_text(
            json.dumps({"version": 1, "files": files})
        )
        archive = Path(temporary) / "snapshot.tar.gz"
        with tarfile.open(archive, "w:gz") as handle:
            handle.add(staging, arcname="data", recursive=True)
        if archive.stat().st_size > MAXIMUM - 1024:
            raise ValueError("Backup exceeds the bounded archive limit.")
        candidate = Path(temporary) / "snapshot.encrypted"
        encrypt(archive, candidate, key)
        os.link(candidate, output)
    return {"encrypted": True, "files": len(files), "bytes": output.stat().st_size}


def restore(archive, target, key):
    target = target.parent.resolve() / target.name
    if target.exists() or target.is_symlink():
        raise ValueError(
            "Restore only to a new directory; existing data is never replaced."
        )
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(
        prefix="lab-restore-", dir=target.parent
    ) as temporary:
        incoming = Path(temporary) / "snapshot.tar.gz"
        decrypt(archive, incoming, key)
        total = 0
        with tarfile.open(incoming, "r:gz") as handle:
            members = handle.getmembers()
            for member in members:
                path = PurePosixPath(member.name)
                total += member.size
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or not path.parts
                    or path.parts[0] != "data"
                    or not (member.isdir() or member.isfile())
                    or total > MAXIMUM
                ):
                    raise ValueError("Unsafe or oversized backup member.")
            handle.extractall(temporary, members=members, filter="data")
        restored = Path(temporary) / "data"
        manifest = json.loads((restored / "backup-manifest.json").read_text())
        actual = {
            str(p.relative_to(restored)): checksum(p)
            for p in restored.rglob("*")
            if p.is_file() and p != restored / "backup-manifest.json"
        }
        if manifest.get("version") != 1 or actual != manifest["files"]:
            raise ValueError(
                "Restored file checksums do not match the authenticated manifest."
            )
        with sqlite3.connect(f"file:{restored / 'lab.db'}?mode=ro", uri=True) as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Restored SQLite database is not valid.")
        (restored / "backup-manifest.json").unlink()
        for path in restored.rglob("*"):
            os.chmod(path, 0o700 if path.is_dir() else 0o600)
        os.chmod(restored, 0o700)
        restored.rename(target)
    return {"restored": True, "files": len(actual), "overwrote_existing_data": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["backup", "restore"])
    parser.add_argument("--data-dir", type=Path, default=Path("/data"))
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--target", type=Path)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        print(
            json.dumps(
                {
                    "phase": args.command,
                    "executed": False,
                    "requires_offline_writers": True,
                    "restore_overwrites": False,
                }
            )
        )
        return
    key = key_bytes(args.key_file)
    if args.command == "backup":
        result = backup(args.data_dir, args.archive, key, args.offline)
    else:
        if not args.target:
            raise ValueError("Restore requires an explicit new --target directory.")
        result = restore(args.archive, args.target, key)
    print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        EOFError,
        tarfile.TarError,
        sqlite3.DatabaseError,
        InvalidTag,
    ):
        raise SystemExit(
            "Backup/restore failed safely. Check offline state, paths, permissions, key and archive integrity; no existing data was replaced."
        ) from None
