import base64
import io
import random
import unittest
from PIL import Image, ImageDraw, ImageFont

from app.number_reader import _binary, _strip_lines, number_glyphs, number_range, read_numbers, review_numbers
from app.ocr import _recognize_sheet, available, recognize


def cell(number, size=60, font=None, border=2, at=(5, 3)):
    image = Image.new('RGB', (size, size), 'white')
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, size-1, size-1), outline='black', width=border)
    draw.text(at, number, font=font or ImageFont.load_default(size=size*.35), fill='black')
    return image


def no_ocr(sheet, whitelist, diagnostics, psm=6):
    return []


class NumberSegmentationTests(unittest.TestCase):
    def test_grid_strokes_are_removed_but_touching_digits_kept(self):
        image = cell('7', border=1, at=(1, 0))
        mask = _strip_lines(_binary(image.convert('L')))
        self.assertFalse(any(mask[0]) or any(row[0] for row in mask))
        self.assertEqual(len(number_glyphs(image)), 1)

    def test_digits_split_even_when_they_touch(self):
        image = Image.new('RGB', (60, 60), 'white')
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default(size=22)
        draw.text((4, 2), '1', font=font, fill='black')
        # Overlap the second digit so the two glyphs form one component.
        draw.text((4+font.getlength('1')-3, 2), '8', font=font, fill='black')
        self.assertEqual(len(number_glyphs(image)), 2)

    def test_grid_line_slivers_and_bent_border_pieces_are_not_digits(self):
        # A crop a pixel off the grid keeps a short piece of the side stroke,
        # and a curled page bends the outer border into the cell's corner.
        image = Image.new('RGB', (70, 70), 'white')
        draw = ImageDraw.Draw(image)
        draw.text((9, 6), '8', font=ImageFont.load_default(size=22), fill='black')
        draw.line((1, 4, 1, 26), fill='black', width=1)
        self.assertEqual(len(number_glyphs(image)), 1)
        bent = Image.new('RGB', (70, 70), 'white')
        draw = ImageDraw.Draw(bent)
        draw.text((8, 9), '16', font=ImageFont.load_default(size=22), fill='black')
        draw.line([(2, 0), (2, 22)], fill='black', width=1)
        draw.line([(2, 4), (22, 0)], fill='black', width=1)
        self.assertEqual(len(number_glyphs(bent)), 2)

    def test_faint_thin_digits_stay_whole(self):
        # Photographed print has light, thin strokes next to a dark border.
        image = Image.new('RGB', (70, 70), (235, 235, 235))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 69, 69), outline=(20, 20, 20), width=2)
        draw.text((8, 6), '16', font=ImageFont.load_default(size=22), fill=(120, 120, 120))
        # Camera blur thins the strokes further.
        image = image.resize((140, 140)).resize((70, 70), Image.Resampling.BILINEAR)
        self.assertEqual(len(number_glyphs(image)), 2)

    def test_large_letters_and_blank_cells_are_not_numbers(self):
        image = cell('')
        ImageDraw.Draw(image).text((15, 15), 'W', font=ImageFont.load_default(size=36), fill='black')
        self.assertEqual(number_glyphs(image), [])
        self.assertEqual(number_glyphs(cell('')), [])


class NumberConsensusTests(unittest.TestCase):
    def glyphs(self, numbers):
        return {i: number_glyphs(cell(n)) for i, n in enumerate(numbers)}

    def test_majority_of_matching_shapes_corrects_misread_cells(self):
        numbers = ['13']*6 + ['18']*6 + ['8']*4
        readings = dict(enumerate(numbers))
        readings[0], readings[6], readings[12] = '18', '13', '3'
        result, _ = read_numbers(self.glyphs(numbers), readings, no_ocr, [])
        self.assertEqual([result[i] for i in range(len(numbers))], numbers)

    def test_weak_clusters_are_relabelled_to_complete_one_to_n(self):
        numbers = [str(n) for n in range(1, 22)] + ['20']
        readings = dict(enumerate(numbers))
        # Both readings of 20 disagree; every other number is read correctly.
        readings[19], readings[21] = '29', ''
        result, _ = read_numbers(self.glyphs(numbers), readings, no_ocr, [])
        self.assertEqual(result[19], '20')
        self.assertEqual(result[21], '20')

    @unittest.skipUnless(available(), 'Tesseract unavailable')
    def test_rare_digits_are_not_absorbed_by_common_similar_digits(self):
        for rare, common in ('09', '38', '56', '17', '90'):
            with self.subTest(rare=rare, common=common):
                numbers = ['1'+rare] + ['1'+common]*16
                result, _ = read_numbers(self.glyphs(numbers), dict(enumerate(numbers)), _recognize_sheet, [])
                self.assertEqual(result[0], '1'+rare)

    @unittest.skipUnless(available(), 'Tesseract unavailable')
    def test_prototype_ocr_reads_numbers_without_per_cell_readings(self):
        numbers = [str(n) for n in range(1, 27)]*2
        result, _ = read_numbers(self.glyphs(numbers), {}, _recognize_sheet, [])
        self.assertEqual([result.get(i) for i in range(len(numbers))], numbers)


