"""Local image decoding and grid-assisted Tesseract recognition."""
import base64
import binascii
import io
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .number_reader import _binary, _strip_lines, number_glyphs, read_numbers, review_numbers

MAX_PIXELS = 16_000_000
MAX_IMAGE_BYTES = 12_000_000


def available():
    try:
        from PIL import Image  # noqa: F401
        return shutil.which('tesseract') is not None
    except ImportError:
        return False


def decode_image(value):
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:
        raise ValueError('Screenshot recognition needs Pillow: pip install -r requirements.txt') from exc
    if not isinstance(value, str) or not re.match(r'^data:image/(png|jpeg|webp|bmp);base64,', value):
        raise ValueError('Use a PNG, JPEG, WebP or BMP image.')
    try:
        raw = base64.b64decode(value.split(',', 1)[1], validate=True)
        if len(raw) > MAX_IMAGE_BYTES:
            raise ValueError('Image exceeds the 12 MB limit.')
        im = Image.open(io.BytesIO(raw))
        if im.width * im.height > MAX_PIXELS:
            raise ValueError('Image exceeds the 16 megapixel limit. Crop or resize it first.')
        im.load()
        # Phone photos store sideways pixels plus an orientation tag. Browsers
        # display the rotated image, so alignment and handles use that frame.
        from PIL import ImageOps
        im = ImageOps.exif_transpose(im)
        # Flatten transparent screenshots on white, rather than treating transparency as black.
        rgba = im.convert('RGBA')
        bg = Image.new('RGBA', rgba.size, 'white')
        bg.alpha_composite(rgba)
        return bg.convert('RGB')
    except (binascii.Error, UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError('The supplied image could not be decoded.') from exc


def image_bounds(bounds):
    if bounds is None:
        bounds = {'x': 0, 'y': 0, 'width': 1, 'height': 1}
    if not isinstance(bounds, dict):
        raise ValueError('Image bounds must be an object with x, y, width and height.')
    try:
        vals = [float(bounds[k]) for k in ('x', 'y', 'width', 'height')]
    except (KeyError, TypeError, ValueError):
        raise ValueError('Image bounds require x, y, width and height fractions.') from None
    x, y, w, h = vals
    if not all(math.isfinite(v) for v in vals) or min(x, y) < 0 or min(w, h) <= 0 or x+w > 1.000001 or y+h > 1.000001:
        raise ValueError('Grid bounds must fit inside the image.')
    return x, y, w, h


def _recognize_sheet(sheet, whitelist, diagnostics, psm=6):
    with tempfile.TemporaryDirectory(prefix='codeword-ocr-') as temp:
        path = Path(temp) / 'grid.png'
        sheet.save(path)
        try:
            result = subprocess.run(['tesseract', str(path), 'stdout', '--psm', str(psm), '-l', 'eng',
                                     '-c', 'tessedit_char_whitelist=' + whitelist, 'makebox'],
                                    capture_output=True, text=True, errors='replace', timeout=3 if psm == 7 else 35)
        except subprocess.TimeoutExpired:
            diagnostics.append('Text recognition reached its time limit. Review and enter missing text manually.')
            return []
    if result.returncode:
        diagnostics.append('Tesseract could not read the grid. Check its English language data; manual editing remains available.')
        return []
    records = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) == 6:
            char, left, bottom, right, top, _ = parts
            records.append({'text': char, 'left': int(left), 'top': sheet.height-int(top),
                            'width': int(right)-int(left), 'height': int(top)-int(bottom)})
    return records


