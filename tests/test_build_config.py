import pytest

from scripts.build_config import keep_resource, validate_torch_build


def test_release_keeps_required_webengine_assets_and_discards_debug_and_other_locales():
    assert keep_resource('PySide6/resources/icudtl.dat')
    assert keep_resource('PySide6/resources/v8_context_snapshot.bin')
    assert keep_resource('PySide6/translations/qtwebengine_locales/en-US.pak')
    assert keep_resource('PySide6/translations/qtwebengine_locales/zh-CN.pak')
    assert not keep_resource('PySide6/resources/qtwebengine_devtools_resources.debug.pak')
    assert not keep_resource('PySide6/resources/v8_context_snapshot.debug.bin')
    assert not keep_resource('PySide6/translations/qtwebengine_locales/fr.pak')
    assert keep_resource('torch/lib/nvrtc64_130_0.alt.dll')


def test_cpuonly_build_rejects_gpu_or_mixed_vision_runtime():
    validate_torch_build('2.14.0+cpu', '0.29.0+cpu', None, 'cpuonly')
    validate_torch_build('2.14.0+cu130', '0.29.0+cu130', '13.0', 'full')
    with pytest.raises(ValueError):
        validate_torch_build('2.14.0+cu130', '0.29.0+cu130', '13.0', 'cpuonly')
    with pytest.raises(ValueError):
        validate_torch_build('2.14.0+cpu', '0.29.0+cu130', None, 'cpuonly')
