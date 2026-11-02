import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from img2tex.model_setup import check_model_directory, device_options


class ModelSetupTests(unittest.TestCase):
    def test_custom_model_is_not_mislabeled_as_verified_release(self):
        from img2tex.model_setup import MODEL_ID, MODEL_REVISION, WEIGHT_SHA256, model_revision
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            self.assertEqual(model_revision(path), "local-unverified")
            manifest = path / "img2tex-model.json"
            manifest.write_text(json.dumps({"repo_id": MODEL_ID, "revision": MODEL_REVISION,
                                            "weights_sha256": WEIGHT_SHA256}), encoding="utf8")
            self.assertEqual(model_revision(path), MODEL_REVISION)
            manifest.write_text("{}", encoding="utf8")
            self.assertEqual(model_revision(path), "local-unverified")

    def test_cpu_does_not_require_cuda_and_cuda_unavailable_is_explicit(self):
        self.assertEqual(device_options("cpu", cuda_available=False), ("cpu", "float32"))
        self.assertEqual(device_options("cuda", cuda_available=True), ("cuda", "float16"))
        with self.assertRaisesRegex(ValueError, "CUDA"):
            device_options("cuda", cuda_available=False)
        with self.assertRaises(ValueError):
            device_options("auto", cuda_available=True)

    def test_incomplete_model_reports_missing_files(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            with self.assertRaisesRegex(ValueError, "config.json"):
                check_model_directory(path)
            (path / "config.json").write_text(json.dumps({"model_type": "unrelated"}), encoding="utf8")
            with self.assertRaisesRegex(ValueError, "Xiaomi|Qwen"):
                check_model_directory(path)

    def test_packaged_model_folder_is_available_outside_source_directory(self):
        from img2tex.model_setup import default_model_dir
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model = root / "models" / "xiaomi-ocr-0"
            model.mkdir(parents=True)
            (model / "config.json").write_text("{}", encoding="utf8")
            with patch("img2tex.model_setup.sys.executable", str(root / "Img2Tex.exe")), \
                 patch("img2tex.model_setup.sys.frozen", True, create=True):
                self.assertEqual(default_model_dir(), model)
