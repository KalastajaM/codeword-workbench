import base64
import io
import math
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

from app.ocr import recognize
from app.straighten import HANDLE_NAMES, MARGIN, outline, straighten, straighten_image

ROWS, COLS, PITCH = 23, 20, 50
BLACK = {(0, 3), (2, 7), (5, 0), (6, 14), (9, 9), (11, 4), (22, 19), (17, 12)}
# Pale tints as a camera sees a printed coloured block, plus one numbered tint.
TINTED = {(1, 1), (3, 10), (8, 5), (13, 16), (19, 2), (20, 8)}
NUMBERED_TINT = (14, 6)
# Lifts the middle of the page by about half a cell.
WAVE = 24


def data_url(image):
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode()


def photographed(x, y, hook=0, wave=0):
    """Map flat grid coordinates to a tilted, bent photograph of the page.

    `hook` curls the top border down near the spine, a shape a single
    midpoint per edge cannot follow. `wave` lifts the middle of the page
    while its borders stay put, which no edge handle can describe.
    """
    width, height = COLS * PITCH, ROWS * PITCH
    y -= wave * math.sin(math.pi * x / width) ** 2 * math.sin(math.pi * y / height)
    y += hook * (max(0, x / width - .6) / .4) ** 2 * (1 - y / height) ** 2
    # A curled page compresses some columns more than others; no single
    # perspective map can make these widths equal again.
    x += 22 * math.sin(2 * math.pi * x / width)
    # The page bows near its right and top edges, as a magazine does near the spine.
    x += 18 * math.sin(math.pi * y / height) * (x / width) ** 2
    y -= 14 * math.sin(math.pi * x / width) * (1 - y / height) ** 2
    # Camera tilt: a projective transform shrinks the far (top) side.
    denominator = 1 + .0003 * y + .00012 * x
    return (120 + (x + .06 * y) / denominator * 1.05, 90 + (y + .03 * x) / denominator)


def photo_fixture(hook=0, wave=0):
    def place(x, y):
        return photographed(x, y, hook, wave)
    image = Image.new('RGB', (1300, 1000), (205, 200, 190))
    draw = ImageDraw.Draw(image)
    width, height = COLS * PITCH, ROWS * PITCH
    draw.polygon([place(x, y) for x, y in
                  [(t, 0) for t in range(0, width + 1, 10)] + [(width, t) for t in range(0, height + 1, 10)]
                  + [(t, height) for t in range(width, -1, -10)] + [(0, t) for t in range(height, -1, -10)]],
                 fill='white')
    for cells, fill in ((BLACK, 'black'), (TINTED | {NUMBERED_TINT}, (196, 214, 205))):
        for r, c in cells:
            quad = [(c * PITCH + dx, r * PITCH + dy) for dx, dy in
                    [(0, 0), (PITCH, 0), (PITCH, PITCH), (0, PITCH)]]
            draw.polygon([place(*p) for p in quad], fill=fill)
    r, c = NUMBERED_TINT
    corner = place(c * PITCH + 6, r * PITCH + 5)
    draw.rectangle((corner[0], corner[1], corner[0] + 3, corner[1] + 13), fill='black')
    for c in range(COLS + 1):
        draw.line([place(c * PITCH, t) for t in range(0, height + 1, 6)], fill='black', width=3)
    for r in range(ROWS + 1):
        draw.line([place(t, r * PITCH) for t in range(0, width + 1, 6)], fill='black', width=3)
    handles = {}
    for name, (fx, fy) in zip(HANDLE_NAMES, [(0, 0), (.5, 0), (1, 0), (1, .5), (1, 1), (.5, 1), (0, 1), (0, .5)]):
        x, y = place(fx * width, fy * height)
        handles[name] = {'x': x / image.width, 'y': y / image.height}
    return image, handles


def edge_points(count, hook=0):
    """Handles with `count` bend points per edge, sampled from the photographed page."""
    image, handles = photo_fixture(hook)
    width, height = COLS * PITCH, ROWS * PITCH
    steps = [(k + 1) / (count + 1) for k in range(count)]
    for name, at in (('top', lambda t: (t, 0)), ('right', lambda t: (1, t)),
                     ('bottom', lambda t: (t, 1)), ('left', lambda t: (0, t))):
        points = [photographed(at(t)[0] * width, at(t)[1] * height, hook) for t in steps]
        handles[name] = [{'x': x / image.width, 'y': y / image.height} for x, y in points]
    return image, handles


