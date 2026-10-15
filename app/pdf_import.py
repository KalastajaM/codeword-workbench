"""Render a single PDF page locally with bounded Poppler subprocesses."""
import base64
import binascii
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

MAX_BYTES = 8 * 1024 * 1024


def available():
    return bool(shutil.which('pdfinfo') and shutil.which('pdftoppm'))


def convert(payload):
    if not isinstance(payload, dict):
        raise ValueError('PDF request must be an object.')
    value = payload.get('pdf')
    if not isinstance(value, str) or not value.startswith('data:application/pdf;base64,'):
        raise ValueError('Choose a PDF document.')
    try:
        raw = base64.b64decode(value.split(',', 1)[1], validate=True)
    except binascii.Error as exc:
        raise ValueError('The PDF could not be decoded.') from exc
    if len(raw) > MAX_BYTES or not raw.startswith(b'%PDF-'):
        raise ValueError('Use a valid PDF of at most 8 MB.')
    page = payload.get('page')
    if page is not None and (type(page) is not int or page < 1):
        raise ValueError('Choose a valid page number.')
    if not available():
        raise ValueError('PDF import needs local Poppler tools (pdfinfo and pdftoppm). Install Poppler and restart the app.')
    env = {**os.environ, 'LC_ALL': 'C'}
    try:
        with tempfile.TemporaryDirectory(prefix='codeword-pdf-') as folder:
            source = Path(folder) / 'input.pdf'
            source.write_bytes(raw)
            info = subprocess.run([shutil.which('pdfinfo'), str(source)], capture_output=True,
                                  timeout=15, env=env)
            if info.returncode:
                raise ValueError('Cannot open this PDF. It may be damaged or password-protected.')
            match = re.search(rb'^Pages:\s+(\d+)', info.stdout, re.M)
            if not match:
                raise ValueError('Could not determine the PDF page count.')
            pages = int(match[1])
            if not 1 <= pages <= 1000:
                raise ValueError('Use a PDF containing 1 to 1000 pages.')
            if page is None:
                return {'pages': pages}
            if page > pages:
                raise ValueError('Page number exceeds the PDF page count.')
            prefix = str(Path(folder) / 'page')
            render = subprocess.run([shutil.which('pdftoppm'), '-f', str(page), '-l', str(page),
                                     '-singlefile', '-scale-to', '3000', '-png', str(source), prefix],
                                    capture_output=True, timeout=30, env=env)
            output = Path(prefix + '.png')
            if render.returncode or not output.is_file():
                raise ValueError('This PDF page could not be rendered.')
            if output.stat().st_size > 12_000_000:
                raise ValueError('Rendered page is too large. Export a smaller image and upload it.')
            return {'pages': pages, 'page': page,
                    'image': 'data:image/png;base64,' + base64.b64encode(output.read_bytes()).decode('ascii')}
    except subprocess.TimeoutExpired as exc:
        raise ValueError('PDF processing timed out. Try a smaller document or export the page as an image.') from exc