def _photo_regions(appearances, rows, cols):
    photos = {i for i, (_, clue, _) in enumerate(appearances) if clue}
    pending = set(photos)
    while pending:
        component = {pending.pop()}
        frontier = list(component)
        while frontier:
            i = frontier.pop()
            r, c = divmod(i, cols)
            neighbours = [rr * cols + cc for rr, cc in ((r-1, c), (r+1, c), (r, c-1), (r, c+1))
                          if 0 <= rr < rows and 0 <= cc < cols]
            for j in neighbours:
                if j in pending:
                    pending.remove(j)
                    component.add(j)
                    frontier.append(j)
        r0, r1 = min(i // cols for i in component), max(i // cols for i in component)
        c0, c1 = min(i % cols for i in component), max(i % cols for i in component)
        area = (r1-r0+1) * (c1-c0+1)
        if r1 > r0 and c1 > c0 and len(component) / area >= .45:
            photos.update(r * cols + c for r in range(r0, r1+1) for c in range(c0, c1+1))
    return photos


def _text_region(crop, kind):
    """Separate small corner numbers from complete, larger central letters."""
    from PIL import Image
    gray = crop.convert('L')
    gray.thumbnail((256, 256), Image.Resampling.LANCZOS)
    pixels = gray.load()
    # A crop can include a sliver of grid line; never read it as text.
    mask = _binary(gray)
    if mask is not None:
        _strip_lines(mask)
    pending = {(x, y) for y in range(gray.height) for x in range(gray.width)
               if pixels[x, y] < 150 and (mask is None or mask[y][x])}
    selected = []
    while pending:
        seed = pending.pop()
        component, frontier = [seed], [seed]
        while frontier:
            x, y = frontier.pop()
            for other in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)):
                if other in pending:
                    pending.remove(other)
                    component.append(other)
                    frontier.append(other)
        xs, ys = zip(*component)
        x0, x1, y0, y1 = min(xs), max(xs)+1, min(ys), max(ys)+1
        height = y1-y0
        if kind == 'number':
            keep = y0 < gray.height*.2 and y1 < gray.height*.55 and height >= max(3, gray.height*.10)
        else:
            keep = height > gray.height*.28 and y1 > gray.height*.55 and x1-x0 < gray.width*.85
        if keep:
            selected.extend(component)
    region = Image.new('L', gray.size, 255)
    ink = region.load()
    for x, y in selected:
        ink[x, y] = pixels[x, y]
    return region


def _mapping_key_cells(cells, rows, cols, edges=None):
    """Identify a corner number key only with a blank separator and 1..N rows."""
    if cells[0].get('number') != '1' or cells[0].get('letter'):
        return set()
    width = 0
    while width < cols and cells[width].get('number') == str(width+1) and not cells[width].get('letter'):
        width += 1
    if width < 4 or width == cols:
        return set()
    height = 1
    while height < rows and all(cells[height*cols+c].get('number') == str(height*width+c+1)
                               and not cells[height*cols+c].get('letter') for c in range(width)):
        height += 1
    if height < 2 or height == rows:
        return set()
    separator = [cells[height*cols+c] for c in range(width)]
    if any(cell.get('number') for cell in separator):
        return set()
    if any(cell.get('letter') or cell.get('black') for cell in separator):
        if edges is None or sum(edges[0][height, c] for c in range(1, width)) > (width-1)*.25:
            return set()
    return {r*cols+c for r in range(height) for c in range(width)}


