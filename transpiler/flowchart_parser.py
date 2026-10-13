import re
import base64
import urllib.parse
import xml.etree.ElementTree as ET
import numpy as np
import cv2

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


def ocr_region(img_bgr, x, y, w, h, pad=8):
    """
    Crop a padded region from img_bgr, preprocess it, and run OCR.
    Tries EasyOCR first (no external binary needed), then pytesseract.
    Returns extracted text string (may be empty).
    """
    ih, iw = img_bgr.shape[:2]
    x1 = max(0, x - pad)
    y1 = max(0, y - pad)
    x2 = min(iw, x + w + pad)
    y2 = min(ih, y + h + pad)
    crop = img_bgr[y1:y2, x1:x2]

    if crop.size == 0:
        return ''

    # Upscale small crops for better OCR
    scale = 1.0
    if crop.shape[1] < 80:
        scale = 3.0
    elif crop.shape[1] < 150:
        scale = 2.0
    if scale > 1.0:
        crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    # --- Try EasyOCR (primary — self contained, no binary) ---
    if _load_easyocr():
        try:
            results = _easyocr_reader.readtext(crop, detail=0, paragraph=True)
            text = ' '.join(results).strip()
            if text:
                return text
        except Exception:
            pass

    # --- Fallback: pytesseract (needs Tesseract binary) ---
    if _load_pytesseract():
        try:
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            mean_val = float(gray.mean())
            if mean_val < 128:
                gray = cv2.bitwise_not(gray)
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
            binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
            from PIL import Image
            pil_img = Image.fromarray(binary)
            config = '--psm 6 --oem 3'
            text = _pytesseract.image_to_string(pil_img, config=config)
            return text.strip()
        except Exception:
            pass

    return ''


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
    try:
        pseudo = drawflow_to_pseudo(drawflow_package)
    except Exception:
        lines = ['START']
        for n in nodes:
            if n['type'] == 'input':
                lines.append(f"READ {n['text'].replace('INPUT', '').strip()}")
            elif n['type'] == 'output':
                lines.append(f"PRINT {n['text'].replace('PRINT', '').strip()}")
            elif n['type'] == 'process':
                lines.append(n['text'])
        lines.append('STOP')
        pseudo = '\n'.join(lines)

    return pseudo, drawflow_package


# ---------------------------------------------------------------------------
# Raster Flowchart Parser  — with REAL OCR
# ---------------------------------------------------------------------------

def _classify_shape(approx, x, y, w, h):
    """
    Classify a contour approximation into a flowchart shape type.
    Returns one of: 'start_or_end', 'input', 'output', 'process', 'decision', 'while'
    """
    vertices = len(approx)
    aspect = float(w) / h if h > 0 else 1.0

    # Ovals / rounded rectangles → start or end
    if vertices > 8:
        return 'start_or_end'

    # Diamond (4 vertices, roughly square aspect)
    if vertices == 4 and 0.6 <= aspect <= 1.6:
        # Check if it's actually a diamond by measuring pointiness
        pts = approx.reshape(-1, 2).astype(float)
        cx_s = pts[:, 0].mean()
        cy_s = pts[:, 1].mean()
        # Diamond: min/max x and y points are close to the center x/y
        x_vals = pts[:, 0]
        y_vals = pts[:, 1]
        if (x_vals.max() - x_vals.min()) > (y_vals.max() - y_vals.min()) * 0.5:
            return 'decision'

    # Parallelogram (4 vertices, wide) → input/output
    if vertices == 4 and (aspect > 1.6 or aspect < 0.6):
        return 'input'  # will be refined by OCR text

    # Rectangle → process
    if 4 <= vertices <= 6:
        return 'process'

    # Everything else → process
    return 'process'


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


