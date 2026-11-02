"""Build clean installed/portable payloads and reproducible distribution checksums."""

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from img2tex import __version__
from img2tex.model_setup import MODEL_FILES, MODEL_ID, MODEL_REVISION, WEIGHT_SHA256, WEIGHT_SIZE

ROOT = Path(__file__).resolve().parents[1]
MODEL_NAMES = MODEL_FILES + ["README.md", "LICENSE", "img2tex-model.json"]


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_runtime(runtime):
    for relative in ["Img2Tex.exe", "_internal/python312.dll", "_internal/latex2mathml/unimathsymbols.txt"]:
        if not (runtime / relative).is_file():
            raise ValueError(f"Incomplete frozen runtime: {relative}")
    model = runtime / "models" / "xiaomi-ocr-0"
    for name in MODEL_NAMES:
        if not (model / name).is_file():
            raise ValueError(f"Incomplete bundled model: {name}")
    weights = model / "model.safetensors"
    if weights.stat().st_size != WEIGHT_SIZE or sha256(weights) != WEIGHT_SHA256:
        raise ValueError("Bundled model integrity check failed")


def stage_runtime(runtime: Path, target: Path, *, portable: bool):
    runtime, target = Path(runtime), Path(target)
    target.mkdir(parents=True, exist_ok=False)
    shutil.copy2(runtime / "Img2Tex.exe", target / "Img2Tex.exe")
    shutil.copytree(runtime / "_internal", target / "_internal",
                    ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.log"))
    model_target = target / "models" / "xiaomi-ocr-0"
    model_target.mkdir(parents=True)
    for name in MODEL_NAMES:
        shutil.copy2(runtime / "models" / "xiaomi-ocr-0" / name, model_target / name)
    guide = (ROOT / "packaging/ReadMe.txt").read_text(encoding="utf8").replace("@VERSION@", __version__)
    (target / "ReadMe.txt").write_text(guide, encoding="utf8")
    shutil.copy2(ROOT / "packaging/THIRD_PARTY_NOTICES.txt", target)
    shutil.copytree(ROOT / "packaging/licenses", target / "licenses")
    shutil.copy2(ROOT / "docs/export-notices.md", target)
    if portable:
        (target / "portable.flag").write_text("Img2Tex portable mode\n", encoding="utf8")
        (target / "data").mkdir()
        (target / "data/ReadMe.txt").write_text("此目录在运行时保存本机数据，发行前请勿加入历史或日志。\n", encoding="utf8")
    manifest = {
        "product": "Img2Tex", "version": __version__, "edition": "portable" if portable else "installed",
        "model_id": MODEL_ID, "model_revision": MODEL_REVISION, "model_sha256": WEIGHT_SHA256,
        "files": {p.relative_to(target).as_posix(): sha256(p) for p in sorted(target.rglob("*")) if p.is_file()},
    }
    (target / "build-manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf8")


def create_portable_zip(folder: Path, output: Path):
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(folder.parent).as_posix())


def create_release_directory(output: Path):
    try:
        output.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise FileExistsError("Choose a new output directory; previous release files are preserved.") from exc


def compile_installer(compiler, payload, output):
    command = [str(compiler), f"/DAppVersion={__version__}", f"/DPayloadDir={payload}",
               f"/DReleaseDir={output}", str(ROOT / "packaging/windows/Img2Tex.iss")]
    result = subprocess.run(command, check=False, capture_output=True, text=True, encoding="utf8", errors="replace")
    (ROOT / "build/installer-compile.log").write_text(result.stdout + result.stderr, encoding="utf8")
    if result.returncode and "DiskSpanning" in result.stdout + result.stderr:
        result = subprocess.run(command[:1] + ["/DSpan=yes"] + command[1:], check=False, capture_output=True,
                                text=True, encoding="utf8", errors="replace")
        (ROOT / "build/installer-compile.log").write_text(result.stdout + result.stderr, encoding="utf8")
    if result.returncode:
        raise RuntimeError("Installer compilation failed; see build/installer-compile.log")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, default=ROOT / "dist/Img2Tex")
    parser.add_argument("--compiler", type=Path, default=ROOT / "build/tools/InnoSetup/ISCC.exe")
    parser.add_argument("--output", type=Path, default=ROOT / "release" / __version__)
    args = parser.parse_args()
    create_release_directory(args.output)
    validate_runtime(args.runtime)
    if not args.compiler.is_file():
        raise FileNotFoundError("Inno Setup compiler is missing")
    stage_parent = ROOT / "build/release"
    stage_parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f"{__version__}-", dir=stage_parent))
    installer_payload = stage / "installer"
    portable_payload = stage / "portable/Img2Tex"
    for folder, portable in [(installer_payload, False), (portable_payload, True)]:
        stage_runtime(args.runtime, folder, portable=portable)
        print(f"Staged clean payload: {folder}", flush=True)
    portable_zip = args.output / f"Img2Tex-{__version__}-Windows-x64-Portable.zip"
    with ThreadPoolExecutor(max_workers=2) as executor:
        installer_job = executor.submit(compile_installer, args.compiler.resolve(), installer_payload, args.output.resolve())
        portable_job = executor.submit(create_portable_zip, portable_payload, portable_zip)
        installer_job.result()
        portable_job.result()
    with zipfile.ZipFile(portable_zip) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError(f"ZIP integrity failure: {bad}")
    bins = list(args.output.glob("*-Setup-*.bin"))
    if bins:
        with zipfile.ZipFile(args.output / f"Img2Tex-{__version__}-Windows-x64-Setup.zip", "w", allowZip64=True) as archive:
            for path in sorted(bins + list(args.output.glob("*-Setup.exe"))):
                archive.write(path, path.name)
    artifacts = sorted(p for p in args.output.iterdir() if p.suffix.lower() in {".exe", ".zip", ".bin"})
    (args.output / "SHA256SUMS.txt").write_text(
        "".join(f"{sha256(p)}  {p.name}\n" for p in artifacts), encoding="ascii")
    build = {"version": __version__, "built_utc": datetime.now(UTC).isoformat(), "stage": str(stage),
             "artifacts": [{"name": p.name, "bytes": p.stat().st_size, "sha256": sha256(p)} for p in artifacts]}
    (ROOT / "build/release-build.json").write_text(json.dumps(build, indent=2), encoding="utf8")
    print(json.dumps(build, indent=2), flush=True)


if __name__ == "__main__":
    main()
