"""Find the largest regular printed grid using local, bounded image analysis."""
from PIL import Image


def _line_centres(scores, threshold=.45):
    runs = []
    for index, score in enumerate(scores):
        if score >= threshold:
            if not runs or index > runs[-1][-1] + 1:
                runs.append([])
            runs[-1].append(index)
    return [sum(run) / len(run) for run in runs
            if len(run) <= max(12, len(scores) * .015)]


def _regular_run(points):
    best = None
    # A printed grid has repeated strokes. Permit noisy extra strokes, but never
    # invent missing rows from an assumed page size or particular publication.
    for start_index, start in enumerate(points):
        for second in points[start_index + 1:]:
            step = second - start
            if step < 12:
                continue
            sequence = [start, second]
            for count in range(2, 41):
                expected = start + count * step
                candidates = [point for point in points if point > sequence[-1] + step * .5
                              and abs(point - expected) <= step * .14]
                if not candidates:
                    break
                sequence.append(min(candidates, key=lambda point: abs(point - expected)))
                # Re-estimate pitch as stroke thickness can bias the outside border.
                step = (sequence[-1] - sequence[0]) / (len(sequence) - 1)
            if len(sequence) >= 4:
                score = (len(sequence) - 1) * (sequence[-1] - sequence[0])
                if best is None or score > best[0]:
                    best = score, sequence
    if best is None:
        raise ValueError('No regular puzzle grid was found. Set dimensions and image alignment manually, then recognize the grid.')
    sequence = best[1]
    # Outside frames are often much thicker. Fit only the interior grid strokes.
    samples = list(enumerate(sequence))[1:-1]
    mean_i = sum(i for i, _ in samples) / len(samples)
    mean_p = sum(p for _, p in samples) / len(samples)
    denominator = sum((i - mean_i) ** 2 for i, _ in samples)
    step = sum((i - mean_i) * (p - mean_p) for i, p in samples) / denominator
    origin = mean_p - step * mean_i
    return origin, step, len(sequence) - 1


def detect_grid(image):
    sample = image.convert('L')
    sample.thumbnail((1400, 1400), Image.Resampling.LANCZOS)
    width, height = sample.size
    pixels = sample.load()
    # Measure narrow strokes against their neighbours. Raw darkness merges
    # entire bands of dark photographs/filled blocks and loses thin borders.
    columns = [sum(max(pixels[max(0, x-3), y], pixels[min(width-1, x+3), y])
                   - pixels[x, y] > 35 for y in range(height)) / height for x in range(width)]
    rows = [sum(max(pixels[x, max(0, y-3)], pixels[x, min(height-1, y+3)])
                - pixels[x, y] > 35 for x in range(width)) / width for y in range(height)]
    left, cw, cols = _regular_run(_line_centres(columns, .25))
    top, ch, row_count = _regular_run(_line_centres(rows, .25))
    # Keep the largest connected group of bordered cells. Full-width row
    # thresholds cut off narrow arms; disconnected number keys must not extend
    # the puzzle bounds even when they happen to share its pitch.
    bounds = dict(x=max(0, left)/width, y=max(0, top)/height,
                  width=min(cw*cols, width-max(0, left))/width,
                  height=min(ch*row_count, height-max(0, top))/height)
    vertical, horizontal = grid_edges(sample, row_count, cols, bounds)
    components = bordered_components(row_count, cols, (vertical, horizontal))
    if components:
        main = max(components, key=len)
        r0, r1 = min(r for r, c in main), max(r for r, c in main)
        c0, c1 = min(c for r, c in main), max(c for r, c in main)
        if len(main) >= 12 and r1-r0 >= 2 and c1-c0 >= 2:
            left += c0*cw
            top += r0*ch
            cols, row_count = c1-c0+1, r1-r0+1
    if not .65 <= cw / ch <= 1.55:
        raise ValueError('The detected grid has inconsistent spacing. Set dimensions and image alignment manually.')
    if left < 0 or top < 0 or left + cw * cols > width or top + ch * row_count > height:
        raise ValueError('The grid reaches outside the image. Set dimensions and image alignment manually.')
    return row_count, cols, {'x': left / width, 'y': top / height,
                            'width': cw * cols / width, 'height': ch * row_count / height}


def bordered_components(rows, cols, edges):
    """Connected groups of cells supported by visible grid borders."""
    vertical, horizontal = edges
    pending = {(r, c) for r in range(rows) for c in range(cols)
               if sum((vertical[r, c], vertical[r, c+1],
                       horizontal[r, c], horizontal[r+1, c])) >= 3}
    components = []
    while pending:
        seed = pending.pop()
        component, frontier = {seed}, [seed]
        while frontier:
            r, c = frontier.pop()
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                other = r+dr, c+dc
                if other in pending:
                    pending.remove(other)
                    component.add(other)
                    frontier.append(other)
        components.append(component)
    return components


def detached_grid_cells(rows, cols, edges):
    """Exclude separate rectangular tables inside the main grid bounds.

    Require a substantial main puzzle and a fully bordered secondary table;
    isolated cells or broken strokes are not enough to discard puzzle content.
    """
    components = bordered_components(rows, cols, edges)
    if not components:
        return set()
    main = max(components, key=len)
    if len(main) < 12:
        return set()
    vertical, horizontal = edges
    detached = set()
    for component in components:
        if component is main or len(component) < 8:
            continue
        r0, r1 = min(r for r, c in component), max(r for r, c in component)
        c0, c1 = min(c for r, c in component), max(c for r, c in component)
        if len(component) != (r1-r0+1)*(c1-c0+1):
            continue
        if all(vertical[r, c] and vertical[r, c+1] and
               horizontal[r, c] and horizontal[r+1, c] for r, c in component):
            detached.update(r*cols+c for r, c in component)
    return detached


