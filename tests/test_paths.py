from pathlib import Path

from img2tex import paths


def app_root(monkeypatch, tmp_path, portable=False):
    root = tmp_path / "应用 程序"
    root.mkdir()
    monkeypatch.setattr(paths, "application_dir", lambda: root)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "profile"))
    if portable:
        (root / "portable.flag").write_text("", encoding="utf8")
    return root


def test_installed_data_stays_in_existing_user_profile(monkeypatch, tmp_path):
    app_root(monkeypatch, tmp_path)
    assert paths.app_data_dir() == tmp_path / "profile" / "Img2Tex"


def test_portable_data_and_runtime_caches_follow_executable(monkeypatch, tmp_path):
    root = app_root(monkeypatch, tmp_path, portable=True)
    for name in ("HF_HOME", "TORCH_HOME", "XDG_CACHE_HOME"):
        monkeypatch.setenv(name, "previous-value")
    assert paths.app_data_dir() == root / "data"
    paths.configure_runtime()
    import os
    assert Path(os.environ["HF_HOME"]).is_relative_to(root / "data")
    assert Path(os.environ["TORCH_HOME"]).is_relative_to(root / "data")
    assert (root / "data" / "logs").is_dir()
    assert not (tmp_path / "profile").exists()


def test_bundled_model_setting_survives_directory_move(monkeypatch, tmp_path):
    root = app_root(monkeypatch, tmp_path, portable=True)
    model = root / "models" / "xiaomi-ocr-0"
    model.mkdir(parents=True)
    saved = paths.serialize_model_path(str(model))
    assert saved == "models/xiaomi-ocr-0"
    moved = tmp_path / "移动 后"
    root.rename(moved)
    monkeypatch.setattr(paths, "application_dir", lambda: moved)
    assert paths.resolve_model_path(saved) == str(moved / "models" / "xiaomi-ocr-0")


def test_external_model_selection_remains_absolute(monkeypatch, tmp_path):
    app_root(monkeypatch, tmp_path, portable=True)
    external = tmp_path / "external" / "model"
    saved = paths.serialize_model_path(str(external))
    assert Path(saved).is_absolute()
    assert paths.resolve_model_path(saved) == str(external)


def test_unwritable_portable_data_never_falls_back_to_profile(monkeypatch, tmp_path):
    import pytest
    root = app_root(monkeypatch, tmp_path, portable=True)
    (root / "data").write_text("blocked by file", encoding="utf8")
    with pytest.raises(OSError):
        paths.configure_runtime()
    assert not (tmp_path / "profile").exists()
