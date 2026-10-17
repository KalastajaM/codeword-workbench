"""The bundled sample page is read exactly by automatic recognition."""
import base64
import json
import shutil
import subprocess
import unittest
from pathlib import Path

from app import ocr

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(ocr.available() and shutil.which('node'), 'Needs Pillow, Tesseract and Node.js.')
class SamplePageTests(unittest.TestCase):
    def test_recognition_reads_every_number_and_black_cell(self):
        image = 'data:image/png;base64,' + base64.b64encode((ROOT/'static'/'samples'/'showcase-en.png').read_bytes()).decode()
        result = ocr.recognize(dict(image=image, autoDetect=True))
        expected = json.loads(subprocess.run(['node', '-e', "console.log(JSON.stringify(require('./static/samples.js').samplePuzzle()))"],
                                             cwd=ROOT, capture_output=True, text=True, check=True).stdout)
        self.assertEqual((result['rows'], result['cols']), (expected['rows'], expected['cols']))
        got = [(bool(c.get('black')), c.get('number') or '') for c in result['cells']]
        want = [(c['black'], c['number']) for c in expected['cells']]
        self.assertEqual(got, want)


if __name__ == '__main__':
    unittest.main()
