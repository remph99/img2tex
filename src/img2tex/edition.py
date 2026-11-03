"""Distribution identity, read without importing the inference runtime."""

import json

from . import paths


def cpu_only() -> bool:
    metadata = paths.application_dir() / "img2tex-runtime.json"
    if not metadata.is_file():
        return False
    return json.loads(metadata.read_text(encoding="utf8"))["edition"] == "cpuonly"


def edition_label() -> str:
    return "CPU Only" if cpu_only() else "完整版"
