"""Explicit preparation and validation of the local model, separate from OCR."""

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

MODEL_ID = "xiaomi-research/Xiaomi-OCR-0"
MODEL_REVISION = "bbd8cf8d21f256b3644b44cb860f3a7cecb93c30"
FORMULA_PROMPT = "Identify the formula in the image and represent it using LATEX format."
WEIGHT_SIZE = 1746937856
WEIGHT_SHA256 = "d4551e9f6127ac9e35cff7b4f7a72a90410e03e6c8676a36f0e2b7eaeb5d5348"
MODEL_FILES = [
    "config.json", "model.safetensors", "processor_config.json", "tokenizer.json",
    "tokenizer_config.json", "chat_template.jinja",
]


def default_model_dir() -> Path:
    portable = (Path(sys.executable).parent if getattr(sys, "frozen", False)
                else Path(__file__).resolve().parents[2]) / "models" / "xiaomi-ocr-0"
    if (portable / "config.json").is_file():
        return portable
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share")) / "Img2Tex" / "models" / "xiaomi-ocr-0"


def device_options(device: str, *, cuda_available: bool) -> tuple[str, str]:
    if device == "cpu":
        return "cpu", "float32"
    if device != "cuda":
        raise ValueError("推理设备必须为 cpu 或 cuda。")
    if not cuda_available:
        raise ValueError("CUDA 当前不可用，请安装支持 CUDA 的 PyTorch/显卡驱动，或选择 CPU。")
    return "cuda", "float16"


def model_revision(path: Path) -> str:
    """Record our downloader's release identity; user-supplied folders remain explicit."""
    try:
        manifest = json.loads((Path(path) / "img2tex-model.json").read_text(encoding="utf8"))
    except (OSError, ValueError):
        return "local-unverified"
    if (manifest.get("repo_id") == MODEL_ID and manifest.get("revision") == MODEL_REVISION
            and manifest.get("weights_sha256") == WEIGHT_SHA256):
        return MODEL_REVISION
    return "local-unverified"


def check_model_directory(path: Path) -> Path:
    path = Path(path).expanduser().resolve()
    config_path = path / "config.json"
    if not config_path.is_file():
        raise ValueError(f"模型未准备好，缺少 config.json：{path}。请先下载或选择模型目录。")
    try:
        config = json.loads(config_path.read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取模型 config.json：{exc}") from exc
    if config.get("model_type") != "qwen3_5":
        raise ValueError("请选择 Xiaomi-OCR-0 的 Qwen3.5 模型目录。")
    missing = [name for name in MODEL_FILES if not (path / name).is_file() or not (path / name).stat().st_size]
    if missing:
        raise ValueError("模型文件不完整，缺少：" + ", ".join(missing))
    return path


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download_weight_file(url: str, destination: Path, size: int, sha256: str, *, chunk_size=16 * 1024 * 1024):
    """Bounded range requests survive proxies that interrupt long checkpoint responses."""
    destination = Path(destination)
    if destination.is_file() and destination.stat().st_size == size and _file_sha256(destination) == sha256:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    position = partial.stat().st_size if partial.exists() else 0
    if position > size:
        raise ValueError(f"模型续传文件大小异常，请移走后重试：{partial}")
    attempts = 0
    resolved_url = None
    while position < size:
        end = min(size, position + chunk_size) - 1
        separator = "&" if "?" in url else "?"
        request = urllib.request.Request(resolved_url or url + separator + f"img2tex_range={position}", headers={
            "Range": f"bytes={position}-{end}", "Accept-Encoding": "identity",
        })
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                expected_range = f"bytes {position}-{end}/{size}"
                if response.status != 206 or response.headers.get("Content-Range") != expected_range:
                    raise ValueError("模型下载服务器返回了错误的字节范围，续传已停止。")
                block = response.read(chunk_size + 1)
                # Reuse the CDN redirect while valid, avoiding a Hub resolve per segment.
                resolved_url = response.geturl()
            if len(block) != end - position + 1:
                raise OSError("模型下载分段不完整。")
            with partial.open("ab") as stream:
                stream.write(block)
            position += len(block)
            attempts = 0
            print(f"模型权重 {position / size:.1%} ({position // 1048576}/{size // 1048576} MiB)", flush=True)
        except (OSError, urllib.error.URLError) as exc:
            if resolved_url and isinstance(exc, urllib.error.HTTPError) and exc.code in (401, 403):
                resolved_url = None
                continue
            attempts += 1
            print(f"下载连接中断，重试 {attempts}/6（{type(exc).__name__}）", flush=True)
            if attempts >= 6:
                raise RuntimeError(f"模型下载中断，已保留续传进度。请稍后重试：{exc}") from exc
            time.sleep(min(2 ** attempts, 30))
    if _file_sha256(partial) != sha256:
        partial.replace(partial.with_name(partial.name + f".corrupt-{time.time_ns()}"))
        raise ValueError("模型 SHA-256 校验失败，损坏文件已隔离，请重新下载。")
    partial.replace(destination)


def download_model(path: Path | None = None) -> Path:
    # Large checkpoint responses may take longer than the Hub's 10s default.
    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "120")
    from huggingface_hub import snapshot_download

    path = Path(path or default_model_dir()).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=MODEL_ID, revision=MODEL_REVISION, local_dir=path,
        allow_patterns=[name for name in MODEL_FILES if name != "model.safetensors"] + ["README.md"], max_workers=2,
    )
    download_weight_file(
        f"https://huggingface.co/{MODEL_ID}/resolve/{MODEL_REVISION}/model.safetensors?download=true",
        path / "model.safetensors", WEIGHT_SIZE, WEIGHT_SHA256,
    )
    check_model_directory(path)
    (path / "img2tex-model.json").write_text(
        json.dumps({"repo_id": MODEL_ID, "revision": MODEL_REVISION, "weights_sha256": WEIGHT_SHA256}, indent=2),
        encoding="utf8",
    )
    license_text = Path(__file__).parent / "assets" / "notices" / "Xiaomi-OCR-0-LICENSE.txt"
    (path / "LICENSE").write_text(license_text.read_text(encoding="utf8"), encoding="utf8")
    return path
