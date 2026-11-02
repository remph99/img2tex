import io
import unittest

from PIL import Image

from img2tex.images import prepare_image


class ImageTests(unittest.TestCase):
    def test_alpha_composites_on_white_and_image_is_bounded(self):
        image = Image.new("RGBA", (3000, 300), (0, 0, 0, 0))
        image.putpixel((0, 0), (255, 0, 0, 255))
        data = io.BytesIO()
        image.save(data, "PNG")
        result = prepare_image(data.getvalue())
        self.assertEqual((result.width, result.height), (3000, 300))
        original = Image.open(io.BytesIO(result.original_png))
        self.assertEqual(original.getpixel((0, 0)), (255, 0, 0))
        self.assertEqual(original.getpixel((100, 100)), (255, 255, 255))
        model = Image.open(io.BytesIO(result.model_png))
        self.assertEqual(model.size, (2048, 205))
        self.assertNotEqual(result.sha256, result.model_sha256)

    def test_corrupt_input_rejected_as_actionable_error(self):
        with self.assertRaisesRegex(ValueError, "图片"):
            prepare_image(b"not an image")
