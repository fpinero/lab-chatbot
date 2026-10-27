"""Prepare private deployment files locally; never contact Kubernetes or print credentials."""

import argparse
import os
from pathlib import Path

from argon2 import Type, extract_parameters
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def create_private(path, content):
    if path.exists():
        if path.is_symlink() or path.stat().st_mode & 0o077:
            raise ValueError(
                "Existing private files must be regular files with mode 0600."
            )
        return False
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(content)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if not args.write:
        print(
            "Plan: prepare ignored k8s/.env and private/deploy credential files locally. No cluster writes."
        )
        return
    values = dotenv_values(ROOT / ".env.local", interpolate=False)
    key_path = values.get("OPENROUTER_API_KEY_FILE")
    key = (
        (ROOT / key_path).read_text().strip()
        if key_path
        else values.get("OPENROUTER_API_KEY", "")
    )
    hash_path = values.get("AUTH_PASSWORD_HASH_FILE") or "private/owner.hash"
    owner_hash = (ROOT / hash_path).read_text().strip()
    parameters = extract_parameters(owner_hash)
    if (
        not key
        or parameters.type != Type.ID
        or parameters.memory_cost < 65536
        or parameters.time_cost < 3
    ):
        raise ValueError(
            "Configure valid private provider and owner credentials first."
        )
    directory = ROOT / "private/deploy"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.is_symlink() or directory.stat().st_mode & 0o077:
        raise ValueError("The deployment credential directory must have mode 0700.")
    create_private(directory / "openrouter.key", key.encode() + b"\n")
    create_private(directory / "owner.hash", owner_hash.encode() + b"\n")
    create_private(directory / "backup.key", os.urandom(32))
    environment = (ROOT / "k8s/.env.example").read_bytes()
    environment = environment.replace(
        b"KUBECTL=kubectl", b"KUBECTL=private/tools/kubectl"
    )
    environment = environment.replace(
        b"KUBECONFORM=kubeconform", b"KUBECONFORM=private/tools/kubeconform"
    )
    create_private(ROOT / "k8s/.env", environment)
    print(
        "Private deployment files prepared with restrictive permissions. Existing files preserved. No credentials printed or uploaded."
    )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError):
        raise SystemExit(
            "Private deployment setup failed; inspect file presence and permissions without printing contents."
        ) from None
