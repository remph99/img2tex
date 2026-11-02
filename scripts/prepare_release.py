"""Generate build metadata and the original x-squared application icon."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

from img2tex import __version__

ROOT = Path(__file__).resolve().parents[1]


def main():
    icon_path = ROOT / "src/img2tex/assets/app.ico"
    canvas = Image.new("RGBA", (256, 256))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((0, 0, 255, 255), radius=64, fill="#6d5dfc")
    font = ImageFont.truetype("C:/Windows/Fonts/cambria.ttc", 155)
    bounds = draw.textbbox((0, 0), "x²", font=font)
    position = ((256 - bounds[2] + bounds[0]) / 2 - bounds[0],
                (256 - bounds[3] + bounds[1]) / 2 - bounds[1] - 4)
    draw.text(position, "x²", font=font, fill="white")
    canvas.save(icon_path, sizes=[(size, size) for size in (16, 24, 32, 48, 64, 128, 256)])
    version = tuple(int(part) for part in __version__.split(".")) + (0,)
    strings = {
        "CompanyName": "Img2Tex", "FileDescription": "Img2Tex Local Formula OCR",
        "FileVersion": __version__, "InternalName": "Img2Tex", "OriginalFilename": "Img2Tex.exe",
        "ProductName": "Img2Tex", "ProductVersion": __version__,
    }
    info = VSVersionInfo(
        ffi=FixedFileInfo(filevers=version, prodvers=version, mask=0x3F, flags=0,
                          OS=0x40004, fileType=1, subtype=0, date=(0, 0)),
        kids=[StringFileInfo([StringTable("040904B0", [StringStruct(k, v) for k, v in strings.items()])]),
              VarFileInfo([VarStruct("Translation", [0x409, 1200])])],
    )
    output = ROOT / "build/version_info.txt"
    output.parent.mkdir(exist_ok=True)
    output.write_text(str(info), encoding="utf8")
    print(f"Prepared Img2Tex {__version__}: icon and version metadata")


if __name__ == "__main__":
    main()
