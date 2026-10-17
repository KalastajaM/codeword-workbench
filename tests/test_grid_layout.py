"""Placing black cells for a target number of words."""
import random
import unittest

from app.grid_layout import check_target, measure, plan


def open_grid(rows, cols, black=(), locked=()):
    return dict(rows=rows, cols=cols, cells=[dict(black=i in black, number='1' if i in locked else '', letter='')
                                             for i in range(rows * cols)])


class TargetTests(unittest.TestCase):
    def test_target_is_checked_against_the_grid(self):
        self.assertEqual(check_target(dict(words=20, shortest=3, longest=12), 10, 10),
                         dict(words=20, shortest=3, longest=10, mirror=True))
        for bad in [dict(words=0), dict(words=True), dict(words=5, shortest=1), dict(words=5, shortest=6, longest=4),
                    dict(words=5, shortest=11), dict(words=5, mirror='yes'), []]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                check_target(bad, 10, 10)

    def test_measure_counts_rule_breaks(self):
        # A 3 × 3 ring: four words of three letters, all connected.
        self.assertEqual(measure(3, 3, {4}, 3, 3), (0, 4, [3, 3, 3, 3]))
        # Four words one letter too short.
        self.assertEqual(measure(3, 3, {4}, 4, 4)[0], 4)
        # The middle column black: two words in two separate pieces.
        self.assertEqual(measure(3, 3, {1, 4, 7}, 3, 3), (1, 2, [3, 3]))
        # A corner cut off: it is in no word and a piece of its own; two words are too short.
        self.assertEqual(measure(3, 3, {1, 3}, 3, 3)[0], 4)


class PlanTests(unittest.TestCase):
    def test_open_grid_reaches_the_target_with_every_rule_met(self):
        for rows, words, shortest, longest in [(10, 20, 3, 7), (7, 10, 3, 5), (13, 28, 3, 8)]:
            with self.subTest(rows=rows, words=words):
                black, breaks, count, lengths = plan(open_grid(rows, rows), check_target(
                    dict(words=words, shortest=shortest, longest=longest), rows, rows), random.Random(1), seconds=1)
                self.assertEqual(breaks, 0)
                self.assertLessEqual(abs(count - words), 1)
                self.assertTrue(shortest <= min(lengths) and max(lengths) <= longest)
                n = rows * rows
                self.assertTrue(all(n - 1 - i in black for i in black), 'Black cells are mirrored')

    def test_drawn_black_cells_stay_and_numbered_cells_stay_open(self):
        black, breaks, count, _ = plan(open_grid(9, 9, black={0}, locked={40, 41}),
                                       check_target(dict(words=14, shortest=3, longest=6, mirror=False), 9, 9),
                                       random.Random(2), seconds=1)
        self.assertIn(0, black)
        self.assertFalse({40, 41} & black)
        self.assertEqual(breaks, 0)

    def test_unreachable_count_returns_the_closest_valid_layout(self):
        black, breaks, count, lengths = plan(open_grid(10, 10), check_target(dict(words=60, shortest=3, longest=7), 10, 10),
                                             random.Random(1), seconds=1)
        self.assertEqual(breaks, 0)
        self.assertLess(count, 60)

    def test_needed_word_lengths_are_provided(self):
        black, breaks, count, lengths = plan(open_grid(9, 9), check_target(dict(words=14, shortest=3, longest=7), 9, 9),
                                             random.Random(3), seconds=1, need={7: 2})
        self.assertEqual(breaks, 0)
        self.assertGreaterEqual(lengths.count(7), 2)


if __name__ == '__main__':
    unittest.main()
