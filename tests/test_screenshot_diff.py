import tempfile
import unittest
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover - optional developer dependency
    Image = None

if Image is not None:
    from verifier.screenshot_diff import compare
else:
    compare = None


@unittest.skipIf(Image is None, "Pillow developer dependency is not installed")
class ScreenshotDiffTests(unittest.TestCase):
    def test_reports_changed_pixel_ratio(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline = root / "baseline.png"
            current = root / "current.png"
            Image.new("RGB", (10, 10), "black").save(baseline)
            changed = Image.new("RGB", (10, 10), "black")
            changed.putpixel((2, 3), (255, 255, 255))
            changed.save(current)

            result = compare(baseline, current, 24, None)

            self.assertEqual(result["changed_pixels"], 1)
            self.assertEqual(result["changed_ratio"], 0.01)


if __name__ == "__main__":
    unittest.main()
