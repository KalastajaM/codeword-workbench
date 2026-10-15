import unittest
from PIL import Image, ImageDraw
from app.colored_blocks import colored_blocks, photo_blocks


class ColoredBlockTests(unittest.TestCase):
    def test_repeated_pink_blocks_and_arrow_preserve_numbered_blue_cells(self):
        crops = [Image.new('RGB', (100, 100), '#f5b2b6') for _ in range(4)]
        ImageDraw.Draw(crops[3]).polygon([(18, 18), (80, 50), (18, 82), (40, 50)], fill='#292929')
        for _ in range(5):
            cell = Image.new('RGB', (100, 100), '#e0f1f4')
            ImageDraw.Draw(cell).rectangle((9, 7, 13, 24), fill='black')
            crops.append(cell)
        edges = ({(r, c): True for r in range(3) for c in range(4)}, {(r, c): True for r in range(4) for c in range(3)})
        self.assertEqual(colored_blocks(crops, 3, 3, edges), {0, 1, 2, 3})
        edges[0][0, 1] = False
        self.assertEqual(colored_blocks(crops, 3, 3, edges), set())

    def test_numbered_cells_of_same_fill_are_not_blocked(self):
        crops = [Image.new('RGB', (100, 100), '#f5b2b6') for _ in range(5)]
        ImageDraw.Draw(crops[-1]).rectangle((9, 7, 13, 24), fill='black')
        crops.append(Image.new('RGB', (100, 100), 'white'))
        edges = ({(r, c): True for r in range(2) for c in range(4)}, {(r, c): True for r in range(3) for c in range(3)})
        self.assertEqual(colored_blocks(crops, 2, 3, edges), {0, 1, 2, 3})

    def test_photo_blocks_are_unnumbered_pale_tints(self):
        tint, white = (205, 222, 214), (255, 255, 255)
        crops = [Image.new('RGB', (80, 80), tint), Image.new('RGB', (80, 80), white),
                 Image.new('RGB', (80, 80), tint), Image.new('RGB', (80, 80), (30, 30, 30))]
        # A printed number marks a shaded answer cell, which stays playable.
        ImageDraw.Draw(crops[2]).rectangle((7, 6, 10, 22), fill='black')
        self.assertEqual(photo_blocks(crops), {0})