def _mapping_key_panel(cells, rows, cols, keys, edges):
    """Include a borderless attribution row/column adjoining a recognized key."""
    height = max(i//cols for i in keys)+1
    width = max(i%cols for i in keys)+1
    vertical, horizontal = edges
    if height < rows and not any(cells[height*cols+c].get('number') for c in range(width)):
        if sum(vertical[height, c] for c in range(1, width)) <= (width-1)*.25:
            height += 1
    if width < cols and not any(cells[r*cols+width].get('number') for r in range(height)):
        if sum(horizontal[r, width] for r in range(1, height)) <= (height-1)*.5:
            width += 1
    return {r*cols+c for r in range(height) for c in range(width)}


def _exclude_detached_panel(cells, panel, diagnostics):
    # Keep the printed key in the OCR sheet until recognition and repeated-glyph
    # checks finish. Its numbers provide useful evidence but are never playable.
    for index in panel:
        cells[index].update(black=True, clue=True, highlight=False, number='', letter='')
    if panel:
        diagnostics.append('Excluded a detached grid panel and its borderless surround from the playable puzzle.')


def _read_numbers_by_consensus(cells, crops, position, diagnostics):
    """Relabel numbers from glyph clusters shared across the whole puzzle.

    The per-cell readings above become votes. Consensus wins where it found a
    number; cells it cannot segment keep their per-cell reading.
    """
    position = 'bottom' if str(position or '').startswith('bottom') else 'top'
    glyphs, disturbed = {}, set()
    for i, cell in enumerate(cells):
        if not cell['black']:
            report = {}
            glyphs[i] = number_glyphs(crops[i], position, report)
            if report.get('disturbed'):
                disturbed.add(i)
    readings = {i: cells[i]['number'] for i in glyphs}
    numbers, confidence = read_numbers(glyphs, readings, _recognize_sheet, diagnostics)
    for i in disturbed:
        confidence[i] = 0
    changed = 0
    # Three-digit readings are kept for review_numbers to repair or drop.
    for index, number in numbers.items():
        if 0 < int(number) <= 999 and cells[index]['number'] != number:
            cells[index]['number'] = number
            changed += 1
    if changed:
        diagnostics.append(f'Matched repeated digit shapes across the puzzle to refine {changed} numbers; review the transcription.')
    return confidence


def _review_numbers(cells, confidence, diagnostics):
    checked, missing_cells = review_numbers(cells, confidence)
    if checked or missing_cells:
        diagnostics.append(f'Marked {checked} numbers to check (amber) and {missing_cells} cells with no number (red ?).')
    values = {int(cell['number']) for cell in cells if cell['number'] and not cell['black']}
    missing = [n for n in range(1, max(values, default=0)+1) if n not in values]
    if values and missing and len(missing) <= 5:
        diagnostics.append('Numbers not found in the grid: ' + ', '.join(map(str, missing)) + '. A codeword normally uses every number, so check for misread cells.')


def recognize(payload):
    try:
        from PIL import Image
    except ImportError as exc:
        raise ValueError('Screenshot recognition needs Pillow: pip install -r requirements.txt') from exc
    from .grid_detection import detect_grid, cell_appearance, missing_grid_regions, grid_edges, detached_grid_cells
    im = decode_image(payload.get('image'))
    photo = payload.get('photo') is True
    auto = payload.get('autoDetect') is True
    if auto:
        rows, cols, bounds = detect_grid(im)
    else:
        rows, cols = payload.get('rows'), payload.get('cols')
        bounds = payload.get('bounds')
    if type(rows) is not int or type(cols) is not int or not (1 <= rows <= 40 and 1 <= cols <= 40):
        raise ValueError('Grid dimensions must be whole numbers from 1 to 40.')
    x, y, w, h = image_bounds(bounds)
    left, top, width, height = x*im.width, y*im.height, w*im.width, h*im.height
    cw, ch = width/cols, height/rows
    if cw < 8 or ch < 8:
        raise ValueError('Cells are too small to recognize. Use a larger screenshot or adjust the bounds.')
    crops, appearances = [], []
    for i in range(rows * cols):
        r, c = divmod(i, cols)
        crop = im.crop((round(left+(c+.02)*cw), round(top+(r+.02)*ch),
                        round(left+(c+.98)*cw), round(top+(r+.98)*ch)))
        crops.append(crop)
        appearances.append(cell_appearance(crop))
    normalized_bounds = dict(zip(('x', 'y', 'width', 'height'), (x, y, w, h)))
    edges = grid_edges(im, rows, cols, normalized_bounds, .12 if photo else .04)
    from .colored_blocks import colored_blocks, photo_blocks
    colored = photo_blocks(crops) if photo else colored_blocks(crops, rows, cols, edges)
    for i in colored:
        appearances[i] = (True, False, False)
    vertical, horizontal = edges
    if photo:
        # Camera noise and handwriting look textured. In a straightened photo,
        # only missing grid strokes identify a picture area.
        appearances = [(black, False, highlight) for black, _, highlight in appearances]
    for i, (black, textured, highlight) in enumerate(appearances):
        r, c = divmod(i, cols)
        if textured and all((vertical[r, c], vertical[r, c+1], horizontal[r, c], horizontal[r+1, c])):
            # A photographic fill enclosed by four real grid strokes is an
            # individual blocked cell, not evidence of a spanning photograph.
            appearances[i] = (True, False, False)
    photos = _photo_regions(appearances, rows, cols)
    detached = detached_grid_cells(rows, cols, edges) if auto else set()
    # Strokes on a strongly curled part of a photographed page sit further
    # from their expected place; only a wide search avoids inventing pictures.
    region_edges = grid_edges(im, rows, cols, normalized_bounds, .25) if photo else edges
    photos.update(missing_grid_regions(im, rows, cols, normalized_bounds, edges=region_edges))
    detached_panel = (detached | missing_grid_regions(
        im, rows, cols, normalized_bounds, detached, edges)) if detached else set()
    cells = [{'black': black or i in photos, 'clue': i in photos,
              'highlight': highlight and i not in photos, 'number': '', 'letter': '',
              'openBeforeAcross': False, 'openAfterAcross': False,
              'openBeforeDown': False, 'openAfterDown': False}
             for i, (black, _, highlight) in enumerate(appearances)]
    diagnostics = ['Review the detected grid, numbers and letters before solving. Image recognition can make mistakes.']
    if auto:
        diagnostics.append(f'Automatically detected a {cols}-column by {rows}-row grid. Adjust alignment if necessary.')
    if photos:
        diagnostics.append(f'Preserved {len(photos)} image-clue or outside-grid cells. Shaded answer cells are marked; the picture meaning is not interpreted automatically.')
    response = {'rows': rows, 'cols': cols,
                'bounds': dict(zip(('x', 'y', 'width', 'height'), (x, y, w, h))),
                'cells': cells, 'diagnostics': diagnostics}
    if not available():
        _exclude_detached_panel(cells, detached_panel, diagnostics)
        diagnostics.append('Tesseract is unavailable. The grid and blocks were detected; enter numbers and letters manually.')
        return response
    tile_w, tile_h, sheet_cols = 150, 100, 12
    # Pack tightly cropped, enlarged glyphs. Keeping numbers and letters on
    # separate sheets avoids interpreting 1 as I or 5 as S.
    kinds = [('number', '0123456789'), ('letter', 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzÅÄÖåäö')]
    if photo:
        # Letters in a photographed puzzle are usually the solver's handwriting,
        # not printed givens; never lock them in as prefilled letters.
        kinds = kinds[:1]
        diagnostics.append('Photo mode: handwritten letters are not read. Enter known letters yourself.')
    for kind, whitelist in kinds:
        glyphs = []
        for i, crop in enumerate(crops):
            if cells[i]['black']:
                continue
            region = _text_region(crop, kind)
            ink = region.point(lambda value: 255 if value < 125 else 0)
            box = ink.getbbox()
            if not box:
                continue
            # Ignore tiny specks, not individual narrow digits such as 1.
            if box[3]-box[1] < max(3, region.height*.07):
                continue
            glyph = region.crop(box).point(lambda value: 0 if value < 150 else 255)
            scale = min(105/glyph.width, 55/glyph.height)
            glyph = glyph.resize((max(1, round(glyph.width*scale)), max(1, round(glyph.height*scale))), Image.Resampling.LANCZOS)
            glyphs.append((i, glyph))
        if not glyphs:
            continue
        sheet = Image.new('L', (sheet_cols*tile_w, math.ceil(len(glyphs)/sheet_cols)*tile_h), 255)
        for index, (_, glyph) in enumerate(glyphs):
            sx, sy = (index % sheet_cols)*tile_w, (index // sheet_cols)*tile_h
            sheet.paste(glyph, (sx+(tile_w-glyph.width)//2, sy+(tile_h-glyph.height)//2))
        found = {}
        for record in _recognize_sheet(sheet, whitelist, diagnostics):
            token = record.get('text', '').strip().upper()
            if not token:
                continue
            cx = int(record['left']) + int(record['width'])/2
            cy = int(record['top']) + int(record['height'])/2
            tile = int(cy//tile_h)*sheet_cols + int(cx//tile_w)
            if 0 <= tile < len(glyphs):
                idx = glyphs[tile][0]
                found.setdefault(idx, []).append(token)
        for idx, tokens in found.items():
            value = ''.join(tokens)
            if kind == 'number' and value.isdecimal() and 0 < int(value) <= 999:
                cells[idx][kind] = str(int(value))
            elif kind == 'letter' and len(value) == 1 and value in whitelist.upper():
                cells[idx][kind] = value
    confidence = _read_numbers_by_consensus(cells, crops, payload.get('numberPosition'), diagnostics)
    key_cells = _mapping_key_cells(cells, rows, cols, edges) if auto else set()
    if key_cells:
        panel = (missing_grid_regions(im, rows, cols, response['bounds'], key_cells, edges)
                 | _mapping_key_panel(cells, rows, cols, key_cells, edges))
        for index in panel:
            cells[index].update(black=True, clue=True, highlight=False, number='', letter='')
        diagnostics.append(f'Excluded {len(key_cells)} sequential number-key entries and their surrounding panel from the playable grid.')
    _exclude_detached_panel(cells, detached_panel, diagnostics)
    _review_numbers(cells, confidence, diagnostics)
    count = sum(bool(cell['number'] or cell['letter']) for cell in cells)
    diagnostics.append(f'Recognized text in {count} cells. Recognition is a draft, not confirmed puzzle data.')
    return response
