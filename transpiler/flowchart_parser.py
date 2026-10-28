import re
import base64
import urllib.parse
import xml.etree.ElementTree as ET
import numpy as np
import cv2
import difflib

from transpiler.flowchart_compiler import drawflow_to_pseudo
from transpiler import TranspilerPipeline


# ---------------------------------------------------------------------------
# Tesseract OCR helper (tries pytesseract; falls back gracefully)
# ---------------------------------------------------------------------------

_PYTESSERACT_AVAILABLE = False
_pytesseract = None
_EASYOCR_AVAILABLE = False
_easyocr_reader = None

def _load_easyocr():
    """Try to load EasyOCR (self-contained, no external binary needed)."""
    global _EASYOCR_AVAILABLE, _easyocr_reader
    if _easyocr_reader is not None:
        return _EASYOCR_AVAILABLE
    try:
        import easyocr
        # gpu=False so it works without CUDA; verbose=False suppresses model download messages
        _easyocr_reader = easyocr.Reader(['en'], gpu=False, verbose=False)
        _EASYOCR_AVAILABLE = True
    except Exception:
        _EASYOCR_AVAILABLE = False
    return _EASYOCR_AVAILABLE


def _load_pytesseract():
    """Try to load pytesseract + locate the Tesseract binary."""
    global _PYTESSERACT_AVAILABLE, _pytesseract
    if _pytesseract is not None:
        return _PYTESSERACT_AVAILABLE
    try:
        import pytesseract as _pt
        import os, subprocess
        candidate_paths = [
            r'C:\Program Files\Tesseract-OCR\tesseract.exe',
            r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
            r'C:\Users\Public\tesseract\tesseract.exe',
        ]
        binary = None
        for p in candidate_paths:
            if os.path.exists(p):
                binary = p
                break
        try:
            out = subprocess.run(['tesseract', '--version'], capture_output=True, timeout=3)
            if out.returncode == 0:
                binary = 'tesseract'
        except Exception:
            pass
        if binary:
            _pt.pytesseract.tesseract_cmd = binary
            _pytesseract = _pt
            _PYTESSERACT_AVAILABLE = True
        else:
            _PYTESSERACT_AVAILABLE = False
    except ImportError:
        _PYTESSERACT_AVAILABLE = False
    return _PYTESSERACT_AVAILABLE

# ===========================================================================
# 1. SHAPE DETECTION
# ===========================================================================

