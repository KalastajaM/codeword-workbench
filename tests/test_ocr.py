import base64
import io
import unittest
from PIL import Image, ImageDraw, ImageFont
from app.ocr import decode_image, recognize, available

class OCRTests(unittest.TestCase):
    def image(self):
        image = Image.new('RGB', (120, 60), 'white')
        ImageDraw.Draw(image).rectangle((0, 0, 59, 59), fill='black')
        stream = io.BytesIO()
        image.save(stream, format='PNG')
        return 'data:image/png;base64,' + base64.b64encode(stream.getvalue()).decode()

    def test_decode_rejects_invalid_and_non_image(self):
        for value in ['not an image', 'data:image/png;base64,bm90IGFuIGltYWdl']:
            with self.assertRaises(ValueError):
                decode_image(value)

    def test_black_cell_and_review_diagnostics(self):
        result = recognize({'image': self.image(), 'rows': 1, 'cols': 2})
        self.assertEqual(len(result['cells']), 2)
        self.assertTrue(result['cells'][0]['black'])
        self.assertFalse(result['cells'][1]['black'])
        self.assertTrue(result['diagnostics'])

    def test_outside_bounds_rejected(self):
        with self.assertRaises(ValueError):
            recognize({'image': self.image(), 'rows': 1, 'cols': 2,
                       'bounds': {'x': .9, 'y': 0, 'width': .5, 'height': 1}})

    @unittest.skipUnless(available(), 'Tesseract unavailable')
    def test_synthetic_number_transcription(self):
        image = Image.new('RGB', (300, 300), 'white')
        draw = ImageDraw.Draw(image)
        for i in range(9):
            x, y = (i % 3) * 100, (i // 3) * 100
            draw.rectangle((x, y, x+99, y+99), outline='black', width=2)
            draw.text((x+10, y+8), str(i+1), font=ImageFont.load_default(size=24), fill='black')
        stream = io.BytesIO()
        image.save(stream, format='PNG')
        result = recognize({'image': 'data:image/png;base64,' + base64.b64encode(stream.getvalue()).decode(),
                            'rows': 3, 'cols': 3})
        self.assertEqual([c['number'] for c in result['cells']], [str(i) for i in range(1, 10)])

    @unittest.skipUnless(available(), 'Tesseract unavailable')
    def test_known_number_letter_pairs_are_separate(self):
        image = Image.new('RGB', (300, 100), 'white')
        draw = ImageDraw.Draw(image)
        for i, letter in enumerate('ABC'):
            draw.rectangle((100*i, 0, 100*i+99, 99), outline='black', width=2)
            draw.text((100*i+8, 5), str(i+1), font=ImageFont.load_default(size=22), fill='black')
            draw.text((100*i+30, 33), letter, font=ImageFont.load_default(size=42), fill='black')
        stream = io.BytesIO()
        image.save(stream, format='PNG')
        result = recognize({'image': 'data:image/png;base64,' + base64.b64encode(stream.getvalue()).decode(),
                            'rows': 1, 'cols': 3})
        self.assertEqual([(cell['number'], cell['letter']) for cell in result['cells']],
                         [('1', 'A'), ('2', 'B'), ('3', 'C')])

    @unittest.skipUnless(available(), 'Tesseract unavailable')
    def test_edge_numbers_and_large_unnumbered_prefilled_letters(self):
        image = Image.new('RGB', (500, 100), 'white')
        draw = ImageDraw.Draw(image)
        for i, number in enumerate(['25', '12', '27']):
            draw.text((100*i+2, 0), number, font=ImageFont.load_default(size=28), fill='black')
        for i, letter in enumerate('ET', 3):
            draw.text((100*i+30, 14), letter, font=ImageFont.load_default(size=55), fill='black')
        stream = io.BytesIO()
        image.save(stream, format='PNG')
        result = recognize({'image': 'data:image/png;base64,' + base64.b64encode(stream.getvalue()).decode(),
                            'rows': 1, 'cols': 5})
        self.assertEqual([(cell['number'], cell['letter']) for cell in result['cells']],
                         [('25', ''), ('12', ''), ('27', ''), ('', 'E'), ('', 'T')])
