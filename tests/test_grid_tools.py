import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class GridToolTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="grid-tools-", dir=ROOT))

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def run_cmd(self, args):
        return subprocess.run(
            args,
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )

    def test_grid_calc_cli_and_metadata(self):
        self.run_cmd(["gcc", "-o", "tools/grid_calc", "tools/grid_calc.c", "-lm"])
        self.run_cmd(
            ["./tools/grid_calc", "--level", "1", "--output-dir", str(self.tmpdir)]
        )

        metadata_path = self.tmpdir / "icosahedral_grid_level_1.json"
        self.assertTrue(metadata_path.exists())
        metadata = json.loads(metadata_path.read_text())
        self.assertEqual(metadata["grid_type"], "icosahedral")
        self.assertEqual(metadata["grid_level"], 1)
        self.assertEqual(metadata["face_count"], 80)
        self.assertTrue((self.tmpdir / metadata["solid_file"]).exists())
        self.assertTrue((self.tmpdir / metadata["wireframe_file"]).exists())

    def test_latlon_grid_calc_cli_and_metadata(self):
        self.run_cmd(["gcc", "-o", "tools/latlon_grid_calc", "tools/latlon_grid_calc.c", "-lm"])
        self.run_cmd(
            [
                "./tools/latlon_grid_calc",
                "--lat",
                "18",
                "--lon",
                "36",
                "--output-dir",
                str(self.tmpdir),
            ]
        )

        metadata_path = self.tmpdir / "latlon_grid_18x36.json"
        self.assertTrue(metadata_path.exists())
        metadata = json.loads(metadata_path.read_text())
        self.assertEqual(metadata["grid_type"], "latlon")
        self.assertEqual(metadata["lat_divisions"], 18)
        self.assertEqual(metadata["lon_divisions"], 36)
        self.assertEqual(metadata["rectangle_count"], 648)
        self.assertEqual(metadata["triangle_count"], 1296)
        self.assertTrue((self.tmpdir / metadata["solid_file"]).exists())
        self.assertTrue((self.tmpdir / metadata["wireframe_file"]).exists())
