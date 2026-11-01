"""Read immutable release metadata packaged with the container image."""

import re
from pathlib import Path

VERSION_FILE = Path(__file__).with_name("_image_version.txt")


def image_version(path: Path = VERSION_FILE) -> str | None:
    if not path.is_file():
        return None
    value = path.read_text(encoding="ascii").strip()
    if not re.fullmatch(r"[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,127}", value):
        raise ValueError("Invalid image version metadata.")
    return value