def cell_appearance(crop):
    """Distinguish inset blocks, photograph cells, and softly shaded answer cells."""
    rgb = crop.convert('RGB')
    gray = rgb.convert('L')
    hist = gray.histogram()
    count = rgb.width * rgb.height
    # Printed cells have a few flat colours, even with antialiased digits. A
    # photographic clue has many colours across a substantial part of the cell.
    # Fixed bins ignore small JPEG colour fluctuations. Adaptive quantization
    # invents eight equally common shades even for a nearly uniform brown block.
    quantized = rgb.point(lambda value: (value // 32) * 32)
    palette = sorted((amount for amount, _ in quantized.getcolors(count)), reverse=True)
    flat_fraction = sum(palette[:2]) / count
    midtones = sum(hist[60:205]) / count
    clue = flat_fraction < .80 and midtones > .08
    centre = gray.crop((gray.width * .25, gray.height * .25, gray.width * .75, gray.height * .75))
    centre_hist = centre.histogram()
    black = not clue and sum(centre_hist[:100]) / (centre.width * centre.height) > .90
    # Off-white coloured backgrounds are hints, not blocked cells. Ignore text.
    light = [pixel for pixel in (rgb.get_flattened_data() if hasattr(rgb, 'get_flattened_data') else rgb.getdata())
             if .299*pixel[0]+.587*pixel[1]+.114*pixel[2] > 145]
    highlight = False
    if not black and not clue and len(light) > count * .55:
        mean = [sum(pixel[channel] for pixel in light) / len(light) for channel in range(3)]
        highlight = min(mean) < 242 and max(mean) - min(mean) > 4
    return black, clue, highlight


def grid_edges(image, rows, cols, bounds, tolerance=.04):
    """Measure actual thin strokes, rather than darkness within cell textures.

    `tolerance` is how far, as a fraction of the cell, a stroke may sit from
    its expected position; straightened photos keep a few pixels of error.
    """
    gray = image.convert('L')
    pixels = gray.load()
    left, top = bounds['x'] * gray.width, bounds['y'] * gray.height
    cw, ch = bounds['width'] * gray.width / cols, bounds['height'] * gray.height / rows
    dx, dy = max(2, round(cw*.06)), max(2, round(ch*.06))
    vertical, horizontal = {}, {}
    for r in range(rows):
        y0, y1 = max(0, round(top+(r+.15)*ch)), min(gray.height, round(top+(r+.85)*ch))
        for c in range(cols+1):
            xx = left+c*cw
            strengths = [sum(max(pixels[max(0, x-dx), y], pixels[min(gray.width-1, x+dx), y])
                             - pixels[x, y] > 30 for y in range(y0, y1)) / max(1, y1-y0)
                         for x in range(max(0, round(xx-cw*tolerance)), min(gray.width, round(xx+cw*tolerance)+1))]
            vertical[r, c] = max(strengths, default=0) >= .55
    for r in range(rows+1):
        yy = top+r*ch
        for c in range(cols):
            x0, x1 = max(0, round(left+(c+.15)*cw)), min(gray.width, round(left+(c+.85)*cw))
            strengths = [sum(max(pixels[x, max(0, y-dy)], pixels[x, min(gray.height-1, y+dy)])
                             - pixels[x, y] > 30 for x in range(x0, x1)) / max(1, x1-x0)
                         for y in range(max(0, round(yy-ch*tolerance)), min(gray.height, round(yy+ch*tolerance)+1))]
            horizontal[r, c] = max(strengths, default=0) >= .55
    return vertical, horizontal


def missing_grid_regions(image, rows, cols, bounds, key_cells=frozenset(), edges=None):
    """Find rectangular illustrations by absent internal cell borders."""
    vertical, horizontal = edges if edges is not None else grid_edges(image, rows, cols, bounds)
    adjacency = {}

    def connect(a, b):
        adjacency.setdefault(a, set()).add(b)
        adjacency.setdefault(b, set()).add(a)

    for r in range(rows):
        for c in range(cols):
            i = r*cols+c
            if c+1 < cols and not vertical[r, c+1]:
                connect(i, i+1)
            if r+1 < rows and not horizontal[r+1, c]:
                connect(i, i+cols)
    pending, clues = set(adjacency), set()
    while pending:
        component = {pending.pop()}
        frontier = list(component)
        while frontier:
            for other in adjacency[frontier.pop()]:
                if other in pending:
                    pending.remove(other)
                    component.add(other)
                    frontier.append(other)
        r0, r1 = min(i//cols for i in component), max(i//cols for i in component)
        c0, c1 = min(i%cols for i in component), max(i%cols for i in component)
        area = (r1-r0+1)*(c1-c0+1)
        # An entirely borderless/faint board is not evidence of an illustration.
        # Leave manual grids playable when their strokes fall below our contrast threshold.
        enclosed_key = {i for i in key_cells if r0 <= i//cols <= r1 and c0 <= i%cols <= c1}
        if area < rows*cols and r1 > r0 and c1 > c0 and len(component | enclosed_key) >= area*.65:
            clues.update(r*cols+c for r in range(r0, r1+1) for c in range(c0, c1+1))
    return clues