def top_border_error(flat):
    """Largest distance of the flattened top border from where an even grid puts it."""
    gray = flat.convert('L')
    pixels = gray.load()
    expected = MARGIN / (1 + 2*MARGIN) * flat.height
    errors = []
    for k in range(1, 20):
        x = round(flat.width * k / 20)
        y = min(range(round(expected) - 30, round(expected) + 31),
                key=lambda y: sum(pixels[x + d, y] for d in range(-2, 3)))
        errors.append(abs(y - expected))
    return max(errors)


class StraightenTests(unittest.TestCase):
    def test_flattening_removes_tilt_and_bow(self):
        photo, handles = photo_fixture()
        flat = straighten_image(photo, handles)
        with patch('app.ocr.available', return_value=False):
            result = recognize({'image': data_url(flat), 'autoDetect': True, 'photo': True})
        # Uneven column widths remain after flattening alone.
        self.assertNotEqual((result['rows'], result['cols']), (ROWS, COLS))

    def test_uneven_curled_photo_becomes_an_even_recognizable_grid(self):
        photo, handles = photo_fixture()
        result = straighten({'image': data_url(photo), 'handles': handles})
        self.assertEqual((result['rows'], result['cols']), (ROWS, COLS))
        with patch('app.ocr.available', return_value=False):
            recognized = recognize({'image': result['image'], 'rows': result['rows'], 'cols': result['cols'],
                                    'bounds': result['bounds'], 'photo': True})
        black = {divmod(i, COLS) for i, cell in enumerate(recognized['cells']) if cell['black']}
        self.assertEqual(black, BLACK | TINTED)
        self.assertFalse(any(cell['clue'] for cell in recognized['cells']))
        # Uniform target cells: recognition at the returned bounds is exact.
        flat = Image.open(io.BytesIO(base64.b64decode(result['image'].split(',', 1)[1])))
        self.assertAlmostEqual(result['bounds']['x'] * flat.width, (1 - result['bounds']['width']) * flat.width / 2, delta=2)

    def test_a_wave_inside_the_page_is_followed_cell_by_cell(self):
        photo, handles = photo_fixture(wave=WAVE)
        result = straighten({'image': data_url(photo), 'handles': handles})
        self.assertEqual((result['rows'], result['cols']), (ROWS, COLS))
        with patch('app.ocr.available', return_value=False):
            recognized = recognize({'image': result['image'], 'rows': ROWS, 'cols': COLS,
                                    'bounds': result['bounds'], 'photo': True})
        self.assertEqual({divmod(i, COLS) for i, cell in enumerate(recognized['cells']) if cell['black']}, BLACK | TINTED)

    def test_photo_mode_never_reads_letters(self):
        photo, handles = photo_fixture()
        result = straighten({'image': data_url(photo), 'handles': handles})
        whitelists = []

        def sheet(image, whitelist, diagnostics, psm=6):
            whitelists.append(whitelist)
            return []
        with patch('app.ocr.available', return_value=True), patch('app.ocr._recognize_sheet', sheet):
            recognized = recognize({'image': result['image'], 'rows': result['rows'], 'cols': result['cols'],
                                    'bounds': result['bounds'], 'photo': True})
        self.assertTrue(whitelists)
        self.assertFalse(any('A' in whitelist for whitelist in whitelists))
        self.assertTrue(any('handwritten letters are not read' in line for line in recognized['diagnostics']))

    def test_payload_returns_jpeg_data_url_within_size_cap(self):
        photo, handles = photo_fixture()
        photo = photo.resize((3000, 2300))
        result = straighten({'image': data_url(photo), 'handles': handles})
        self.assertTrue(result['image'].startswith('data:image/jpeg;base64,'))
        flat = Image.open(io.BytesIO(base64.b64decode(result['image'].split(',', 1)[1])))
        self.assertLessEqual(max(flat.size), 2000)
        self.assertEqual((result['width'], result['height']), flat.size)

    def test_unclear_lines_still_return_the_flattened_image(self):
        blank = Image.new('RGB', (600, 500), 'white')
        handles = {name: {'x': x, 'y': y} for name, (x, y) in zip(
            HANDLE_NAMES, [(.1, .1), (.5, .1), (.9, .1), (.9, .5), (.9, .9), (.5, .9), (.1, .9), (.1, .5)])}
        result = straighten({'image': data_url(blank), 'handles': handles})
        self.assertIsNone(result['rows'])
        self.assertTrue(result['image'].startswith('data:image/jpeg;base64,'))

    def test_phone_orientation_tag_is_applied_like_the_browser_does(self):
        # Phones store pixels sideways plus an EXIF "rotate 90" tag; browsers
        # display the rotated image, so handles are placed in that frame.
        photo, handles = photo_fixture()
        sideways = photo.transpose(Image.Transpose.ROTATE_90)
        exif = sideways.getexif()
        exif[0x0112] = 6
        buffer = io.BytesIO()
        sideways.save(buffer, format='JPEG', quality=95, exif=exif.tobytes())
        image = 'data:image/jpeg;base64,' + base64.b64encode(buffer.getvalue()).decode()
        result = straighten({'image': image, 'handles': handles})
        self.assertEqual((result['rows'], result['cols']), (ROWS, COLS))

    def test_more_edge_points_follow_a_curled_border(self):
        photo, one = photo_fixture(hook=44)
        _, many = edge_points(5, hook=44)
        rough, close = top_border_error(straighten_image(photo, one)), top_border_error(straighten_image(photo, many))
        # A single midpoint per edge leaves the hooked corner of the border bent.
        self.assertGreater(rough, 4)
        self.assertLessEqual(close, 2)

    def test_outline_passes_through_every_edge_point_in_any_order(self):
        photo, handles = edge_points(4)
        handles['top'] = handles['top'][::-1]
        border = outline(handles, photo.width, photo.height, steps=400)
        for name in ('top', 'right', 'bottom', 'left'):
            for point in handles[name]:
                with self.subTest(edge=name):
                    gap = min(math.dist((point['x'] * photo.width, point['y'] * photo.height),
                                        (x * photo.width, y * photo.height)) for x, y in border[name])
                    self.assertLess(gap, 2)

    def test_straight_edges_need_no_points(self):
        photo, handles = photo_fixture()
        handles.update(top=[], right=[], bottom=[], left=[])
        self.assertEqual(straighten({'image': data_url(photo), 'handles': handles})['image'][:22], 'data:image/jpeg;base64')

    def test_a_corner_cut_off_by_the_photo_may_sit_just_outside_it(self):
        photo, handles = photo_fixture()
        cropped = photo.crop((0, 0, 1040, 1000))
        scale = photo.width / cropped.width
        moved = {name: ([{'x': p['x'] * scale, 'y': p['y']} for p in value] if isinstance(value, list)
                        else {'x': value['x'] * scale, 'y': value['y']}) for name, value in handles.items()}
        self.assertGreater(moved['topRight']['x'], 1)
        result = straighten({'image': data_url(cropped), 'handles': moved})
        self.assertEqual((result['rows'], result['cols']), (ROWS, COLS))

    def test_invalid_handles_are_rejected(self):
        photo, handles = photo_fixture()
        image = data_url(photo)
        missing = dict(handles)
        del missing['left']
        outside = dict(handles, topLeft={'x': -.2, 'y': .1})
        collapsed = {name: {'x': .5, 'y': .5} for name in HANDLE_NAMES}
        crossed = dict(handles, topLeft=handles['bottomRight'], bottomRight=handles['topLeft'])
        _, many = edge_points(3)
        crowded = dict(many, top=many['top'] + [dict(many['top'][0], x=many['top'][0]['x'] + .001)])
        beyond = dict(many, top=many['top'] + [{'x': .01, 'y': handles['topLeft']['y']}])
        too_many = dict(many, left=many['left'] * 3)
        for bad in [None, [], missing, outside, collapsed, crossed, crowded, beyond, too_many, dict(handles, top='a'),
                    dict(handles, top={'x': 'a', 'y': .1}), dict(handles, top={'x': float('nan'), 'y': .1})]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                straighten({'image': image, 'handles': bad})
        with self.assertRaises(ValueError):
            straighten({'image': 'garbage', 'handles': handles})


if __name__ == '__main__':
    unittest.main()
