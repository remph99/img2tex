"""One authority for installed and portable application locations."""

import os
import sys
import tempfile
from pathlib import Path


def application_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def is_portable() -> bool:
    return (application_dir() / "portable.flag").is_file()


def app_data_dir() -> Path:
    if is_portable():
        return application_dir() / "data"
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share"))) / "Img2Tex"


def configure_runtime() -> Path:
    data = app_data_dir()
    for folder in (data, data / "logs", data / "cache"):
        folder.mkdir(parents=True, exist_ok=True)
    # Probe writes as well as directory existence, so read-only media fail here.
    with tempfile.TemporaryFile(dir=data) as probe:
        probe.write(b"")
    os.environ["HF_HOME"] = str(data / "cache" / "huggingface")
    os.environ["TORCH_HOME"] = str(data / "cache" / "torch")
    os.environ["XDG_CACHE_HOME"] = str(data / "cache")
    return data


def resolve_model_path(value: str) -> str:
    if not value.strip():
        return ""
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = application_dir() / path
    return str(path)


def serialize_model_path(value: str) -> str:
    if not value.strip():
        return ""
    path = Path(resolve_model_path(value)).resolve()
    try:
        return path.relative_to(application_dir().resolve()).as_posix()
    except ValueError:
        return str(path)