def _refine_type_by_text(shape_type, ocr_text):
    """Use OCR'd text to refine / correct the shape classification."""
    upper = ocr_text.upper()
    if any(kw in upper for kw in ('START', 'BEGIN')):
        return 'start_or_end'
    if any(kw in upper for kw in ('END', 'STOP', 'EXIT', 'FINISH')):
        return 'end'
    if any(kw in upper for kw in ('READ', 'INPUT', 'ENTER', 'GET')):
        return 'input'
    if any(kw in upper for kw in ('PRINT', 'OUTPUT', 'DISPLAY', 'WRITE', 'SHOW')):
        return 'output'
    if any(kw in upper for kw in ('WHILE', 'REPEAT', 'LOOP')):
        return 'while'
    if '?' in ocr_text or re.search(r'[<>!=]=?', ocr_text):
        return 'decision'
    return shape_type


def parse_raster_flowchart(image_bytes, engine='shape-ocr'):
    """
    Parses raster flowchart images (PNG, JPG, WEBP) using OpenCV contour analysis
    + pytesseract OCR to read the actual text inside each shape.
    """
    np_arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image bytes")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h_img, w_img = img.shape[:2]

    # --- Preprocessing ---
    # For handwritten: adaptive threshold; for digital: Otsu
    if engine == 'handwritten':
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        thresh = cv2.adaptiveThreshold(
            blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 15, 3
        )
    else:
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Close small gaps
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)

    # Find contours
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    detected_shapes = []
    min_area = (h_img * w_img) * 0.003  # at least 0.3% of diagram area

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue

        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.03 * peri, True)
        x, y, w, h = cv2.boundingRect(approx)

        # Skip full-image border
        if w > w_img * 0.93 and h > h_img * 0.93:
            continue
        # Skip very tall/thin things (arrows)
        aspect = float(w) / h if h > 0 else 1.0
        if aspect > 8 or aspect < 0.12:
            continue

        shape_type = _classify_shape(approx, x, y, w, h)

        # Run OCR on this region
        ocr_text = ocr_region(img, x, y, w, h, pad=6)

        # Refine shape type using OCR text
        shape_type = _refine_type_by_text(shape_type, ocr_text)

        detected_shapes.append({
            'type': shape_type,
            'x': x, 'y': y, 'w': w, 'h': h,
            'cy': y + h / 2,
            'cx': x + w / 2,
            'ocr_text': ocr_text,
            'area': area
        })

    # Remove heavily overlapping shapes
    detected_shapes = _merge_overlapping_shapes(detected_shapes)

    # Sort top-to-bottom
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
            # Take only first word as variable (avoid garbage)
            var = re.split(r'[\s,;]', cleaned)[0] if cleaned else ''
            var = re.sub(r'[^a-zA-Z0-9_]', '', var)
            if not var or len(var) < 1:
                var = f'var{i}'
            lines.append(f'READ {var}')

        elif t == 'output':
            cleaned = re.sub(r'^(PRINT|OUTPUT|DISPLAY|WRITE|SHOW)\s*', '', txt, flags=re.IGNORECASE).strip()
            if not cleaned:
                cleaned = f'result{i}'
            # If multi-word string → quote it; if single identifier → bare
            words = re.split(r'\s+', cleaned)
            if len(words) > 1:
                lines.append(f'PRINT "{cleaned}"')
            else:
                lines.append(f'PRINT {cleaned}')

        elif t == 'process':
            cleaned = re.sub(r'^(SET|LET|COMPUTE)\s*', '', txt, flags=re.IGNORECASE).strip()
            if cleaned and '=' in cleaned:
                lines.append(cleaned)
            elif cleaned:
                lines.append(cleaned)
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
                words1 = re.split(r'\s+', o1_txt)
                if len(words1) > 1:
                    lines.append(f'    PRINT "{o1_txt}"')
                else:
                    lines.append(f'    PRINT {o1_txt}')
                seen_ids.add(id(o1))

                lines.append('ELSE')

                # False branch
                o2 = output_nodes[1]
                o2_txt = re.sub(r'^(PRINT|OUTPUT|DISPLAY|WRITE|SHOW)\s*', '', o2['ocr_text'], flags=re.IGNORECASE).strip()
                if not o2_txt:
                    o2_txt = f'result_false{i}'
                words2 = re.split(r'\s+', o2_txt)
                if len(words2) > 1:
                    lines.append(f'    PRINT "{o2_txt}"')
                else:
                    lines.append(f'    PRINT {o2_txt}')
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
