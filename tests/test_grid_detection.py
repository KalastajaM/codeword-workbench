import base64
import io
import random
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageFont
from app.grid_detection import detect_grid, cell_appearance, missing_grid_regions, grid_edges
from app.ocr import recognize, available


def data_url(image):
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode()


class GridDetectionTests(unittest.TestCase):
    def test_cross_shape_keeps_arms_and_excludes_detached_number_key(self):
        image = Image.new('RGB', (1061, 1061), 'white')
        draw = ImageDraw.Draw(image)
        for c in range(21):
            draw.rectangle((5+c*50, 5, 5+(c+1)*50, 55), outline='black', width=3)
        for r in range(19):
            for c in range(21):
                if not (7 <= c < 14 or 6 <= r < 13):
                    continue
                draw.rectangle((5+c*50, 105+r*50, 5+(c+1)*50, 105+(r+1)*50),
                               fill='#006000' if r % 2 == 0 and c % 2 == 1 else 'white',
                               outline='black', width=2)
        with patch('app.ocr.available', return_value=False):
            result = recognize({'image': data_url(image), 'autoDetect': True})
        self.assertEqual((result['rows'], result['cols']), (19, 21))
        self.assertAlmostEqual(result['bounds']['y'], 105/1061, delta=.004)
        for r in range(19):
            for c in range(21):
                cell = result['cells'][r*21+c]
                outside = not (7 <= c < 14 or 6 <= r < 13)
                self.assertEqual(cell['clue'], outside, (r, c))
                self.assertEqual(cell['black'], outside or (r % 2 == 0 and c % 2 == 1), (r, c))

    def test_upper_right_detached_key_is_not_playable(self):
        image = Image.new('RGB', (941, 1261), 'white')
        draw = ImageDraw.Draw(image)
        pitch, left, top = 50, 40, 50
        for r in range(23):
            for c in range(17):
                if r < 6 and c >= 11:
                    continue
                draw.rectangle((left+c*pitch, top+r*pitch,
                                left+(c+1)*pitch, top+(r+1)*pitch),
                               outline='black', width=3)
        for r in range(5):
            for c in range(12, 17):
                draw.rectangle((left+c*pitch, top+r*pitch,
                                left+(c+1)*pitch, top+(r+1)*pitch),
                               outline='black', width=3)
                draw.text((left+c*pitch+7, top+r*pitch+5),
                          str(r*5+c-11), fill='black', font=ImageFont.load_default(size=16))
        for ocr_available in (False, True) if available() else (False,):
            with self.subTest(ocr_available=ocr_available):
                with patch('app.ocr.available', return_value=ocr_available):
                    result = recognize({'image': data_url(image), 'autoDetect': True})
                self.assertEqual((result['rows'], result['cols']), (23, 17))
                self.assertEqual({i for i, cell in enumerate(result['cells']) if cell['clue']},
                                 {r*17+c for r in range(6) for c in range(11, 17)})
                self.assertTrue(all(cell['black'] == cell['clue'] for cell in result['cells']))

    def test_thin_grid_strokes_survive_a_large_dark_photo(self):
        image = Image.new('RGB', (1265, 1385), 'white')
        draw = ImageDraw.Draw(image)
        for r in range(23):
            for c in range(21):
                if r % 2 == 0 and c % 2 == 1:
                    draw.rectangle((2+c*60, 2+r*60, 2+(c+1)*60, 2+(r+1)*60), fill='#783411')
        for x in range(2, 1263, 60):
            draw.line((x, 2, x, 1382), fill='#202020')
        for y in range(2, 1383, 60):
            draw.line((2, y, 1262, y), fill='#202020')
        rng = random.Random(42)
        # Photo covers nine columns and nine rows, making raw darkness
        # projections merge grid strokes with broad bands of image texture.
        for y in range(842, 1382):
            for x in range(302, 842):
                v = rng.randrange(20, 140)
                image.putpixel((x, y), (v, v, v))
        rows, cols, bounds = detect_grid(image)
        self.assertEqual((rows, cols), (23, 21))
        self.assertAlmostEqual(bounds['x'], 2/1265, delta=.004)
        self.assertAlmostEqual(bounds['height'], 1380/1385, delta=.006)

    def printed_puzzle(self):
        image = Image.new('RGB', (760, 990), 'white')
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 759, 989), outline='#122e4b', width=18)
        # Main puzzle: 10 columns by 13 rows, with separate smaller mapping key.
        left, top, pitch, cols, rows = 70, 100, 60, 10, 13
        for c in range(cols + 1):
            draw.line((left+c*pitch, top, left+c*pitch, top+rows*pitch), fill='#122e4b', width=4)
        for r in range(rows + 1):
            draw.line((left, top+r*pitch, left+cols*pitch, top+r*pitch), fill='#122e4b', width=4)
        for c in range(16):
            draw.line((180+c*25, 920, 180+c*25, 970), fill='#122e4b', width=3)
        for y in (920, 945, 970):
            draw.line((180, y, 555, y), fill='#122e4b', width=3)
        draw.rectangle((left+9, top+9, left+51, top+51), fill='#122e4b')
        draw.rectangle((left+6*pitch+3, top+3, left+7*pitch-3, top+pitch-3), fill='#e1e9ed')
        rng = random.Random(125)
        # A photograph interrupts internal strokes across a rectangle.
        for y in range(top+3, top+3*pitch-2):
            for x in range(left+2*pitch+3, left+5*pitch-2):
                image.putpixel((x, y), tuple(rng.randrange(25, 220) for _ in range(3)))
        return image

    def test_dominant_grid_ignores_frame_and_mapping_key(self):
        rows, cols, bounds = detect_grid(self.printed_puzzle())
        self.assertEqual((rows, cols), (13, 10))
        self.assertAlmostEqual(bounds['x'], 70/760, delta=.004)
        self.assertAlmostEqual(bounds['y'], 100/990, delta=.004)
        self.assertAlmostEqual(bounds['width'], 600/760, delta=.006)
        self.assertAlmostEqual(bounds['height'], 780/990, delta=.006)

    def test_auto_import_retains_clue_and_shaded_cells_without_ocr(self):
        with patch('app.ocr.available', return_value=False):
            result = recognize({'image': data_url(self.printed_puzzle()), 'autoDetect': True})
        self.assertEqual((result['rows'], result['cols']), (13, 10))
        cells = result['cells']
        self.assertTrue(cells[0]['black'])
        self.assertFalse(cells[0]['clue'])
        self.assertTrue(cells[6]['highlight'])
        self.assertEqual([i for i, cell in enumerate(cells) if cell['clue']],
                         [r*10+c for r in range(3) for c in range(2, 5)])
        for cell in cells:
            self.assertFalse(any(cell[key] for key in cell if key.startswith('open')))
            if cell['clue']:
                self.assertTrue(cell['black'])
                self.assertEqual((cell['number'], cell['letter']), ('', ''))

    def test_no_grid_reports_manual_recovery(self):
        with self.assertRaisesRegex(ValueError, 'manually'):
            detect_grid(Image.new('RGB', (400, 500), 'white'))

    def test_inset_square_is_a_block_not_photo(self):
        tile = Image.new('RGB', (100, 100), 'white')
        ImageDraw.Draw(tile).rectangle((14, 14, 86, 86), fill='#122e4b')
        self.assertEqual(cell_appearance(tile), (True, False, False))

    def cartoon_puzzle(self):
        image = Image.new('RGB', (1100, 1600), 'white')
        draw = ImageDraw.Draw(image)
        left, top, pitch, rows, cols = 80, 100, 55, 23, 17
        # Page frame coincidentally lies exactly one cell pitch outside the grid.
        draw.rectangle((25, 35, 1070, 1540), outline='black', width=2)
        for r in range(rows):
            for c in range(cols):
                box = (left+c*pitch, top+r*pitch, left+(c+1)*pitch, top+(r+1)*pitch)
                draw.rectangle(box, fill='black' if r % 2 == 0 and c % 2 == 1 else 'white', outline='black', width=3)
        # Mostly flat colour and white margins: texture alone cannot find this.
        draw.rectangle((left, top+8*pitch, left+7*pitch, top+17*pitch), fill='white', outline='black', width=3)
        draw.ellipse((left+50, top+9*pitch, left+7*pitch-50, top+16*pitch), fill='#d85900', outline='black', width=10)
        for c in range(7, 12):
            draw.rectangle((left+c*pitch+3, top+16*pitch+3, left+(c+1)*pitch-3, top+17*pitch-3), fill='#f8d7ad')
        return image

    def test_grid_with_large_flat_clue_and_coincidental_frame_pitch(self):
        image = self.cartoon_puzzle()
        with patch('app.ocr.available', return_value=False):
            result = recognize({'image': data_url(image), 'autoDetect': True})
        self.assertEqual((result['rows'], result['cols']), (23, 17))
        self.assertAlmostEqual(result['bounds']['x'], 80/1100, delta=.004)
        cells = result['cells']
        self.assertEqual([i for i, cell in enumerate(cells) if cell['clue']],
                         [r*17+c for r in range(8, 17) for c in range(7)])
        self.assertEqual([i for i, cell in enumerate(cells) if cell['highlight']],
                         [16*17+c for c in range(7, 12)])
        self.assertTrue(cells[1]['black'])
        self.assertFalse(cells[1]['clue'])

    def test_orange_highlight_is_a_usable_cell(self):
        image = Image.new('RGB', (80, 80), '#f8d7ad')
        self.assertEqual(cell_appearance(image), (False, False, True))

    def test_jpeg_noise_in_brown_block_is_not_a_photograph(self):
        rng = random.Random(7)
        image = Image.new('RGB', (70, 70))
        image.putdata([tuple(v+rng.randrange(-5, 6) for v in (120, 52, 17)) for _ in range(4900)])
        self.assertEqual(cell_appearance(image), (True, False, False))

    def test_yellow_answer_cell_is_highlighted(self):
        self.assertEqual(cell_appearance(Image.new('RGB', (70, 70), '#fff180')),
                         (False, False, True))

    def test_number_key_and_its_borderless_surround_excluded(self):
        from app.ocr import _mapping_key_cells, _mapping_key_panel
        cells = [dict(number='7', letter='', black=False) for _ in range(8*12)]
        image = Image.new('RGB', (721, 481), 'white')
        draw = ImageDraw.Draw(image)
        for x in range(0, 721, 60):
            draw.line((x, 0, x, 480), fill='black', width=2)
        for y in range(0, 481, 60):
            draw.line((0, y, 720, y), fill='black', width=2)
        draw.rectangle((0, 0, 300, 180), fill='white', outline='black', width=2)
        for r in range(3):
            for c in range(5):
                cells[r*12+c]['number'] = ''
        for r in range(2):
            for c in range(4):
                draw.rectangle((c*60, r*60, (c+1)*60, (r+1)*60), outline='black', width=2)
                cells[r*12+c]['number'] = str(r*4+c+1)
        keys = _mapping_key_cells(cells, 8, 12)
        self.assertEqual(keys, {0, 1, 2, 3, 12, 13, 14, 15})
        clues = missing_grid_regions(image, 8, 12, dict(x=0, y=0, width=720/721, height=480/481), keys)
        self.assertEqual(clues | keys, {0, 1, 2, 3, 4, 12, 13, 14, 15, 16, 24, 25, 26, 27, 28})
        # Printed attribution below a key may look like letters to OCR; it is
        # not a playable word row when the internal grid strokes are absent.
        cells[25]['letter'] = 'F'
        self.assertEqual(_mapping_key_cells(cells, 8, 12,
                         grid_edges(image, 8, 12, dict(x=0, y=0, width=720/721, height=480/481))), keys)
        draw.line((240, 60, 300, 60), fill='black', width=2)  # a logo stroke in the separator
        self.assertEqual(_mapping_key_panel(cells, 8, 12, keys,
                         grid_edges(image, 8, 12, dict(x=0, y=0, width=720/721, height=480/481))),
                         {0, 1, 2, 3, 4, 12, 13, 14, 15, 16, 24, 25, 26, 27, 28})
        cells[0]['number'] = '9'
        self.assertEqual(_mapping_key_cells(cells, 8, 12), set())

    def test_textured_blocks_do_not_expand_over_numbered_cells(self):
        image = Image.new('RGB', (601, 601), 'white')
        rng = random.Random(17)
        # Adjacent textured blocks form an L, never a rectangular photograph.
        for r, c in [(1, 1), (1, 2), (2, 1), (4, 4)]:
            for y in range(r*60, (r+1)*60):
                for x in range(c*60, (c+1)*60):
                    value = rng.randrange(90, 215)
                    image.putpixel((x, y), (value, value, value))
        draw = ImageDraw.Draw(image)
        for coordinate in range(0, 601, 60):
            draw.line((coordinate, 0, coordinate, 600), fill='#666666', width=1)
            draw.line((0, coordinate, 600, coordinate), fill='#666666', width=1)
        with patch('app.ocr.available', return_value=False):
            result = recognize({'image': data_url(image), 'rows': 10, 'cols': 10,
                                'bounds': dict(x=0, y=0, width=600/601, height=600/601)})
        self.assertFalse(any(cell['clue'] for cell in result['cells']))
        self.assertEqual([i for i, cell in enumerate(result['cells']) if cell['black']], [11, 12, 21, 44])
        self.assertFalse(result['cells'][22]['black'])

    def test_faint_manual_grid_is_not_an_entire_illustration(self):
        image = Image.new('RGB', (201, 201), 'white')
        draw = ImageDraw.Draw(image)
        for coordinate in range(0, 201, 50):
            draw.line((coordinate, 0, coordinate, 200), fill=(150, 150, 150), width=2)
            draw.line((0, coordinate, 200, coordinate), fill=(150, 150, 150), width=2)
        with patch('app.ocr.available', return_value=False):
            result = recognize({'image': data_url(image), 'rows': 4, 'cols': 4})
        self.assertTrue(all(not cell['clue'] and not cell['black'] for cell in result['cells']))
