"""Infer repeated coloured block fills from enclosed, unnumbered cells."""
from collections import defaultdict


def colored_blocks(crops, rows, cols, edges):
    vertical, horizontal = edges
    groups = defaultdict(list)
    for i, crop in enumerate(crops):
        r, c = divmod(i, cols)
        if not all((vertical[r, c], vertical[r, c+1], horizontal[r, c], horizontal[r+1, c])):
            continue
        rgb = crop.convert('RGB')
        # Exclude grid strokes, but retain enough of a directional marker to
        # associate its background with the other blocked cells.
        inner = rgb.crop((rgb.width*.12, rgb.height*.12, rgb.width*.88, rgb.height*.88))
        pixels = list(inner.get_flattened_data() if hasattr(inner, 'get_flattened_data') else inner.getdata())
        bins = defaultdict(list)
        for pixel in pixels:
            bins[tuple(channel//24 for channel in pixel)].append(pixel)
        dominant = max(bins.values(), key=len)
        if len(dominant) < len(pixels)*.55:
            continue
        color = tuple(sum(p[ch] for p in dominant)/len(dominant) for ch in range(3))
        if max(color)-min(color) < 30 or min(color) > 225:
            continue
        # A number/letter in the label corner is positive evidence of a
        # playable shaded cell. Do not mistake answer shading for a block.
        corner = rgb.crop((rgb.width*.06, rgb.height*.06, rgb.width*.48, rgb.height*.43)).convert('L')
        hist = corner.histogram()
        has_label = sum(hist[:110]) > max(2, corner.width*corner.height*.012)
        top = rgb.crop((rgb.width*.04, rgb.height*.03, rgb.width*.55, rgb.height*.18)).convert('L')
        center = rgb.crop((rgb.width*.35, rgb.height*.35, rgb.width*.65, rgb.height*.65)).convert('L')
        marker = sum(center.histogram()[:110]) > center.width*center.height*.35 and sum(top.histogram()[:110]) <= max(2, top.width*top.height*.025)
        has_label = has_label and not marker
        key = tuple(round(channel/24) for channel in color)
        groups[key].append((i, has_label))
    result = set()
    for group in groups.values():
        blank = [i for i, label in group if not label]
        # Infer a block palette only when repeated blank cells dominate it.
        if (len(blank) >= 3 and len(blank)/len(group) >= .8
                and len({i//cols for i in blank}) > 1
                and len({i%cols for i in blank}) > 1):
            result.update(blank)
    return result


def photo_blocks(crops):
    """Unnumbered cells filled with a uniform tint in an evened-out photo.

    Camera colour varies from cell to cell, so tints cannot be grouped into a
    palette. Every playable codeword cell carries a printed number, so a tinted
    cell without one is a block; shaded answer cells keep their numbers.
    """
    result = set()
    for i, crop in enumerate(crops):
        gray = crop.convert('L')
        inner = gray.crop((gray.width*.15, gray.height*.15, gray.width*.85, gray.height*.85))
        hist = inner.histogram()
        count = inner.width * inner.height
        running, median = 0, 255
        for value, amount in enumerate(hist):
            running += amount
            if running * 2 >= count:
                median = value
                break
        # Near-black cells are found as blocks elsewhere; mid-dark tints such as teal are found here.
        if median >= 240 or median < 60:
            continue
        uniform = sum(hist[max(0, median-18):median+19]) / count
        width, height = gray.size
        data = list(gray.get_flattened_data() if hasattr(gray, 'get_flattened_data') else gray.getdata())
        # Ink is darker than the tint itself, which may be fairly dark.
        threshold = min(110, median - 40)
        dark = [[value < threshold for value in data[y*width:(y+1)*width]] for y in range(height)]
        # A slightly misaligned crop carries a sliver of the grid stroke along
        # its top or left edge. Strokes span the cell; printed digits do not.
        top, left = 0, 0
        while top < height // 4 and sum(dark[top]) > width * .5:
            top += 1
        while left < width // 4 and sum(row[left] for row in dark) > height * .5:
            left += 1
        y0, y1 = top + round(height*.04), top + round(height*.41)
        x0, x1 = left + round(width*.04), left + round(width*.46)
        ink = sum(dark[y][x] for y in range(y0, min(y1, height)) for x in range(x0, min(x1, width)))
        if uniform >= .6 and ink <= max(2, (x1-x0)*(y1-y0)*.012):
            result.add(i)
    return result
