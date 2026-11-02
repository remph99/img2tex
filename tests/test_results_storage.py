import tempfile
import unittest
from pathlib import Path

from img2tex.results import normalize_latex
from img2tex.storage import Store


class ResultTests(unittest.TestCase):
    def test_matching_outer_wrappers_only(self):
        for raw, expected in [
            ("```latex\n\\frac{1}{2}\n```", "\\frac{1}{2}"),
            ("$$x+1$$", "x+1"), ("\\[x^2\\]", "x^2"),
            ("$x$ + $y$", "$x$ + $y$"), ("$x", "$x"),
            ("\\begin{aligned}x&=1\\\\y&=2\\end{aligned}",
             "\\begin{aligned}x&=1\\\\y&=2\\end{aligned}"),
        ]:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_latex(raw), expected)

    def test_empty_or_thinking_response_rejected(self):
        for raw in ["  ", "$$ $$", "<think>reasoning</think>x=1"]:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                normalize_latex(raw)


class StoreTests(unittest.TestCase):
    def test_history_keeps_raw_when_edited_and_survives_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "中文" / "state.sqlite3"
            store = Store(path)
            store.set_setting("device", "cpu")
            record_id = store.add_result({
                "raw_output": "$$x^2$$", "latex_normalized": "x^2", "device": "cpu",
                "elapsed_seconds": 1.2, "model_revision": "fixed",
                "parameters": {"do_sample": False, "dtype": "float32"}, "model_image_sha256": "model-hash",
            }, b"original-image")
            store.update_edited(record_id, "x^3")
            store.close()
            store = Store(path)
            record = store.get_record(record_id)
            self.assertEqual(record["raw_output"], "$$x^2$$")
            self.assertEqual(record["latex_normalized"], "x^2")
            self.assertEqual(record["latex_edited"], "x^3")
            self.assertEqual(record["image_png"], b"original-image")
            self.assertEqual(record["metadata"]["parameters"]["dtype"], "float32")
            self.assertEqual(record["metadata"]["model_image_sha256"], "model-hash")
            self.assertEqual(store.get_setting("device"), "cpu")
            self.assertEqual(store.get_setting("absent", 42), 42)
            self.assertEqual(len(store.list_history("x^3")), 1)
            self.assertEqual(store.list_history("absent"), [])
            store.delete(record_id)
            self.assertIsNone(store.get_record(record_id))
            store.close()

    def test_empty_result_cannot_enter_success_history(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp) / "state.sqlite3")
            with self.assertRaises(ValueError):
                store.add_result({"raw_output": "", "latex_normalized": ""}, b"image")
            self.assertEqual(store.list_history(), [])
            store.close()
