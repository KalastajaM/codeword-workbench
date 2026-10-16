"""Self-calibrating reader for the small printed numbers in codeword cells.

A puzzle prints every number in one font, so the same digit looks the same in
every cell. Rather than trusting one OCR call per cell, split each number into
digit glyphs, cluster identical glyphs across the whole puzzle and label each
cluster once, by consensus. Labels come from OCR of the cluster's averaged
prototype plus the votes of independent per-cell readings. A codeword uses
every number 1..N, which gives a final consistency check.
"""

GLYPH_W, GLYPH_H = 16, 24


def _binary(gray):
    """Return an ink mask for a cell, adapting to its background and contrast."""
    hist = gray.histogram()
    total = sum(hist)
    # The background is the bright majority; ink is the darkest few percent.
    count, background = 0, 255
    for value in range(255, -1, -1):
        count += hist[value]
        if count >= total*.5:
            background = value
            break
    count, dark = 0, 0
    for value in range(256):
        count += hist[value]
        if count >= max(1, total*.01):
            dark = value
            break
    if background-dark < 60:
        return None
    threshold = dark+(background-dark)*.55
    pixels = gray.load()
    return [[pixels[x, y] < threshold for x in range(gray.width)] for y in range(gray.height)]


def _strip_lines(mask):
    """Clear grid strokes along the cell edges, keeping digits that touch them."""
    height, width = len(mask), len(mask[0])
    limit_y, limit_x = max(1, round(height*.15)), max(1, round(width*.15))
    for rows in (range(limit_y), range(height-1, height-1-limit_y, -1)):
        for y in rows:
            if sum(mask[y]) < width*.6:
                break
            mask[y] = [False]*width
    for cols in (range(limit_x), range(width-1, width-1-limit_x, -1)):
        for x in cols:
            if sum(mask[y][x] for y in range(height)) < height*.6:
                break
            for y in range(height):
                mask[y][x] = False
    return mask


def _components(mask):
    height, width = len(mask), len(mask[0])
    seen = [[False]*width for _ in range(height)]
    found = []
    for y in range(height):
        for x in range(width):
            if not mask[y][x] or seen[y][x]:
                continue
            seen[y][x] = True
            stack, points = [(x, y)], []
            while stack:
                px, py = stack.pop()
                points.append((px, py))
                for nx in (px-1, px, px+1):
                    for ny in (py-1, py, py+1):
                        if 0 <= nx < width and 0 <= ny < height and mask[ny][nx] and not seen[ny][nx]:
                            seen[ny][nx] = True
                            stack.append((nx, ny))
            xs, ys = [p[0] for p in points], [p[1] for p in points]
            found.append({'points': points, 'x0': min(xs), 'x1': max(xs)+1, 'y0': min(ys), 'y1': max(ys)+1})
    return found


def number_glyphs(crop, position='top', report=None):
    """Return the corner number of one cell as left-to-right digit masks.

    Each digit is (width, height, rows-of-bools). Large central letters, lone
    specks and grid strokes are excluded. Returns [] when no number is found.
    With a `report` dict, sets report['disturbed'] when an excluded shape
    touches the number's text line, where it may have hidden a digit.
    """
    gray = crop.convert('L')
    if min(gray.size) < 8:
        return []
    mask = _binary(gray)
    if mask is None:
        return []
    mask = _strip_lines(mask)
    height, width = len(mask), len(mask[0])
    parts, components = [], _components(mask)
    for part in components:
        tall = part['y1']-part['y0']
        if position == 'top':
            corner = part['y0'] < height*.3 and part['y1'] < height*.62
        else:
            corner = part['y1'] > height*.7 and part['y0'] > height*.38
        wide = part['x1']-part['x0']
        # A short piece of a grid stroke left at the side of a slightly
        # misaligned crop is a hair-thin upright; even a narrow 1 is wider.
        sliver = wide <= max(2, tall*.12) and (part['x0'] < width*.15 or part['x1'] > width*.85)
        # A number is small: well under the cell height, but not a speck.
        if corner and not sliver and height*.12 <= tall <= height*.5 and wide < width*.6:
            parts.append(part)
    if not parts:
        return []
    # Keep components on the tallest component's text line.
    anchor = max(parts, key=lambda p: p['y1']-p['y0'])
    line = [p for p in parts if min(p['y1'], anchor['y1'])-max(p['y0'], anchor['y0']) > (anchor['y1']-anchor['y0'])*.4]
    line.sort(key=lambda p: p['x0'])
    if report is not None:
        # Handwriting through a digit merges with it into one large shape that
        # is excluded above; the remaining digits then read confidently wrong.
        line_height = anchor['y1']-anchor['y0']
        reach = max(p['x1'] for p in line)+line_height
        report['disturbed'] = any(
            part not in line and part['x0'] < reach and part['x1'] > line[0]['x0']
            and min(part['y1'], anchor['y1'])-max(part['y0'], anchor['y0']) > line_height*.4
            and len(part['points']) > line_height
            for part in components)
    # Merge pieces of one broken digit that overlap horizontally.
    groups = []
    for part in line:
        if groups:
            last = groups[-1]
            overlap = min(last['x1'], part['x1'])-max(last['x0'], part['x0'])
            if overlap > min(last['x1']-last['x0'], part['x1']-part['x0'])*.5:
                last['points'] += part['points']
                last.update(x0=min(last['x0'], part['x0']), x1=max(last['x1'], part['x1']),
                            y0=min(last['y0'], part['y0']), y1=max(last['y1'], part['y1']))
                continue
        groups.append(dict(part, points=list(part['points'])))
    # A group spanning far more than one line height holds touching digits.
    text_height = max(g['y1'] for g in groups)-min(g['y0'] for g in groups)
    glyphs = []
    for group in groups:
        pieces = _split_touching(group, text_height)
        glyphs.extend(pieces)
    if not 1 <= len(glyphs) <= 3:
        return []
    return glyphs


