import base64
import io
import unittest
from unittest.mock import patch
from PIL import Image
from app.pdf_import import available, convert
from app.ocr import decode_image


def fixture():
    stream = io.BytesIO()
    Image.new('RGB', (100, 150), 'white').save(stream, format='PDF', save_all=True,
                                            append_images=[Image.new('RGB', (100, 150), 'black')])
    return 'data:application/pdf;base64,' + base64.b64encode(stream.getvalue()).decode()


class PDFImportTests(unittest.TestCase):
    @unittest.skipUnless(available(), 'Poppler unavailable')
    def test_metadata_and_selected_page(self):
        pdf = fixture()
        self.assertEqual(convert({'pdf': pdf}), {'pages': 2})
        result = convert({'pdf': pdf, 'page': 2})
        image = decode_image(result['image'])
        self.assertEqual(image.getpixel((image.width//2, image.height//2)), (0, 0, 0))
        self.assertEqual(max(image.size), 3000)
        self.assertEqual(result['page'], 2)
        with self.assertRaises(ValueError):
            convert({'pdf': pdf, 'page': 3})

    def test_invalid_input_and_missing_tools(self):
        for payload in [[], {}, {'pdf': 'bad'}, {'pdf': 'data:application/pdf;base64,%%%%'},
                        {'pdf': fixture(), 'page': True}, {'pdf': fixture(), 'page': 0}]:
            with self.assertRaises(ValueError):
                convert(payload)
        with patch('app.pdf_import.available', return_value=False):
            with self.assertRaisesRegex(ValueError, 'Poppler'):
                convert({'pdf': fixture()})

    @unittest.skipUnless(available(), 'Poppler unavailable')
    def test_damaged_pdf(self):
        with self.assertRaisesRegex(ValueError, 'damaged'):
            convert({'pdf': 'data:application/pdf;base64,' + base64.b64encode(b'%PDF-broken').decode()})
