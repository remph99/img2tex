import hashlib
import http.server
import tempfile
import threading
import unittest
from pathlib import Path

from img2tex.model_setup import download_weight_file


class DownloadTests(unittest.TestCase):
    def test_resumes_partial_ranges_and_checks_final_hash(self):
        data = b"actual-checkpoint-fixture" * 7
        ranges = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                start, end = map(int, self.headers["Range"][6:].split("-"))
                ranges.append((start, end))
                block = data[start:end + 1]
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
                self.send_header("Content-Length", str(len(block)))
                self.end_headers()
                self.wfile.write(block)

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as temp:
                output = Path(temp) / "weights.bin"
                output.with_name("weights.bin.part").write_bytes(data[:9])
                download_weight_file(f"http://127.0.0.1:{server.server_port}/weights", output,
                                     len(data), hashlib.sha256(data).hexdigest(), chunk_size=17)
                self.assertEqual(output.read_bytes(), data)
                self.assertEqual(ranges[0], (9, 25))
                self.assertFalse(output.with_name("weights.bin.part").exists())
                # A complete verified file is reusable without another request.
                count = len(ranges)
                download_weight_file("invalid://unused", output, len(data), hashlib.sha256(data).hexdigest())
                self.assertEqual(len(ranges), count)
        finally:
            server.shutdown()
            server.server_close()

    def test_bad_complete_partial_is_never_published_as_model(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "weights.bin"
            output.with_name("weights.bin.part").write_bytes(b"wrong")
            with self.assertRaisesRegex(ValueError, "校验"):
                download_weight_file("unused", output, 5, hashlib.sha256(b"right").hexdigest())
            self.assertFalse(output.exists())