def _split_touching(group, text_height):
    x0, x1, y0, y1 = group['x0'], group['x1'], group['y0'], group['y1']
    width = x1-x0
    columns = [0]*width
    for x, _ in group['points']:
        columns[x-x0] += 1
    count = 1
    if width > text_height*1.05:
        count = 2
    if width > text_height*1.75:
        count = 3
    cuts = []
    for k in range(1, count):
        centre = round(width*k/count)
        window = range(max(1, centre-max(1, width//(count*4))), min(width-1, centre+max(1, width//(count*4))+1))
        cuts.append(min(window, key=lambda x: (columns[x], abs(x-centre))))
    bounds = [0, *cuts, width]
    pieces = []
    for left, right in zip(bounds, bounds[1:]):
        points = [(x, y) for x, y in group['points'] if left <= x-x0 < right]
        if not points:
            continue
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        gx0, gy0 = min(xs), min(ys)
        w, h = max(xs)-gx0+1, max(ys)-gy0+1
        rows = [[False]*w for _ in range(h)]
        for x, y in points:
            rows[y-gy0][x-gx0] = True
        pieces.append((w, h, rows))
    return pieces


def glyph_feature(glyph):
    """Scale a digit to a fixed height, keeping its width; ink is bright."""
    from PIL import Image
    w, h, rows = glyph
    image = Image.new('L', (w, h), 0)
    image.putdata([255 if value else 0 for row in rows for value in row])
    scaled_w = max(1, min(GLYPH_W, round(w*GLYPH_H/h)))
    image = image.resize((scaled_w, GLYPH_H), Image.Resampling.BOX if w > scaled_w else Image.Resampling.BILINEAR)
    canvas = Image.new('L', (GLYPH_W, GLYPH_H), 0)
    canvas.paste(image, ((GLYPH_W-scaled_w)//2, 0))
    return canvas


def feature_distance(a, b):
    """Mean absolute grey-level difference, from 0 (same) to 1."""
    from PIL import ImageChops, ImageStat
    return ImageStat.Stat(ImageChops.difference(a, b)).sum[0]/(255*GLYPH_W*GLYPH_H)


def _mean(images):
    from PIL import Image
    mean = images[0]
    for count, image in enumerate(images[1:], 2):
        mean = Image.blend(mean, image, 1/count)
    return mean


def cluster_glyphs(features, threshold=.06):
    """Group near-identical glyphs. Returns centroids and per-glyph cluster ids.

    The threshold is tight on purpose: splitting one digit into several
    clusters costs only extra OCR, while merging two digits forces an error.
    """
    from PIL import Image
    centroids, members = [], []
    for index, feature in enumerate(features):
        distances = [feature_distance(feature, centroid) for centroid in centroids]
        best = min(range(len(distances)), key=distances.__getitem__, default=None)
        if best is None or distances[best] >= threshold:
            centroids.append(feature)
            members.append([index])
        else:
            members[best].append(index)
            centroids[best] = Image.blend(centroids[best], feature, 1/len(members[best]))
    assignment = [0]*len(features)
    for _ in range(2):
        for index, feature in enumerate(features):
            distances = [feature_distance(feature, centroid) for centroid in centroids]
            assignment[index] = min(range(len(centroids)), key=distances.__getitem__)
        groups = {}
        for index, c in enumerate(assignment):
            groups.setdefault(c, []).append(index)
        centroids = [_mean([features[i] for i in groups[c]]) if c in groups else centroids[c]
                     for c in range(len(centroids))]
    return centroids, assignment


def _prototype_image(centroid, height=48):
    from PIL import Image, ImageFilter, ImageOps
    image = ImageOps.invert(centroid)
    # Trim empty columns so spacing between repeats looks like printed text.
    box = centroid.point(lambda v: 255 if v > 127 else 0).getbbox()
    if box:
        image = image.crop((box[0], 0, box[2], GLYPH_H))
    width = max(1, round(image.width*height/GLYPH_H))
    return image.resize((width, height), Image.Resampling.BICUBIC).filter(ImageFilter.GaussianBlur(.8))


def prototype_votes(centroids, recognize_sheet, diagnostics):
    """OCR every cluster prototype in context; return per-cluster digit votes.

    Each prototype is printed three times on its own line, at two sizes, so a
    cluster can collect up to six votes.
    """
    from PIL import Image
    votes = {}
    if not centroids:
        return votes
    for height in (48, 30):
        line, repeats, gap = height*2+14, 3, height//2
        images = [_prototype_image(centroid, height) for centroid in centroids]
        width = max(80+repeats*(image.width+gap) for image in images)
        sheet = Image.new('L', (width, line*len(images)+40), 255)
        for row, image in enumerate(images):
            x = 40
            for _ in range(repeats):
                sheet.paste(image, (x, 20+row*line))
                x += image.width+gap
        for record in recognize_sheet(sheet, '0123456789', diagnostics):
            text = record['text']
            if not text.isdecimal():
                continue
            row = int((record['top']+record['height']/2-20+(line-height)/2)//line)
            if 0 <= row < len(images):
                votes.setdefault(row, {}).setdefault(text, 0)
                votes[row][text] += 1
    return votes


def _label_clusters(centroids, sizes, assignment, glyph_cells, cell_readings, proto_votes):
    """Rank digit labels for every cluster.

    A cluster's own evidence is prototype OCR plus independent per-cell
    readings. A weakly read cluster also borrows from nearby clusters whose own
    reading is confident, weighted by size and visual similarity.
    """
    count = len(centroids)
    cell_votes = [dict() for _ in range(count)]
    cursor = 0
    for cell, glyph_count in glyph_cells:
        reading = cell_readings.get(cell, '')
        if len(reading) == glyph_count:
            for offset, digit in enumerate(reading):
                votes = cell_votes[assignment[cursor+offset]]
                votes[digit] = votes.get(digit, 0)+1
        cursor += glyph_count
    own = []
    for c in range(count):
        score = {}
        total = sum(cell_votes[c].values())
        for digit, n in cell_votes[c].items():
            # Agreement among many cells is strong; one cell is a weak vote.
            score[digit] = score.get(digit, 0)+n/total*min(1, total/3)
        for digit, n in proto_votes.get(c, {}).items():
            score[digit] = score.get(digit, 0)+min(n, 6)/6
        own.append(score)
    labels = []
    for c in range(count):
        confidence = min(1, max(own[c].values(), default=0))
        borrowed, weight_total = {}, 0
        for other in range(count):
            if other == c or not own[other]:
                continue
            digit, strength = max(own[other].items(), key=lambda item: item[1])
            if strength < .66:
                continue
            distance = feature_distance(centroids[c], centroids[other])
            if distance >= .15:
                continue
            weight = min(1, sizes[other]/3)*(1-distance/.15)**2
            borrowed[digit] = borrowed.get(digit, 0)+weight
            weight_total += weight
        score = dict(own[c])
        for digit, weight in borrowed.items():
            score[digit] = score.get(digit, 0)+(1-confidence)*weight/weight_total
        labels.append(sorted(score.items(), key=lambda item: -item[1]))
    return labels, [max(score.values(), default=0) for score in own]


def _numbers_for(labels, choice, glyph_cells, assignment):
    numbers, cursor = {}, 0
    for cell, glyph_count in glyph_cells:
        digits = []
        for offset in range(glyph_count):
            c = assignment[cursor+offset]
            digits.append(choice[c] if c in choice else labels[c][0][0] if labels[c] else '')
        cursor += glyph_count
        text = ''.join(digits)
        if len(text) == glyph_count and text[0] != '0':
            numbers[cell] = text
    return numbers


def _coverage(numbers):
    """Score how well numbers form the complete 1..N sequence a codeword uses."""
    values = [int(v) for v in numbers.values()]
    present = set(values)
    run = 0
    while run+1 in present:
        run += 1
    # Prefer a longer unbroken run, then more cells inside it.
    return run*1000+sum(value <= run for value in values)


def read_numbers(cell_glyphs, cell_readings, recognize_sheet, diagnostics):
    """Return ({cell: number}, {cell: confidence}) from per-puzzle glyph consensus.

    cell_glyphs maps cell index to its glyph list; cell_readings maps the same
    indices to independent OCR text, used only as votes.
    """
    glyph_cells, features = [], []
    for cell, glyphs in sorted(cell_glyphs.items()):
        if glyphs:
            glyph_cells.append((cell, len(glyphs)))
            features.extend(glyph_feature(glyph) for glyph in glyphs)
    if not features:
        return {}, {}
    centroids, assignment = cluster_glyphs(features)
    proto = prototype_votes(centroids, recognize_sheet, diagnostics)
    sizes = [assignment.count(c) for c in range(len(centroids))]
    labels, own_strength = _label_clusters(centroids, sizes, assignment, glyph_cells, cell_readings, proto)
    choice = {}
    numbers = _numbers_for(labels, choice, glyph_cells, assignment)
    # Relabel weakly read clusters only when that makes the numbers a more
    # complete 1..N sequence. Strongly read clusters are never changed.
    best = _coverage(numbers)
    weak = [c for c in range(len(labels)) if own_strength[c] < .66]
    for _ in range(3):
        improved = False
        for c in weak:
            current = choice.get(c, labels[c][0][0] if labels[c] else '')
            # Only digits with visual evidence here or in a near-identical
            # cluster; otherwise relabelling invents numbers to fill gaps.
            options = {digit for other in range(len(labels))
                       if other == c or feature_distance(centroids[c], centroids[other]) < .15
                       for digit, _ in labels[other]}
            for digit in sorted(options):
                if digit == current:
                    continue
                trial = {**choice, c: digit}
                candidate = _numbers_for(labels, trial, glyph_cells, assignment)
                score = _coverage(candidate)
                if score > best:
                    best, choice, numbers, improved = score, trial, candidate, True
                    current = digit
        if not improved:
            break
    confidence, cursor = {}, 0
    for cell, glyph_count in glyph_cells:
        strengths = []
        for offset in range(glyph_count):
            c = assignment[cursor+offset]
            ranked = dict(labels[c])
            picked = choice.get(c, labels[c][0][0] if labels[c] else '')
            other = max((v for d, v in ranked.items() if d != picked), default=0)
            strengths.append(ranked.get(picked, 0)-other)
        cursor += glyph_count
        confidence[cell] = min(strengths)
    return numbers, confidence


def number_range(values):
    """Highest number of the puzzle's 1..N sequence, from repeatedly read values.

    A codeword uses every number from 1 upwards. Misreads such as 114 for 14
    occur once and sit far above the run, so they never extend it.
    """
    counts = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    frequent = sorted(value for value, count in counts.items() if count >= 2 and value > 0)
    top = 0
    for value in frequent:
        if value - top > 3:
            break
        top = value
    return top


def review_numbers(cells, confidence, sure=.6):
    """Repair out-of-range numbers and mark cells whose number needs review.

    Sets cell['numberReview'] to 'check' (doubtful reading) or 'missing' (no
    number found in a playable cell). Sure readings carry no mark.
    Returns (checked, missing) counts.
    """
    playable = [i for i, cell in enumerate(cells) if not cell['black']]
    values = [int(cells[i]['number']) for i in playable if cells[i]['number']]
    top = number_range(values)
    counts = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    for i in playable:
        cell = cells[i]
        cell.pop('numberReview', None)
        number = cell['number']
        doubtful = confidence.get(i, 0) < sure
        # A rarely used letter can number just above the repeated run.
        if number and top and int(number) > top + 3:
            # A stray stroke adds a digit at either end; keep the reading only
            # if dropping it gives a number used elsewhere in the puzzle.
            options = [text for text in (number[1:], number[:-1])
                       if text and text[0] != '0' and 1 <= int(text) <= top + 3 and counts.get(int(text))]
            number = max(options, key=lambda text: counts[int(text)]) if options else ''
            cell['number'], doubtful = number, True
        if not number:
            cell['numberReview'] = 'missing'
        elif doubtful or counts.get(int(number), 0) < 2:
            cell['numberReview'] = 'check'
    checked = sum(cells[i].get('numberReview') == 'check' for i in playable)
    missing = sum(cells[i].get('numberReview') == 'missing' for i in playable)
    return checked, missing
