"""Flatten a photographed grid from corner and edge handles, then even out its cells."""
import base64
import io
import math

from .ocr import decode_image

HANDLE_NAMES = ('topLeft', 'top', 'topRight', 'right', 'bottomRight', 'bottom', 'bottomLeft', 'left')
MAX_SIDE = 2000
MESH_TILES = 40
# Keep some of the photo around the outline so its border strokes stay whole.
MARGIN = .02
BANDS = 12


def _handles(value, width, height):
    if not isinstance(value, dict) or set(value) != set(HANDLE_NAMES):
        raise ValueError('Straightening needs the four grid corners and four edge midpoints.')
    points = {}
    for name in HANDLE_NAMES:
        point = value[name]
        try:
            x, y = float(point['x']), float(point['y'])
        except (KeyError, TypeError, ValueError):
            raise ValueError('Each straightening handle needs x and y fractions.') from None
        if not (math.isfinite(x) and math.isfinite(y)) or not (0 <= x <= 1 and 0 <= y <= 1):
            raise ValueError('Straightening handles must lie inside the image.')
        points[name] = (x * width, y * height)
    corners = [points[name] for name in ('topLeft', 'topRight', 'bottomRight', 'bottomLeft')]
    turns = [(b[0]-a[0])*(c[1]-b[1]) - (b[1]-a[1])*(c[0]-b[0])
             for a, b, c in zip(corners, corners[1:] + corners[:1], corners[2:] + corners[:2])]
    area = sum(a[0]*b[1] - b[0]*a[1] for a, b in zip(corners, corners[1:] + corners[:1])) / 2
    # Corners must run clockwise (on screen) around a convex outline of real size.
    if min(turns) <= 0 or area < width * height * .01:
        raise ValueError('Place the four corners on the grid outline: top left, top right, bottom right, bottom left.')
    return points


def _edge(start, middle, end):
    """Quadratic curve from start to end that passes through middle at t=0.5."""
    control = (2*middle[0] - (start[0]+end[0])/2, 2*middle[1] - (start[1]+end[1])/2)

    def at(t):
        a, b, c = (1-t)**2, 2*t*(1-t), t*t
        return (a*start[0] + b*control[0] + c*end[0], a*start[1] + b*control[1] + c*end[1])
    return at


def _length(curve, steps=64):
    points = [curve(i/steps) for i in range(steps+1)]
    return sum(math.dist(a, b) for a, b in zip(points, points[1:]))


def _perspective(tl, tr, br, bl):
    """Projective map from the unit square to the corner quadrilateral (Heckbert)."""
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = tl, tr, br, bl
    dx1, dx2, dx3 = x1-x2, x3-x2, x0-x1+x2-x3
    dy1, dy2, dy3 = y1-y2, y3-y2, y0-y1+y2-y3
    det = dx1*dy2 - dx2*dy1
    g, h = (dx3*dy2 - dx2*dy3) / det, (dx1*dy3 - dx3*dy1) / det
    a, b, d, e = x1-x0+g*x1, x3-x0+h*x3, y1-y0+g*y1, y3-y0+h*y3

    def at(u, v):
        w = g*u + h*v + 1
        return ((a*u + b*v + x0) / w, (d*u + e*v + y0) / w)
    return at


def _bend(middle, start, end, plane_middle):
    """Offset of a bowed edge midpoint across its chord; ignore sliding along it."""
    cx, cy = end[0]-start[0], end[1]-start[1]
    length = math.hypot(cx, cy)
    nx, ny = -cy/length, cx/length
    amount = (middle[0]-plane_middle[0])*nx + (middle[1]-plane_middle[1])*ny
    return amount*nx, amount*ny


