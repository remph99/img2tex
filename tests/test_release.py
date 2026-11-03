import zipfile
from pathlib import Path

from scripts.release import create_portable_zip, stage_runtime


def sample_runtime(tmp_path):
    from img2tex.model_setup import MODEL_FILES
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "Img2Tex.exe").write_bytes(b"executable")
    (runtime / "_internal").mkdir()
    (runtime / "_internal" / "python312.dll").write_bytes(b"runtime")
    model = runtime / "models" / "xiaomi-ocr-0"
    model.mkdir(parents=True)
    for name in MODEL_FILES + ["README.md", "LICENSE", "img2tex-model.json"]:
        (model / name).write_text("model data", encoding="utf8")
    (runtime / "data").mkdir()
    (runtime / "data" / "history.sqlite3").write_bytes(b"private history")
    (runtime / "developer.log").write_text("private", encoding="utf8")
    (model / ".part").write_bytes(b"unfinished download")
    return runtime


def test_portable_stage_is_clean_and_contains_complete_runtime(tmp_path):
    runtime = sample_runtime(tmp_path)
    target = tmp_path / "portable" / "Img2Tex"
    stage_runtime(runtime, target, portable=True)
    assert (target / "portable.flag").is_file()
    assert (target / "_internal" / "python312.dll").is_file()
    assert (target / "models" / "xiaomi-ocr-0" / "model.safetensors").is_file()
    assert not list(target.rglob("*.sqlite3"))
    assert not list(target.rglob("*.log"))
    assert not list(target.rglob("*.part"))
    assert (target / "ReadMe.txt").is_file()


def test_installer_stage_never_enables_portable_mode(tmp_path):
    runtime = sample_runtime(tmp_path)
    (runtime / "portable.flag").touch()
    target = tmp_path / "installed"
    stage_runtime(runtime, target, portable=False)
    assert not (target / "portable.flag").exists()
    assert not (target / "data").exists()


def test_cpuonly_identity_survives_staging_and_is_recorded_in_manifest(tmp_path):
    import json
    runtime = sample_runtime(tmp_path)
    metadata = {"edition": "cpuonly", "torch": "2.14.0+cpu", "cuda_runtime": None}
    (runtime / "img2tex-runtime.json").write_text(json.dumps(metadata), encoding="utf8")
    target = tmp_path / "cpuonly" / "Img2Tex"
    stage_runtime(runtime, target, portable=True)
    assert json.loads((target / "img2tex-runtime.json").read_text()) == metadata
    manifest = json.loads((target / "build-manifest.json").read_text(encoding="utf8"))
    assert manifest["runtime"] == metadata
    assert "models/xiaomi-ocr-0/model.safetensors" in manifest["files"]


def test_portable_zip_has_one_top_folder_and_valid_crc(tmp_path):
    runtime = sample_runtime(tmp_path)
    target = tmp_path / "portable" / "Img2Tex"
    stage_runtime(runtime, target, portable=True)
    archive = tmp_path / "Portable.zip"
    create_portable_zip(target, archive)
    with zipfile.ZipFile(archive) as package:
        assert package.testzip() is None
        assert all(name.startswith("Img2Tex/") for name in package.namelist())
        assert "Img2Tex/portable.flag" in package.namelist()
        assert "Img2Tex/Img2Tex.exe" in package.namelist()
        assert not any(Path(name).suffix == ".sqlite3" for name in package.namelist())


def test_release_output_cannot_reuse_stale_artifacts(tmp_path):
    import pytest

    from scripts import release
    output = tmp_path / "previous"
    output.mkdir()
    previous = output / "old-Setup-1.bin"
    previous.write_bytes(b"preserve previous release")
    # A nonempty publication directory must never be reused or cleaned silently.
    with pytest.raises(FileExistsError):
        release.create_release_directory(output)
    assert previous.read_bytes() == b"preserve previous release"
