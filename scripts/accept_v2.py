"""Verify an actual portable archive in a relocated, isolated offline test folder."""

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import zipfile
from pathlib import Path

from img2tex import __version__
from img2tex.model_setup import WEIGHT_SHA256

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    parent = ROOT / "build/v2-acceptance"
    parent.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix=args.archive.stem + "-", dir=parent))
    original = workspace / "original"
    with zipfile.ZipFile(args.archive) as archive:
        if archive.testzip() is not None:
            raise ValueError("Archive CRC failed")
        for entry in archive.infolist():
            if not (original / entry.filename).resolve().is_relative_to(original.resolve()):
                raise ValueError("Unsafe archive path")
        archive.extractall(original)
    runtime = workspace / "移动 便携目录" / "Img2Tex"
    runtime.parent.mkdir()
    (original / "Img2Tex").rename(runtime)
    metadata = json.loads((runtime / "img2tex-runtime.json").read_text(encoding="utf8"))
    manifest = json.loads((runtime / "build-manifest.json").read_text(encoding="utf8"))
    assert manifest["version"] == __version__
    digest = hashlib.sha256()
    with (runtime / "models/xiaomi-ocr-0/model.safetensors").open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    assert digest.hexdigest() == WEIGHT_SHA256
    dlls = [p.name.lower() for p in (runtime / "_internal/torch/lib").glob("*.dll")]
    if metadata["edition"] == "cpuonly":
        prefixes = ("cublas", "cudnn", "cufft", "cusolver", "cusparse", "curand", "nvrtc", "nvjitlink")
        assert not any("cuda" in name or name.startswith(prefixes) for name in dlls)
        assert metadata["cuda_runtime"] is None
    else:
        assert "torch_cuda.dll" in dlls
    assert not list((runtime / "_internal/PySide6").rglob("*.debug.*"))
    assert not list((runtime / "data").glob("*.sqlite3"))
    environment = os.environ.copy()
    environment.update(PATH=os.pathsep.join([os.path.join(os.environ["SystemRoot"], "System32"),
                                             os.environ["SystemRoot"]]),
                       PYTHONPATH="", PYTHONNOUSERSITE="1", HF_HUB_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
    results = []
    devices = ["cpu"] if metadata["edition"] == "cpuonly" else ["cpu", "cuda"]
    for device in devices:
        output = workspace / f"{device}.json"
        env = environment.copy()
        if device == "cpu":
            env["CUDA_VISIBLE_DEVICES"] = "-1"
        process = subprocess.run([str(runtime / "Img2Tex.exe"), "--smoke",
                                  str(ROOT / "tests/fixtures/energy.png"), "--device", device,
                                  "--max-tokens", "96", "--output", str(output)],
                                 check=False, env=env, cwd=workspace, capture_output=True, timeout=300)
        assert process.returncode == 0, process.stderr.decode(errors="replace")
        result = json.loads(output.read_text(encoding="utf8"))
        assert result["device"] == device, result
        assert "E" in result["latex_normalized"] and "2" in result["latex_normalized"]
        assert result["initialization"]["warmup_seconds"] > 0
        results.append(result)
    report = {"archive": str(args.archive.resolve()), "runtime": str(runtime), "metadata": metadata,
              "archive_crc": "passed", "model_sha256": digest.hexdigest(), "relocated": True,
              "system_only_path": True, "HF_HUB_OFFLINE": True, "smoke_results": results,
              "no_driver_machine": "not tested; host has NVIDIA driver"}
    report_path = workspace / "acceptance.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
    print(report_path)


if __name__ == "__main__":
    main()