def straighten_image(image, handles):
    """Undo camera perspective from the corners, then page bowing from the edge midpoints."""
    from PIL import Image
    p = _handles(handles, image.width, image.height)
    top = _edge(p['topLeft'], p['top'], p['topRight'])
    bottom = _edge(p['bottomLeft'], p['bottom'], p['bottomRight'])
    left = _edge(p['topLeft'], p['left'], p['bottomLeft'])
    right = _edge(p['topRight'], p['right'], p['bottomRight'])
    tl, tr, br, bl = p['topLeft'], p['topRight'], p['bottomRight'], p['bottomLeft']
    plane = _perspective(tl, tr, br, bl)
    # Equal steps on a tilted page shrink with distance, so cells stay evenly
    # spaced only under the projective map, not under arc-length interpolation.
    bends = [_bend(p['top'], tl, tr, plane(.5, 0)), _bend(p['bottom'], bl, br, plane(.5, 1)),
             _bend(p['left'], tl, bl, plane(0, .5)), _bend(p['right'], tr, br, plane(1, .5))]

    def source(u, v):
        x, y = plane(u, v)
        bu, bv = 4*u*(1-u), 4*v*(1-v)
        weights = ((1-v)*bu, v*bu, (1-u)*bv, u*bv)
        return (x + sum(w*b[0] for w, b in zip(weights, bends)),
                y + sum(w*b[1] for w, b in zip(weights, bends)))

    width = (_length(top) + _length(bottom)) / 2
    height = (_length(left) + _length(right)) / 2
    scale = min(1, MAX_SIDE / (max(width, height) * (1 + 2*MARGIN)))
    width = max(1, round(width * scale * (1 + 2*MARGIN)))
    height = max(1, round(height * scale * (1 + 2*MARGIN)))
    cols, rows = min(MESH_TILES, width), min(MESH_TILES, height)
    xs = [round(i * width / cols) for i in range(cols+1)]
    ys = [round(j * height / rows) for j in range(rows+1)]
    span = 1 + 2*MARGIN

    def u(i):
        return i/cols*span - MARGIN

    def v(j):
        return j/rows*span - MARGIN
    mesh = []
    for j in range(rows):
        for i in range(cols):
            u0, u1, v0, v1 = u(i), u(i+1), v(j), v(j+1)
            # Pillow quads list upper left, lower left, lower right, upper right.
            quad = source(u0, v0) + source(u0, v1) + source(u1, v1) + source(u1, v0)
            mesh.append(((xs[i], ys[j], xs[i+1], ys[j+1]), quad))
    return image.transform((width, height), Image.Transform.MESH, mesh,
                           Image.Resampling.BICUBIC, fillcolor='white')