def _binarize(img, engine='shape-ocr'):
    """Returns (gray, ink) where ink is 255 on dark strokes."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if engine == 'handwritten':
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        ink = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                    cv2.THRESH_BINARY_INV, 15, 3)
    else:
        blur = cv2.GaussianBlur(gray, (3, 3), 0)
        _, ink = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return gray, ink


def _classify_shape(mask):
    """
    mask: uint8 crop (255 inside the shape, 0 outside), tightly bounded.
    Classifies by how the left/right edge moves down the shape (the "edge profile"),
    which is far more stable than counting approxPolyDP vertices.
    Returns: 'decision' | 'hexagon' | 'parallelogram' | 'terminator' | 'process'
    """
    h, w = mask.shape
    if h < 8 or w < 8:
        return 'process'
    area = cv2.countNonZero(mask)
    extent = area / float(w * h)

    def edges(frac):
        r = min(h - 1, max(0, int(round(h * frac))))
        xs = np.flatnonzero(mask[r])
        if len(xs) == 0:
            return 0.0, 1.0
        return xs[0] / float(w), (xs[-1] + 1) / float(w)

    l10, r10 = edges(0.10)
    l25, r25 = edges(0.25)
    l50, r50 = edges(0.50)
    l90, r90 = edges(0.90)

    # How far the edge moves inward at the top/bottom relative to the middle row
    inset_l = max(l10, l90) - l50
    inset_r = r50 - min(r10, r90)

    # Diamond: both sides taper to a point at the middle row, about half the bbox area
    if extent < 0.66 and inset_l > 0.15 and inset_r > 0.15:
        return 'decision'

    # Parallelogram: both edges lean the same way, and the lean is linear
    lean_l = l10 - l90
    lean_r = r10 - r90
    if (abs(lean_l) > 0.07 and abs(lean_r) > 0.07 and lean_l * lean_r > 0
            and abs(l50 - (l10 + l90) / 2) < 0.05):
        return 'parallelogram'

    # Hexagon: tapers like a diamond but straight-line (not curved) and fatter
    if 0.66 <= extent < 0.93 and inset_l > 0.05 and inset_r > 0.05:
        d10 = l10 - l50
        if d10 > 1e-6 and (l25 - l50) / d10 > 0.5:
            return 'hexagon'

    # Terminator (stadium): edge curves in at the ends, rectangle edge does not
    if (inset_l + inset_r) / 2 > 0.03 and extent < 0.97:
        return 'terminator'

    return 'process'

def find_shapes(img, engine='shape-ocr'):
    """
    Finds flowchart shapes as ENCLOSED REGIONS (the inside of each outline) instead of as
    dark contours. Arrows connected to a shape can't merge shapes together this way,
    because arrows are outside the enclosed region.
    """
    H, W = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Outlines are found as strong EDGES, not as "dark pixels": that works for dark text on
    # white, white text on a coloured fill, gradients and drop shadows alike.
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blur, 50, 130)

    # Thicken so 1-2px gaps in an outline don't leak the interior into the background
    k = max(3, int(round(min(H, W) / 250.0)) | 1)
    walls = cv2.dilate(edges, np.ones((k, k), np.uint8))
    free = cv2.bitwise_not(walls)

    n, labels, stats, _ = cv2.connectedComponentsWithStats(free, connectivity=4)
    min_area = H * W * 0.002
    shapes = []

    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if x <= 0 or y <= 0 or x + w >= W or y + h >= H:
            continue                         # touches the image edge => page background
        if area < min_area:
            continue
        aspect = w / float(h)
        if aspect > 10 or aspect < 0.1:
            continue

        comp = (labels[y:y + h, x:x + w] == i).astype(np.uint8) * 255
        cnts, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cnt = max(cnts, key=cv2.contourArea)
        filled = np.zeros_like(comp)
        cv2.drawContours(filled, [cnt], -1, 255, -1)

        farea = float(cv2.countNonZero(filled))
        hull_area = cv2.contourArea(cv2.convexHull(cnt))
        solidity = farea / hull_area if hull_area > 0 else 0
        ink_frac = 1.0 - cv2.countNonZero(comp) / farea   # text + any nested shapes

        # Reject regions that are not a single clean shape interior:
        #  - concave (gap between a loop-back arrow and the main chain)
        #  - mostly "holes" (a region that contains other shapes)
        if solidity < 0.85 or ink_frac > 0.45:
            continue

        # All flowchart shapes are convex: use the hull as the shape mask so notches made by
        # text edges touching the outline don't cut letters out of the OCR crop.
        hull_mask = np.zeros_like(comp)
        cv2.drawContours(hull_mask, [cv2.convexHull(cnt)], -1, 255, -1)
        filled = hull_mask

        shapes.append({
            'type': _classify_shape(filled),
            'x': int(x), 'y': int(y), 'w': int(w), 'h': int(h),
            'cx': x + w / 2.0, 'cy': y + h / 2.0,
            'mask': filled,                  # crop-sized interior mask for OCR
            'area': farea,
        })
    # Drop container regions (page border, swim-lane box): they enclose other shapes
    def contains(a, b):
        return (a is not b and a['x'] <= b['cx'] <= a['x'] + a['w']
                and a['y'] <= b['cy'] <= a['y'] + a['h'] and a['area'] > 2 * b['area'])
    shapes = [a for a in shapes if not any(contains(a, b) for b in shapes)]
    return gray, shapes

# ===========================================================================
# 2. OCR
# ===========================================================================

def _prep_for_ocr(gray, shape):
    """
    Crop the shape INTERIOR only (outline, arrows and Yes/No labels masked out) and return a
    tight DARK-TEXT-ON-WHITE grayscale crop, whatever the original colours were.
    Text is whatever differs from the local fill colour, so white-on-red, black-on-white and
    gradient fills all come out the same way.
    """
    x, y, w, h = shape['x'], shape['y'], shape['w'], shape['h']
    crop = gray[y:y + h, x:x + w].copy()
    m = shape['mask']
    e = max(2, int(0.04 * min(w, h)))
    m = cv2.erode(m, np.ones((2 * e + 1, 2 * e + 1), np.uint8))

    ksz = max(5, (min(h, w) // 2) | 1)                    # bigger than a stroke, odd
    fill = cv2.medianBlur(crop, ksz)                      # local fill colour estimate
    diff = cv2.absdiff(crop, fill)
    diff[m == 0] = 0

    top = float(diff.max())
    if top < 25:                                          # nothing but fill: no text
        return None
    diff = np.clip(diff.astype(np.float32) * (255.0 / top), 0, 255).astype(np.uint8)
    _, txt = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    pts = cv2.findNonZero(txt)
    if pts is None:
        return None
    bx, by, bw, bh = cv2.boundingRect(pts)
    return 255 - diff[by:by + bh, bx:bx + bw]

# Glyphs that are just "a vertical bar" to an OCR engine: I  l  |  !  1  [  ]
_BAR_CHARS = set('lI|!1[]')
_PAD = 24


def _scaled(crop, target_ink_h):
    f = float(np.clip(target_ink_h / float(max(crop.shape[0], 1)), 0.5, 5.0))
    interp = cv2.INTER_CUBIC if f > 1 else cv2.INTER_AREA
    im = cv2.resize(crop, None, fx=f, fy=f, interpolation=interp)
    im = cv2.copyMakeBorder(im, _PAD, _PAD, _PAD, _PAD, cv2.BORDER_CONSTANT, value=255)
    return im, f


def _has_dot(native_inv, x0, x1):
    """True if columns [x0,x1) of the NATIVE-resolution ink image hold a dot above a stem (an 'i')."""
    h, w = native_inv.shape
    x0, x1 = max(0, int(x0) - 1), min(w, int(np.ceil(x1)) + 1)
    if x1 - x0 < 1:
        return False
    k, _, st, _ = cv2.connectedComponentsWithStats(native_inv[:, x0:x1], connectivity=8)
    comps = [tuple(int(v) for v in st[i][:4]) for i in range(1, k)]
    for (ax, ay, aw, ah) in comps:                       # candidate dot
        if ah > 0.35 * h:
            continue
        for (bx, by, bw, bh) in comps:                   # candidate stem below it
            if (bh >= 0.45 * h and ay + ah <= by and
                    min(ax + aw, bx + bw) - max(ax, bx) >= 0.5 * min(aw, bw)):
                return True
    return False


def _tesseract_read(pt, im, psm, native_inv, f):
    """Returns (text, conf). Short bar-like words are re-decided from glyph geometry."""
    from PIL import Image
    try:
        d = pt.image_to_data(Image.fromarray(im), config=f'--oem 3 --psm {psm}',
                             output_type=pt.Output.DICT)
    except Exception:
        return '', 0.0
    words, confs, last = [], [], None
    for i, (t, c) in enumerate(zip(d['text'], d['conf'])):
        if not t.strip() or float(c) < 0:
            continue
        ln = (d['block_num'][i], d['par_num'][i], d['line_num'][i])
        if len(t) <= 3 and set(t) <= (_BAR_CHARS | set('i')):
            x0 = (d['left'][i] - _PAD) / f
            x1 = (d['left'][i] + d['width'][i] - _PAD) / f
            t = 'i' if _has_dot(native_inv, x0, x1) else ('l' if t == 'i' else t)
        if last is not None and ln != last:
            words.append('\n')
        words.append(t)
        confs.append(float(c))
        last = ln
    if not confs:
        return '', 0.0
    return ' '.join(words).replace(' \n ', '\n'), sum(confs) / len(confs)


def ocr_candidates(gray, shape):
    """
    Read the shape at several scales and return [(text, conf), ...].
    A single scale is unreliable for short names; the caller votes across scales.
    """
    crop = _prep_for_ocr(gray, shape)
    if crop is None:
        return []
    _, native_inv = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    ink_h = crop.shape[0]
    single_line = crop.shape[1] / float(max(ink_h, 1)) > 3.0
    psm = 7 if single_line else 6
    scale_targets = (35, 50, 70, 100) if single_line else (60, 100)
    out = []
    if _load_pytesseract():
        for tgt in scale_targets:
            im, f = _scaled(crop, tgt)
            t, c = _tesseract_read(_pytesseract, im, psm, native_inv, f)
            if t.strip():
                out.append((t.strip(), c))
    if (not out or max(c for _, c in out) < 60) and _load_easyocr():
        try:
            im, _ = _scaled(crop, 60)
            res = _easyocr_reader.readtext(cv2.cvtColor(im, cv2.COLOR_GRAY2BGR),
                                           detail=1, paragraph=False)
            res.sort(key=lambda r: (round(r[0][0][1] / 20), r[0][0][0]))
            if res:
                out.append((' '.join(r[1] for r in res),
                            100.0 * sum(r[2] for r in res) / len(res)))
        except Exception:
            pass
    return out


# ===========================================================================
# 3. TEXT CLEAN-UP  (operators, look-alike glyphs, variable-name consensus)
# ===========================================================================

_UNICODE_FIX = {'\u2264': '<=', '\u2265': '>=', '\u2260': '!=', '\u00d7': '*', '\u00f7': '/',
                '\u2212': '-', '\u2013': '-', '\u2014': '-', '\u2190': '=', '\u201c': '"',
                '\u201d': '"', '\u2018': "'", '\u2019': "'", '\u00b7': '*'}

# Look-alikes used only to MATCH names against each other (never to rewrite digits)
_CONFUSABLE = str.maketrans({'0': 'o', '1': 'l', 'i': 'l', 'I': 'l', '|': 'l', '5': 's', '8': 'b', '$': 's'})

_TOKEN_RE = re.compile(r'"[^"]*"|<=|>=|==|!=|(?:[A-Za-z0-9_.|\[\]]|!(?!=))+|\S')

_KEYWORDS = {'READ', 'INPUT', 'ENTER', 'GET', 'PRINT', 'OUTPUT', 'DISPLAY', 'WRITE', 'SHOW',
             'SET', 'LET', 'IF', 'IS', 'WHILE', 'START', 'STOP', 'END', 'BEGIN', 'THEN', 'ELSE',
             'AND', 'OR', 'NOT', 'FOR', 'TO', 'DO', 'ENDIF', 'ENDWHILE'}

BAR = '\x00'


def _clean_operators(t):
    for k, v in _UNICODE_FIX.items():
        t = t.replace(k, v)
    t = t.replace('\n', ' ')
    t = re.sub(r'\s*:\s*=\s*', ' = ', t)
    t = re.sub(r'<\s*=|=\s*<', '<=', t)
    t = re.sub(r'>\s*=|=\s*>', '>=', t)
    t = re.sub(r'!\s*=|<\s*>', '!=', t)
    t = re.sub(r'=\s*=', '==', t)
    return re.sub(r'\s+', ' ', t).strip()


def _is_bar_token(tok, stray_brackets):
    if not (1 <= len(tok) <= 3):
        return False
    allowed = _BAR_CHARS if stray_brackets else (_BAR_CHARS - set('[]'))
    return all(c in allowed for c in tok) and set(tok) != {'1'}   # "1", "11" are numbers


def _tokens(text):
    return _TOKEN_RE.findall(text)


def normalise_text(raw):
    """Operators fixed; look-alike number glyphs fixed; bar-glyph names -> BAR placeholder."""
    t = _clean_operators(raw)
    stray = t.count('[') != t.count(']')
    out = []
    for tok in _tokens(t):
        if _is_bar_token(tok, stray):
            out.append(BAR)                         # placeholder, resolved later
        elif re.search(r'\d', tok) and re.fullmatch(r'[0-9OolI|SsBZ]+', tok):
            out.append(tok.translate(str.maketrans('OolI|SsBZ', '001115582')))
        else:
            out.append(tok)
    return ' '.join(out)


def chart_context(all_norm_texts):
    """Facts about the whole chart that decide what an ambiguous bar glyph means."""
    lower_i = any(tok == 'i' for t in all_norm_texts for tok in t.split(' '))
    has_bar_var = any(re.match(r'^(?:(?:SET|LET)\s+)?\x00 =', t, re.I) or
                      re.match(r'^(?:READ|INPUT|ENTER|GET)\s+\x00', t, re.I)
                      for t in all_norm_texts)
    return {'lower_i': lower_i, 'has_bar_var': has_bar_var}


def resolve_bars(text, ctx):
    """
    A bare vertical bar is either the variable I, the digit 1, or noise.
      * chart already uses a dotted 'i'  -> a bar is the digit 1
      * nothing in the chart defines I   -> a bar is the digit 1
      * otherwise it is I, except in 'I = <bar>' and 'I = I +/- <bar>' where it is 1
    """
    if BAR not in text:
        return text
    if ctx['lower_i'] or not ctx['has_bar_var']:
        return text.replace(BAR, '1')
    toks = text.split(' ')
    eq = toks.index('=') if '=' in toks else -1
    lhs_bar = eq == 1 and toks[0] == BAR
    out = []
    for k, t in enumerate(toks):
        if t != BAR:
            out.append(t)
        elif lhs_bar and k == eq + 1 and len(toks) == eq + 2:
            out.append('1')                               # I = 1
        elif lhs_bar and k > eq + 1 and toks[k - 1] in ('+', '-') and k == len(toks) - 1:
            out.append('1')                               # I = I + 1
        else:
            out.append('I')
    return ' '.join(out)


def pick_best_reading(cands):
    """
    cands: [(resolved_text, conf)] for ONE shape (one per scale).
    Choose the medoid: the reading most similar to all the others. A single bad scale
    (e.g. 'it + 1' for 'i + 1') loses the vote; confidence only breaks ties.
    """
    cands = [(t, c) for t, c in cands if t.strip()]
    if not cands:
        return '', 0.0
    if len(cands) == 1:
        return cands[0]
    keys = [re.sub(r'\s+', '', t).lower() for t, _ in cands]
    def score(i):
        return sum(difflib.SequenceMatcher(None, keys[i], keys[j]).ratio()
                   for j in range(len(cands)) if j != i)
    best = max(range(len(cands)), key=lambda i: (round(score(i), 3), cands[i][1]))
    return cands[best]


def _identifiers(t):
    return re.findall(r'[A-Za-z_][A-Za-z0-9_]*', re.sub(r'"[^"]*"', '', t))


def select_readings(per_shape):
    """
    per_shape: list (one per shape) of [(resolved_text, conf), ...] across scales.
    Pass 1: pick the medoid reading per shape.
    Pass 2: build a vocabulary of variable names from the CONFIDENT shapes and re-pick,
            preferring readings whose identifiers are all known names.  This stops a
            one-off misread like 'it + 1' or 'ij' beating the 'i' the rest of the chart uses.
    Returns [(text, conf), ...].
    """
    first = [pick_best_reading(c) for c in per_shape]
    vocab = set()
    for t, c in first:
        if c >= 80:
            vocab.update(n for n in _identifiers(t) if n.upper() not in _KEYWORDS)

    def quality(t):
        ids = [n for n in _identifiers(t) if n.upper() not in _KEYWORDS]
        return 1.0 if not ids else sum(n in vocab for n in ids) / len(ids)

    out = []
    for cands, (t0, c0) in zip(per_shape, first):
        cands = [(t, c) for t, c in cands if t.strip()]
        if len(cands) < 2:
            out.append((t0, c0))
            continue
        keys = [re.sub(r'\s+', '', t).lower() for t, _ in cands]
        def sim(i):
            return sum(difflib.SequenceMatcher(None, keys[i], keys[j]).ratio()
                       for j in range(len(cands)) if j != i)
        best = max(range(len(cands)), key=lambda i: (round(quality(cands[i][0]), 2),
                                                     round(sim(i), 3), cands[i][1]))
        out.append(cands[best])
    return out


def build_name_map(texts):
    """
    Variable names occur several times in one flowchart (declared, updated, compared,
    printed).  OCR rarely misreads every occurrence the same way, so vote: group names that
    are identical after look-alike folding (or >=85% similar, len>=4) and use the most
    frequent spelling.
    """
    counts = {}
    for t in texts:
        for name in _identifiers(t):
            if name.upper() not in _KEYWORDS:
                counts[name] = counts.get(name, 0) + 1
    groups = []
    for name, c in sorted(counts.items(), key=lambda kv: -kv[1]):
        key = name.translate(_CONFUSABLE).lower()
        for g in groups:
            rkey = g['rep'].translate(_CONFUSABLE).lower()
            sim = difflib.SequenceMatcher(None, key, rkey).ratio()
            if key == rkey or (len(name) >= 4 and sim >= 0.85):
                g['members'][name] = c
                break
        else:
            groups.append({'rep': name, 'members': {name: c}})
    mapping = {}
    for g in groups:
        best = sorted(g['members'].items(),
                      key=lambda kv: (-kv[1], sum(ch.isdigit() for ch in kv[0])))[0][0]
        for n in g['members']:
            mapping[n] = best
    return mapping


def apply_name_map(text, mapping):
    parts = re.split(r'("[^"]*")', text)          # leave quoted strings alone
    for i in range(0, len(parts), 2):
        parts[i] = re.sub(r'[A-Za-z_][A-Za-z0-9_]*',
                          lambda m: mapping.get(m.group(0), m.group(0)), parts[i])
    return ''.join(parts)


# ===========================================================================
# 4. TYPE REFINEMENT
# ===========================================================================

def _first_word(text):
    m = re.match(r'\s*([A-Za-z]+)', text)
    return m.group(1).upper() if m else ''


def refine_type(shape_type, text):
    """
    Shape decides the node type. Text only breaks ties the shape cannot:
      parallelogram -> input vs output,  terminator -> start vs end.
    First-word matching only, so 'Send = 0' can't be mistaken for a keyword.
    """
    fw = _first_word(text)
    if shape_type == 'parallelogram':
        if fw in ('PRINT', 'OUTPUT', 'DISPLAY', 'WRITE', 'SHOW'):
            return 'output'
        return 'input'
    if shape_type == 'terminator':
        if fw in ('END', 'STOP', 'EXIT', 'FINISH'):
            return 'end'
        if fw in ('START', 'BEGIN'):
            return 'start'
        return 'start_or_end'                     # decided by position later
    if shape_type == 'hexagon':
        return 'while'
    if shape_type == 'process':
        # I/O drawn as plain rectangles: trust an explicit keyword not followed by '='
        if fw in ('READ', 'INPUT', 'ENTER', 'GET') and not re.match(r'\s*\w+\s*=', text):
            return 'input'
        if fw in ('PRINT', 'OUTPUT', 'DISPLAY', 'WRITE', 'SHOW') and not re.match(r'\s*\w+\s*=', text):
            return 'output'
    return shape_type

# ---------------------------------------------------------------------------
# Text → Pseudocode interpreters
# ---------------------------------------------------------------------------

def _normalise(text):
    """Lowercase, collapse whitespace, strip punctuation except useful chars."""
    t = re.sub(r'[^\w\s<>=!%/*+\-\."\'?]', ' ', text)
    return re.sub(r'\s+', ' ', t).strip()


def _text_to_pseudocode_line(text, node_type):
    """
    Convert OCR'd raw text + detected shape type into a pseudocode line.
    Returns a string like "READ Temp", "PRINT \"Below Freezing\"", "IF Temp < 32 THEN", etc.
    """
    raw = text.strip()
    n = _normalise(raw)
    upper = n.upper()

    if node_type in ('start', 'start_or_end'):
        if 'END' in upper or 'STOP' in upper:
            return 'STOP'
        return 'START'

    if node_type == 'end':
        return 'STOP'

    if node_type == 'input':
        # "Read Temp" → READ Temp
        # "Input X" → READ X
        cleaned = re.sub(r'^(READ|INPUT|ENTER|GET)\s*', '', n, flags=re.IGNORECASE).strip()
        if not cleaned:
            cleaned = 'value'
        # Make a clean variable name: take first word, capitalised as-is
        var = re.split(r'\s+', cleaned)[0]
        # Remove any trailing punctuation
        var = re.sub(r'[^a-zA-Z0-9_]', '', var)
        if not var:
            var = 'value'
        return f'READ {var}'

    if node_type == 'output':
        # "Print Below Freezing" → PRINT "Below Freezing"
        # "Output Result" → PRINT Result
        cleaned = re.sub(r'^(PRINT|OUTPUT|DISPLAY|WRITE|SHOW)\s*', '', n, flags=re.IGNORECASE).strip()
        if not cleaned:
            cleaned = 'result'
        # If it looks like a quoted string, keep as string
        if cleaned.startswith('"') or cleaned.startswith("'"):
            return f'PRINT {cleaned}'
        # If the text contains words (not just an identifier), wrap in quotes
        words = cleaned.split()
        if len(words) > 1:
            return f'PRINT "{cleaned}"'
        else:
            return f'PRINT {cleaned}'

    if node_type == 'process':
        # "Fact = Fact * I" → as-is assignment
        # "Set result = A + B" → result = A + B
        cleaned = re.sub(r'^(SET|LET|COMPUTE|CALC|CALCULATE)\s*', '', n, flags=re.IGNORECASE).strip()
        if not cleaned:
            cleaned = 'result = 0'
        return cleaned

    if node_type == 'decision':
        # "Temp < 32?" → IF Temp < 32 THEN
        # "A > B" → IF A > B THEN
        cond = n.replace('?', '').replace('Is ', '').strip()
        cond = re.sub(r'^(IF|CHECK|IS|WHEN)\s*', '', cond, flags=re.IGNORECASE).strip()
        if not cond:
            cond = 'condition'
        return f'IF {cond} THEN'

    if node_type == 'while':
        cond = n.replace('?', '').strip()
        cond = re.sub(r'^(WHILE|LOOP|REPEAT|UNTIL)\s*', '', cond, flags=re.IGNORECASE).strip()
        if not cond:
            cond = 'condition'
        return f'WHILE {cond}'

    return n  # fallback: return raw text


# ---------------------------------------------------------------------------
# SVG Flowchart parser (unchanged core, kept from before)
# ---------------------------------------------------------------------------

def pseudo_to_tamil(pseudo_text):
    """Converts standard pseudocode keywords into Tamil / Tanglish syntax."""
    translations = [
        (r'\bSTART\b', 'THODANGU'),
        (r'\bSTOP\b', 'MUDI'),
        (r'\bEND\b', 'MUDI'),
        (r'\bREAD\b', 'PADI'),
        (r'\bPRINT\b', 'KANBI'),
        (r'\bOUTPUT\b', 'KANBI'),
        (r'\bDECLARE\b', 'ARIVI'),
        (r'\bSET\b', 'AMAI'),
        (r'\bIF\b', 'IRUNDHAL'),
        (r'\bTHEN\b', ''),
        (r'\bELSE\b', 'ILLAIYEL'),
        (r'\bENDIF\b', 'IF_MUDI'),
        (r'\bWHILE\b', 'VARAI'),
        (r'\bDO\b', ''),
        (r'\bENDWHILE\b', 'VARAI_MUDI'),
    ]
    lines = []
    for line in pseudo_text.splitlines():
        trimmed = line.strip()
        for pattern, repl in translations:
            trimmed = re.sub(pattern, repl, trimmed)
        trimmed = re.sub(r'\s+', ' ', trimmed).strip()
        if trimmed:
            lines.append(trimmed)
    return '\n'.join(lines)


def parse_svg_flowchart(svg_text):
    """
    Parses an SVG flowchart diagram into a Drawflow node graph and pseudocode.
    """
    svg_clean = re.sub(r'\sxmlns(:\w+)?="[^"]+"', '', svg_text)
    root = ET.fromstring(svg_clean)

    texts = []
    for t in root.iter('text'):
        try:
            x = float(t.attrib.get('x', 0))
            y = float(t.attrib.get('y', 0))
            val = "".join(t.itertext()).strip()
            if val:
                texts.append({'x': x, 'y': y, 'text': val})
        except (ValueError, TypeError):
            continue

    nodes = []

    for r in root.iter('rect'):
        try:
            w = float(r.attrib.get('width', 0))
            h = float(r.attrib.get('height', 0))
            if w > 300 and h > 350:
                continue
            x = float(r.attrib.get('x', 0))
            y = float(r.attrib.get('y', 0))
            rx = float(r.attrib.get('rx', 0))
            cx = x + w / 2
            cy = y + h / 2
            closest_text = ""
            min_dist = float('inf')
            for t in texts:
                dist = ((t['x'] - cx)**2 + (t['y'] - cy)**2)**0.5
                if dist < min_dist and dist < max(w, h):
                    min_dist = dist
                    closest_text = t['text']
            node_type = 'process'
            upper_text = closest_text.upper()
            if 'START' in upper_text or (rx >= 15 and cy < 100):
                node_type = 'start'
                closest_text = 'START'
            elif 'END' in upper_text or 'STOP' in upper_text or (rx >= 15 and cy > 350):
                node_type = 'end'
                closest_text = 'STOP'
            nodes.append({'type': node_type, 'cx': cx, 'cy': cy, 'w': w, 'h': h, 'text': closest_text})
        except (ValueError, TypeError):
            continue

    for p in root.iter('polygon'):
        points_str = p.attrib.get('points', '').strip()
        if not points_str:
            continue
        try:
            pts = []
            for pair in points_str.replace(',', ' ').split():
                pts.append(float(pair))
            if len(pts) >= 8:
                xs = pts[0::2]
                ys = pts[1::2]
                cx = sum(xs) / len(xs)
                cy = sum(ys) / len(ys)
                w = max(xs) - min(xs)
                h = max(ys) - min(ys)
                closest_text = ""
                min_dist = float('inf')
                for t in texts:
                    dist = ((t['x'] - cx)**2 + (t['y'] - cy)**2)**0.5
                    if dist < min_dist and dist < max(w, h):
                        min_dist = dist
                        closest_text = t['text']
                node_type = 'decision' if ('?' in closest_text or '>' in closest_text or '<' in closest_text or '==' in closest_text) else 'input'
                if 'PRINT' in closest_text.upper() or 'OUTPUT' in closest_text.upper():
                    node_type = 'output'
                elif 'INPUT' in closest_text.upper() or 'READ' in closest_text.upper():
                    node_type = 'input'
                nodes.append({'type': node_type, 'cx': cx, 'cy': cy, 'w': w, 'h': h, 'text': closest_text})
        except (ValueError, TypeError):
            continue

    nodes.sort(key=lambda n: n['cy'])

    if not nodes:
        lines = [t['text'] for t in sorted(texts, key=lambda t: t['y'])]
        pseudo_text = '\n'.join(lines)
        if 'START' not in pseudo_text:
            pseudo_text = f"START\n{pseudo_text}\nSTOP"
        return pseudo_text, {}

    drawflow_data = {}
    node_id_map = {}

    for idx, n in enumerate(nodes, 1):
        node_id_map[idx] = n
        name = n['type']
        text = n['text']
        node_data = {}
        if name == 'input':
            clean_input = re.sub(r'^(INPUT|READ)\s*', '', text, flags=re.IGNORECASE).strip()
            node_data = {'input': clean_input or 'X'}
        elif name == 'output':
            clean_output = re.sub(r'^(OUTPUT|PRINT)\s*', '', text, flags=re.IGNORECASE).strip()
            node_data = {'output': clean_output or 'X'}
        elif name == 'decision':
            clean_cond = text.replace('?', '').strip()
            node_data = {'condition': clean_cond or 'A > B'}
        elif name == 'process':
            node_data = {'process': text or 'X = 0'}
        elif name == 'while':
            clean_cond = re.sub(r'^WHILE\s*', '', text, flags=re.IGNORECASE).strip()
            node_data = {'condition': clean_cond or 'I <= N'}
        drawflow_data[str(idx)] = {
            'id': idx, 'name': name, 'data': node_data, 'class': name,
            'html': name, 'typenode': False,
            'inputs': {'input_1': {'connections': []}} if name != 'start' else {},
            'outputs': {'output_1': {'connections': []}} if name != 'end' else {},
            'pos_x': int(n['cx']), 'pos_y': int(n['cy'])
        }
        if name in ('decision', 'while'):
            drawflow_data[str(idx)]['outputs']['output_2'] = {'connections': []}

    total = len(nodes)
    for idx in range(1, total):
        curr_node = drawflow_data[str(idx)]
        curr_type = curr_node['name']
        next_id = str(idx + 1)
        if curr_type == 'decision':
            curr_node['outputs']['output_1']['connections'].append({'node': next_id, 'output': 'input_1'})
            alt_id = str(idx + 2) if (idx + 2) <= total else next_id
            curr_node['outputs']['output_2']['connections'].append({'node': alt_id, 'output': 'input_1'})
        elif curr_type != 'end':
            curr_node['outputs']['output_1']['connections'].append({'node': next_id, 'output': 'input_1'})

    drawflow_package = {'drawflow': {'Home': {'data': drawflow_data}}}

    # --------------------------------------------------------------------------
    # Smart pseudocode builder — detects WHILE loops vs IF/ELSE
    # Heuristic: decision followed by process node(s) then an output/end node
    # means it is a WHILE loop (the process nodes are the loop body).
    # --------------------------------------------------------------------------
    def _smart_pseudo(node_list):
        lines_out = []
        consumed = set()
        total_n = len(node_list)
        i = 0
        while i < total_n:
            if i in consumed:
                i += 1
                continue
            nd = node_list[i]
            t, txt = nd['type'], nd['text']

            if t == 'start':
                lines_out.append('START')

            elif t == 'end':
                lines_out.append('STOP')

            elif t == 'input':
                var = re.sub(r'^(INPUT|READ)\s*', '', txt, flags=re.IGNORECASE).strip()
                vars_list = [re.sub(r'[^a-zA-Z0-9_]', '', v.strip()) for v in re.split(r'[,;\s]+', var) if v.strip()]
                vars_list = [v for v in vars_list if v]
                if not vars_list:
                    vars_list = ['X']
                for v in vars_list:
                    lines_out.append(f'READ {v}')

            elif t == 'output':
                val = re.sub(r'^(PRINT|OUTPUT|DISPLAY|WRITE|SHOW)\s*', '', txt, flags=re.IGNORECASE).strip()
                val = val or 'result'
                if len(val.split()) > 1:
                    lines_out.append(f'PRINT "{val}"')
                else:
                    lines_out.append(f'PRINT {val}')

            elif t == 'process':
                cleaned = re.sub(r'^(SET|LET|COMPUTE)\s*', '', txt, flags=re.IGNORECASE).strip()
                if cleaned:
                    for sub in re.split(r'[,;\n]+', cleaned):
                        sub = sub.strip()
                        if sub:
                            lines_out.append(sub)

            elif t in ('decision', 'while'):
                cond = txt.replace('?', '').strip()
                cond = re.sub(r'^(IF|IS|CHECK|WHEN|WHILE|LOOP|REPEAT)\s*', '', cond, flags=re.IGNORECASE).strip()
                cond = cond or 'condition'

                # Scan ahead for consecutive process nodes (potential loop body)
                body = []
                j = i + 1
                while j < total_n and j not in consumed and node_list[j]['type'] == 'process':
                    body.append(j)
                    j += 1

                # After body nodes, check if next is output or end (loop-exit path)
                after_body_type = node_list[j]['type'] if j < total_n else 'end'
                is_loop = len(body) >= 1 and after_body_type in ('output', 'end', 'start_or_end')

                if is_loop:
                    lines_out.append(f'WHILE {cond}')
                    for bi in body:
                        bt = re.sub(r'^(SET|LET|COMPUTE)\s*', '', node_list[bi]['text'], flags=re.IGNORECASE).strip()
                        if bt:
                            for sub in re.split(r'[,;\n]+', bt):
                                sub = sub.strip()
                                if sub:
                                    lines_out.append(f'    {sub}')
                        consumed.add(bi)
                    lines_out.append('ENDWHILE')
                else:
                    # IF/ELSE: find next two output nodes
                    out_nodes = [(k, node_list[k]) for k in range(i+1, total_n)
                                 if node_list[k]['type'] == 'output']
                    lines_out.append(f'IF {cond} THEN')
                    if len(out_nodes) >= 2:
                        o1_i, o1 = out_nodes[0]
                        o1_txt = re.sub(r'^(PRINT|OUTPUT|DISPLAY|WRITE|SHOW)\s*', '', o1['text'], flags=re.IGNORECASE).strip() or 'result'
                        lines_out.append(f'    PRINT "{o1_txt}"' if len(o1_txt.split()) > 1 else f'    PRINT {o1_txt}')
                        consumed.add(o1_i)
                        lines_out.append('ELSE')
                        o2_i, o2 = out_nodes[1]
                        o2_txt = re.sub(r'^(PRINT|OUTPUT|DISPLAY|WRITE|SHOW)\s*', '', o2['text'], flags=re.IGNORECASE).strip() or 'result'
                        lines_out.append(f'    PRINT "{o2_txt}"' if len(o2_txt.split()) > 1 else f'    PRINT {o2_txt}')
                        consumed.add(o2_i)
                    lines_out.append('ENDIF')

            i += 1
        return lines_out

    smart = _smart_pseudo(nodes)
    if smart:
        if smart[0] != 'START':
            smart.insert(0, 'START')
        if smart[-1] != 'STOP':
            smart.append('STOP')
        pseudo = '\n'.join(ln for ln in smart if ln.strip())
    else:
        try:
            pseudo = drawflow_to_pseudo(drawflow_package)
        except Exception:
            fallback = ['START']
            for nd in nodes:
                if nd['type'] == 'input':
                    fallback.append(f"READ {re.sub(r'^(INPUT|READ)\\s*', '', nd['text'], flags=re.IGNORECASE).strip() or 'X'}")
                elif nd['type'] == 'output':
                    fallback.append(f"PRINT {re.sub(r'^(PRINT|OUTPUT)\\s*', '', nd['text'], flags=re.IGNORECASE).strip() or 'result'}")
                elif nd['type'] == 'process':
                    fallback.append(nd['text'])
            fallback.append('STOP')
            pseudo = '\n'.join(fallback)

    return pseudo, drawflow_package


# ---------------------------------------------------------------------------
# Raster Flowchart Parser  — with REAL OCR
# ---------------------------------------------------------------------------

def _print_arg(text):
    """
    Turn OCR text into the argument of PRINT.
      '"Below Freezing"'  -> '"Below Freezing"'   (already quoted: keep, fix stray/missing quote)
      'Below Freezing'    -> '"Below Freezing"'   (several words, no quotes: it's a message)
      'Fact'              -> 'Fact'               (single identifier: print the variable)
    """
    t = text.strip()
    if not t:
        return t
    if re.fullmatch(r"""["'“”‘’]?[^"'“”‘’]*["'“”‘’]?""", t) and re.search(r"""["'“”‘’]""", t):
        inner = t.strip("\"'“”‘’").strip()          # quoted string, maybe one quote lost by OCR
        return '"' + inner + '"'
    if '"' in t:
        return t                                      # a real expression, e.g. "Sum:" , S
    if len(t.split()) > 1:
        return '"' + t + '"'
    return t

def _merge_overlapping_shapes(shapes, overlap_thresh=0.4):
    """Remove shapes that significantly overlap (keep larger one)."""
    if not shapes:
        return shapes
    shapes = sorted(shapes, key=lambda s: s['w'] * s['h'], reverse=True)
    kept = []
    for s in shapes:
        x1, y1, w1, h1 = s['x'], s['y'], s['w'], s['h']
        dominated = False
        for k in kept:
            x2, y2, w2, h2 = k['x'], k['y'], k['w'], k['h']
            ix = max(0, min(x1 + w1, x2 + w2) - max(x1, x2))
            iy = max(0, min(y1 + h1, y2 + h2) - max(y1, y2))
            inter = ix * iy
            area_s = w1 * h1
            if area_s > 0 and inter / area_s > overlap_thresh:
                dominated = True
                break
        if not dominated:
            kept.append(s)
    return kept

def parse_raster_flowchart(image_bytes, engine='shape-ocr'):
    """
    Parses raster flowchart images (PNG, JPG, WEBP) using OpenCV contour analysis
    + pytesseract OCR to read the actual text inside each shape.
    """
    np_arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image bytes")

    # --- Shape detection (enclosed-region based) + OCR ---
    gray, shapes = find_shapes(img, engine)
    shapes.sort(key=lambda s: s['cy'])
    for s in shapes:
        s['cands'] = [(normalise_text(t), c) for t, c in ocr_candidates(gray, s)]
    ctx = chart_context([t for s in shapes for t, _ in s['cands']])
    per_shape = [[(resolve_bars(t, ctx), c) for t, c in s['cands']] for s in shapes]
    picked = select_readings(per_shape)
    name_map = build_name_map([t for t, _ in picked])
    detected_shapes = []
    for s, (txt, conf) in zip(shapes, picked):
        txt = apply_name_map(txt, name_map)
        s['ocr_text'] = txt
        s['ocr_conf'] = conf
        s['type'] = refine_type(s['type'], txt)
        detected_shapes.append(s)

    # Remove heavily overlapping shapes, then sort top-to-bottom
    detected_shapes = _merge_overlapping_shapes(detected_shapes)
    detected_shapes.sort(key=lambda s: s['cy'])

    # --- Build pseudocode from shapes ---
    # Identify start/end nodes
    starts = [s for s in detected_shapes if s['type'] in ('start_or_end', 'start')]
    ends = [s for s in detected_shapes if s['type'] == 'end']

    # If no explicit start/end detected, treat first & last oval/round as start/end
    if not starts and detected_shapes:
        detected_shapes[0]['type'] = 'start_or_end'
    if not ends and detected_shapes:
        detected_shapes[-1]['type'] = 'end'

    # Assign proper start / end labels to start_or_end nodes
    for i, s in enumerate(detected_shapes):
        if s['type'] == 'start_or_end':
            if i == 0:
                s['type'] = 'start'
            else:
                s['type'] = 'end'

    # Build pseudocode lines using OCR text
    lines = []
    decision_stack = []  # track open IF blocks
    seen_ids = set()

    for i, s in enumerate(detected_shapes):
        sid = id(s)
        if sid in seen_ids:
            continue
        seen_ids.add(sid)

        t = s['type']
        txt = s['ocr_text']

        if t == 'start':
            lines.append('START')

        elif t == 'end':
            # Close any open decision blocks
            while decision_stack:
                lines.append('ENDIF')
                decision_stack.pop()
            lines.append('STOP')

        elif t == 'input':
            # Extract variable name from OCR text
            cleaned = re.sub(r'^(READ|INPUT|ENTER|GET)\s*', '', txt, flags=re.IGNORECASE).strip()
            vars_list = [re.sub(r'[^a-zA-Z0-9_]', '', v.strip()) for v in re.split(r'[,;\s]+', cleaned) if v.strip()]
            vars_list = [v for v in vars_list if v]
            if not vars_list:
                vars_list = [f'var{i}']
            for v in vars_list:
                lines.append(f'READ {v}')

        elif t == 'output':
            cleaned = re.sub(r'^(PRINT|OUTPUT|DISPLAY|WRITE|SHOW)\s*', '', txt, flags=re.IGNORECASE).strip()
            if not cleaned:
                cleaned = f'result{i}'
            # If multi-word string → quote it; if single identifier → bare
            lines.append(f'PRINT {_print_arg(cleaned)}')

        elif t == 'process':
            cleaned = re.sub(r'^(SET|LET|COMPUTE)\s*', '', txt, flags=re.IGNORECASE).strip()
            if cleaned:
                for sub in re.split(r'[,;\n]+', cleaned):
                    sub = sub.strip()
                    if sub:
                        lines.append(sub)
            # else skip empty

        elif t == 'decision':
            cond = txt.replace('?', '').strip()
            cond = re.sub(r'^(IF|IS|CHECK|WHEN)\s*', '', cond, flags=re.IGNORECASE).strip()
            if not cond:
                cond = f'condition{i}'
            lines.append(f'IF {cond} THEN')
            decision_stack.append(i)

            # Look ahead: find the ELSE branch output if visible
            # Peek at next two shapes for output nodes branching from decision
            next_shapes = detected_shapes[i+1:]
            output_nodes = [s2 for s2 in next_shapes if s2['type'] == 'output']
            if len(output_nodes) >= 2:
                # True branch
                o1 = output_nodes[0]
                o1_txt = re.sub(r'^(PRINT|OUTPUT|DISPLAY|WRITE|SHOW)\s*', '', o1['ocr_text'], flags=re.IGNORECASE).strip()
                if not o1_txt:
                    o1_txt = f'result_true{i}'
                lines.append(f'    PRINT {_print_arg(o1_txt)}')
                seen_ids.add(id(o1))

                lines.append('ELSE')

                # False branch
                o2 = output_nodes[1]
                o2_txt = re.sub(r'^(PRINT|OUTPUT|DISPLAY|WRITE|SHOW)\s*', '', o2['ocr_text'], flags=re.IGNORECASE).strip()
                if not o2_txt:
                    o2_txt = f'result_false{i}'
                lines.append(f'    PRINT {_print_arg(o2_txt)}')
                seen_ids.add(id(o2))

                lines.append('ENDIF')
                decision_stack.pop()

        elif t == 'while':
            cond = txt.replace('?', '').strip()
            cond = re.sub(r'^(WHILE|LOOP|REPEAT)\s*', '', cond, flags=re.IGNORECASE).strip()
            if not cond:
                cond = f'condition{i}'
            lines.append(f'WHILE {cond}')
            # Body will be added by following process/output nodes
            # ENDWHILE will be added when we detect no more body nodes

    # Ensure START and STOP exist
    if not lines or lines[0] != 'START':
        lines.insert(0, 'START')
    if not lines or lines[-1] != 'STOP':
        # Close any remaining open blocks
        while decision_stack:
            lines.append('ENDIF')
            decision_stack.pop()
        lines.append('STOP')

    pseudo = '\n'.join(ln for ln in lines if ln.strip())
    return pseudo, {}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def parse_flowchart_payload(image_payload, filename='', engine='shape-ocr', target='pseudocode'):
    """
    Main entry point for Flowchart Upload recognition.
    Accepts data URLs, raw SVG strings, or image bytes.
    """
    pseudo_code = ""
    drawflow_data = {}

    if not image_payload:
        raise ValueError("No image data provided")

    # SVG path
    if image_payload.startswith('data:image/svg+xml') or '<svg' in image_payload:
        if image_payload.startswith('data:'):
            header, encoded = image_payload.split(',', 1)
            if ';base64' in header:
                svg_text = base64.b64decode(encoded).decode('utf-8')
            else:
                svg_text = urllib.parse.unquote(encoded)
        else:
            svg_text = image_payload
        pseudo_code, drawflow_data = parse_svg_flowchart(svg_text)

    else:
        # Raster image (PNG, JPG, etc.)
        if image_payload.startswith('data:'):
            header, encoded = image_payload.split(',', 1)
            image_bytes = base64.b64decode(encoded)
        else:
            image_bytes = image_payload.encode('latin-1')

        pseudo_code, drawflow_data = parse_raster_flowchart(image_bytes, engine=engine)

    # Convert to Tamil syntax if requested
    if target == 'tamil':
        pseudo_code = pseudo_to_tamil(pseudo_code)

    # Run through the compiler pipeline
    pipeline = TranspilerPipeline()
    compilation_result = pipeline.compile(pseudo_code)

    compilation_result['generated_pseudo'] = pseudo_code
    compilation_result['drawflow_data'] = drawflow_data
    compilation_result['engine_used'] = engine
    compilation_result['target'] = target

    return compilation_result
