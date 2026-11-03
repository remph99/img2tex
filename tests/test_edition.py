import json

from img2tex import paths
from img2tex.edition import cpu_only, edition_label


def test_cpuonly_uses_bundled_metadata_without_importing_torch(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, 'application_dir', lambda: tmp_path)
    assert not cpu_only()
    (tmp_path / 'img2tex-runtime.json').write_text(json.dumps({'edition': 'cpuonly'}))
    assert cpu_only()
    assert edition_label() == 'CPU Only'