def even_lighting(image):
    """Divide out shadows and paper tint so the paper reads as white."""
    from PIL import Image, ImageFilter, ImageMath
    small = image.resize((max(1, image.width // 8), max(1, image.height // 8)), Image.Resampling.BOX)
    # The brightest nearby pixels are paper; the window spans more than a cell.
    size = max(3, min(small.size) // 24 * 2 + 1)
    paper = small.filter(ImageFilter.MaxFilter(size)).filter(ImageFilter.GaussianBlur(2))
    paper = paper.resize(image.size, Image.Resampling.BILINEAR)
    channels = []
    for ink, light in zip(image.split(), paper.split()):
        if hasattr(ImageMath, 'lambda_eval'):
            channel = ImageMath.lambda_eval(
                lambda a: a['convert'](a['min'](a['ink'] * 255 / a['max'](a['light'], 1), 255), 'L'),
                ink=ink, light=light)
        else:
            channel = ImageMath.eval('convert(min(ink * 255 / max(light, 1), 255), "L")', ink=ink, light=light)
        channels.append(channel)
    # Remove camera speckle without erasing thin grid strokes, then let
    # near-white paper become white so cells read as flat printed colours.
    even = Image.merge('RGB', channels).filter(ImageFilter.MedianFilter(3))
    return even.point(lambda value: 255 if value >= 228 else round(value * 255 / 228))


def _stroke_centres(scores):
    """(position, strength) of each stroke peak in a band profile."""
    runs = []
    for index, score in enumerate(scores):
        if score >= .2:
            if runs and index == runs[-1][-1] + 1:
                runs[-1].append(index)
            else:
                runs.append([index])
    centres = []
    for run in runs:
        if len(run) > 18:
            continue
        centre, strength = sum(run) / len(run), max(scores[i] for i in run)
        # A slightly slanted stroke splits into two nearby peaks; merge them.
        if centres and centre - centres[-1][0] < 10:
            previous, weight = centres[-1]
            centres[-1] = ((previous*weight + centre*strength) / (weight+strength), max(weight, strength))
        else:
            centres.append((centre, strength))
    return centres


def _pitch(profile, span):
    """Typical cell size: the strongest repeat in the stroke profile."""
    lo, hi = max(8, int(span / 45)), int(span / 3)
    mean = sum(profile) / len(profile)
    centred = [value - mean for value in profile]

    def repeat(lag):
        return sum(a*b for a, b in zip(centred, centred[lag:]))
    scores = {lag: repeat(lag) for lag in range(lo, hi+1)}
    best = max(scores, key=scores.get)
    # Prefer the cell size over a multiple of it when both repeat strongly.
    for divisor in (3, 2):
        lag = round(best / divisor)
        if lag >= lo and max(scores.get(lag+d, 0) for d in (-1, 0, 1)) >= .6 * scores[best]:
            return best / divisor
    return best


def _fit_lines(centres, start, end, pitch):
    """Best chain of strokes from one border to the other.

    Rewards strong strokes, penalizes cell sizes far from the typical pitch, and
    lets a chain skip strokes hidden by illustrations or blocked runs.
    """
    nodes = [(start, 0.0, .5)] + [(p, s, 0.0) for p, s in centres if start - .5*pitch < p < end + .5*pitch]
    nodes.append((end, 0.0, .5))
    nodes.sort()
    best, back = {}, {}
    for j, (pj, sj, virtual_j) in enumerate(nodes):
        if abs(pj - start) <= .5*pitch:
            best[j], back[j] = virtual_j - sj, None
        for i in range(j):
            if i not in best:
                continue
            gap = pj - nodes[i][0]
            steps = round(gap / pitch)
            if not 1 <= steps <= 8:
                continue
            deviation = (gap/steps - pitch) / pitch
            if abs(deviation) > .3:
                continue
            cost = best[i] + 20*deviation**2 + .6*(steps-1) + virtual_j - sj
            if j not in best or cost < best[j]:
                best[j], back[j] = cost, i
    finals = [j for j in best if abs(nodes[j][0] - end) <= .5*pitch]
    if not finals:
        return None
    j = min(finals, key=best.get)
    chain = []
    while j is not None:
        chain.append(nodes[j][0])
        j = back[j]
    chain.reverse()
    strengths = {p: s for p, s, virtual in nodes if not virtual}
    typical = sorted(strengths.get(p, 0) for p in chain)[len(chain)//2]
    # Inferred lines and faint strokes (drawing outlines, handwriting) only
    # bridge gaps; they must not steer the fitted grid line.
    measured = {p for p in chain if strengths.get(p, 0) >= .5 * typical > 0}
    lines = [(chain[0], chain[0] in measured)]
    for a, b in zip(chain, chain[1:]):
        steps = round((b - a) / pitch)
        lines.extend((a + (b - a) * k / steps, k == steps and b in measured) for k in range(1, steps + 1))
    return lines


def _stroke_mask(gray, vertical):
    """Thin dark strokes against their neighbours, thickened to tolerate slight slope."""
    from PIL import ImageChops, ImageFilter
    dx, dy = (3, 0) if vertical else (0, 3)
    sides = ImageChops.lighter(ImageChops.offset(gray, dx, dy), ImageChops.offset(gray, -dx, -dy))
    mask = ImageChops.subtract(sides, gray).point(lambda value: 255 if value > 35 else 0)
    return mask.filter(ImageFilter.MaxFilter(5))


def _band_lines(gray, vertical):
    """Grid line positions measured separately in several bands across the image."""
    from PIL import Image
    mask = _stroke_mask(gray, vertical)
    width, height = gray.size
    along, across = (width, height) if vertical else (height, width)
    margin = MARGIN / (1 + 2*MARGIN) * along
    def profile_of(box, size):
        profile = mask.crop(box).resize(size, Image.Resampling.BOX)
        data = profile.get_flattened_data() if hasattr(profile, 'get_flattened_data') else profile.getdata()
        return [value / 255 for value in data]
    whole = profile_of((0, 0, width, height), (width, 1) if vertical else (1, height))
    pitch = _pitch(whole, along - 2*margin)
    bands = []
    for band in range(BANDS):
        lo, hi = across*band//BANDS, across*(band+1)//BANDS
        box, size = ((0, lo, width, hi), (width, 1)) if vertical else ((lo, 0, hi, height), (1, height))
        lines = _fit_lines(_stroke_centres(profile_of(box, size)), margin, along-margin, pitch)
        bands.append(((lo+hi)/2, lines))
    counts = [len(lines)-1 for _, lines in bands if lines]
    if not counts:
        return None
    ranked = sorted(set(counts), key=counts.count, reverse=True)
    count = ranked[0]
    # Handwriting and illustrations can mislead a band. Trust only a clear majority.
    if count < 2 or counts.count(count) < 3 or len(ranked) > 1 and counts.count(ranked[1]) == counts.count(count):
        return None
    agreeing = [(centre, lines) for centre, lines in bands if lines and len(lines)-1 == count]
    return [_smooth_line([(centre, lines[k][0], lines[k][1]) for centre, lines in agreeing], pitch)
            for k in range(count+1)]


def _curve(knots, at):
    """Piecewise-linear position of a grid line; constant beyond its ends."""
    if at <= knots[0][0]:
        return knots[0][1]
    for (a0, p0), (a1, p1) in zip(knots, knots[1:]):
        if at <= a1:
            return p0 + (p1 - p0) * (at - a0) / (a1 - a0)
    return knots[-1][1]


def _smooth_line(samples, pitch):
    """Follow one grid line across the bands, discarding stray band readings.

    A band that snapped to a neighbouring stroke disagrees with both of its
    neighbours; a page curl moves neighbouring bands together.
    """
    points = [(at, position) for at, position, measured in samples if measured]
    if len(points) < 2:
        points = [(at, position) for at, position, _ in samples]
    if len(points) < 3:
        return points
    knots = []
    for i, (at, position) in enumerate(points):
        if 0 < i < len(points) - 1:
            expected = sorted((points[i-1][1], position, points[i+1][1]))[1]
        else:
            # Extrapolate an end band from its two inward neighbours.
            (a1, p1), (a2, p2) = (points[1], points[2]) if i == 0 else (points[-2], points[-3])
            expected = p1 + (p1 - p2) * (at - a1) / (a1 - a2)
        if abs(position - expected) <= .15 * pitch:
            knots.append((at, position))
    return knots or points


def regularize(image):
    """Remap measured, unevenly spaced grid lines onto an even grid.

    Returns (image, rows, cols, bounds) or None when the lines are ambiguous.
    """
    from PIL import Image
    gray = image.convert('L')
    scale = min(1, 1400 / max(gray.size))
    if scale < 1:
        gray = gray.resize((round(gray.width*scale), round(gray.height*scale)), Image.Resampling.LANCZOS)
    columns, rows = _band_lines(gray, True), _band_lines(gray, False)
    if columns is None or rows is None:
        return None
    cols, row_count = len(columns) - 1, len(rows) - 1

    def column_at(k, y):
        return _curve(columns[k], y*scale) / scale

    def row_at(j, x):
        return _curve(rows[j], x*scale) / scale
    width, height = image.size
    left, top = MARGIN / (1 + 2*MARGIN) * width, MARGIN / (1 + 2*MARGIN) * height
    pitch_x, pitch_y = (width - 2*left) / cols, (height - 2*top) / row_count

    def source(k, j):
        """Where measured column line k meets measured row line j."""
        x, y = column_at(k, height/2), row_at(j, width/2)
        for _ in range(4):
            x, y = column_at(k, y), row_at(j, x)
        return x, y

    targets_x = [0] + [left + k*pitch_x for k in range(cols+1)] + [width]
    targets_y = [0] + [top + j*pitch_y for j in range(row_count+1)] + [height]
    points = {}
    for j in range(row_count+1):
        for k in range(cols+1):
            points[k+1, j+1] = source(k, j)
    # Extend the outermost cells to the image edge, keeping the photo margin.
    for j in range(1, row_count+2):
        x, y = points[1, j]
        points[0, j] = (x - left, y)
        x, y = points[cols+1, j]
        points[cols+2, j] = (x + left, y)
    for k in range(cols+3):
        x, y = points[k, 1]
        points[k, 0] = (x, y - top)
        x, y = points[k, row_count+1]
        points[k, row_count+2] = (x, y + top)
    mesh = []
    for j in range(row_count+2):
        for k in range(cols+2):
            box = tuple(map(round, (targets_x[k], targets_y[j], targets_x[k+1], targets_y[j+1])))
            if box[2] <= box[0] or box[3] <= box[1]:
                continue
            quad = points[k, j] + points[k, j+1] + points[k+1, j+1] + points[k+1, j]
            mesh.append((box, quad))
    even = image.transform(image.size, Image.Transform.MESH, mesh, Image.Resampling.BICUBIC, fillcolor='white')
    bounds = {'x': round(left)/width, 'y': round(top)/height,
              'width': (round(targets_x[-2]) - round(left))/width, 'height': (round(targets_y[-2]) - round(top))/height}
    return even, row_count, cols, bounds


def straighten(payload):
    if not isinstance(payload, dict):
        raise ValueError('Straightening needs an image and handles.')
    image = decode_image(payload.get('image'))
    flat = even_lighting(straighten_image(image, payload.get('handles')))
    result = {'rows': None, 'cols': None, 'bounds': None}
    even = regularize(flat)
    if even is not None:
        flat, result['rows'], result['cols'], result['bounds'] = even
    buffer = io.BytesIO()
    flat.save(buffer, format='JPEG', quality=92)
    result.update(image='data:image/jpeg;base64,' + base64.b64encode(buffer.getvalue()).decode(),
                  width=flat.width, height=flat.height)
    return result
