"""Configure a local owner password without printing or committing credentials."""

from getpass import getpass
from pathlib import Path

from argon2 import PasswordHasher

root = Path(__file__).resolve().parents[1]
private = root / "private"
private.mkdir(mode=0o700, exist_ok=True)
target = private / "owner.hash"
if target.exists():
    raise SystemExit(
        "Owner hash already exists. Choose a separate file to rotate credentials."
    )
password = getpass("Choose an owner passphrase (at least 16 characters): ")
if len(password) < 16 or password != getpass("Confirm passphrase: "):
    raise SystemExit("Passphrase is too short or confirmation does not match.")
with target.open("x") as stream:
    stream.write(PasswordHasher().hash(password) + "\n")
target.chmod(0o600)
print(
    "Local owner configured. Export AUTH_PASSWORD_HASH_FILE=private/owner.hash before starting."
)
