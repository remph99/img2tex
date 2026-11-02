"""One image normalization path for file, clipboard and screenshot input."""

import hashlib
import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError


@dataclass(frozen=True)
class PreparedImage:
    original_png: bytes
    model_png: bytes
    width: int
    height: int
    sha256: str
    model_sha256: str


def _png(image: Image.Image) -> bytes:
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def prepare_image(data: bytes) -> PreparedImage:
    if not data or len(data) > 50 * 1024 * 1024:
        raise ValueError("图片为空或超过 50 MiB，请选择较小的图片。")
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.width * source.height > 40_000_000:
                raise ValueError("图片像素过大，请先裁剪公式区域。")
            image = ImageOps.exif_transpose(source).convert("RGBA")
        white = Image.new("RGBA", image.size, "white")
        image = Image.alpha_composite(white, image).convert("RGB")
        width, height = image.size
        original = _png(image)
        image.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
        model = _png(image)
        return PreparedImage(
            original, model, width, height, hashlib.sha256(original).hexdigest(), hashlib.sha256(model).hexdigest(),
        )
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError(f"无法解码图片：{exc}") from exc
