"""Optional real-model smoke test; regular query tests use small SQLite fixtures."""
import subprocess
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
NATIVE=ROOT/'data/morphology/native/bin/python'

class MorphologyBuildTests(unittest.TestCase):
    @unittest.skipUnless(NATIVE.exists() and (ROOT/'data/morphology/omorfi.generate.hfst').exists(), 'Optional native HFST/models not installed')
    def test_native_generation_known_forms(self):
        code="""
from scripts.build_finnish_morphology import initialise,generate_batch
initialise('data/morphology')
rows,missing=generate_batch([('talo','substantiivi'),('äiti','substantiivi'),('yö','substantiivi'),('juosta','verbi')])
words={row[0] for row in rows}
assert {'TALOJEN','TALOSSA','ÄITIEN','ÄIDILLÄ','YÖN','JUOKSEN'}<=words, words
"""
        subprocess.run([str(NATIVE),'-c',code],cwd=ROOT,check=True,timeout=30,capture_output=True)