@unittest.skipUnless(available(), 'Tesseract unavailable')
class SmallBitmapPuzzleTests(unittest.TestCase):
    def test_tiny_bitmap_numbers_with_one_pixel_grid_lines(self):
        """Regression: a 451 px, 15x15 screenshot with ~8 px tall digits."""
        size, pitch = 15, 30
        rng = random.Random(7)
        numbers = [str(n) for n in range(1, 27)]
        numbers += [str(rng.randint(1, 26)) for _ in range(size*size-len(numbers)-30)]
        rng.shuffle(numbers)
        inner = [i for i in range(size*size) if 0 < i//size < size-1 and 0 < i % size < size-1]
        blocks = set(rng.sample(inner, 30))
        font = ImageFont.load_default_imagefont()
        image = Image.new('RGB', (size*pitch+1, size*pitch+1), 'white')
        draw = ImageDraw.Draw(image)
        expected, values = [], iter(numbers)
        for index in range(size*size):
            r, c = divmod(index, size)
            x, y = c*pitch, r*pitch
            if index in blocks:
                draw.rectangle((x, y, x+pitch, y+pitch), fill='black')
                expected.append('')
                continue
            number = next(values)
            draw.rectangle((x, y, x+pitch, y+pitch), outline='black')
            draw.text((x+4, y+3), number, font=font, fill='black')
            expected.append(number)
        stream = io.BytesIO()
        image.save(stream, format='PNG')
        result = recognize({'image': 'data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode(),
                            'autoDetect': True})
        self.assertEqual((result['rows'], result['cols']), (size, size))
        self.assertEqual([c['number'] for c in result['cells']], expected)
        self.assertFalse(any(c['letter'] for c in result['cells']))


if __name__ == '__main__':
    unittest.main()


class NumberReviewTests(unittest.TestCase):
    @staticmethod
    def cells(numbers):
        return [{'black': number is None, 'number': number or ''} for number in numbers]

    def test_range_follows_repeated_run_and_ignores_rare_large_misreads(self):
        values = [n for n in range(1, 26) for _ in range(3)] + [114, 101, 241]
        self.assertEqual(number_range(values), 25)
        # One gap in the run is tolerated; a far outlier repeated twice is not.
        self.assertEqual(number_range([1, 1, 2, 2, 5, 5, 6, 6, 90, 90]), 6)

    def test_out_of_range_numbers_are_repaired_or_reported_missing(self):
        numbers = [str(n) for n in range(1, 26) for _ in range(2)]
        cells = self.cells(numbers + ['114', '241', '999', '', None])
        confidence = {i: 1 for i in range(len(cells))}
        checked, missing = review_numbers(cells, confidence)
        self.assertEqual([c['number'] for c in cells[-5:-1]], ['14', '24', '', ''])
        self.assertEqual([c.get('numberReview') for c in cells[-5:]], ['check', 'check', 'missing', 'missing', None])
        self.assertEqual((checked, missing), (2, 2))
        self.assertNotIn('numberReview', cells[0])

    def test_weak_or_unique_readings_are_marked_for_checking(self):
        cells = self.cells(['1', '1', '2', '2', '2', '4'])
        review_numbers(cells, {0: 1, 1: 1, 2: .4, 3: 1, 4: 1, 5: 1})
        # 4 is used once, just above the repeated run: kept, but checked.
        self.assertEqual([c.get('numberReview') for c in cells], [None, None, 'check', None, None, 'check'])
        self.assertEqual(cells[5]['number'], '4')

    def test_handwriting_touching_a_number_is_reported(self):
        clean, scribbled = cell('24'), cell('24')
        ImageDraw.Draw(scribbled).line((17, 4, 26, 52), fill='black', width=3)
        for image, expected in ((clean, False), (scribbled, True)):
            report = {}
            number_glyphs(image, 'top', report)
            self.assertEqual(report.get('disturbed'), expected)

