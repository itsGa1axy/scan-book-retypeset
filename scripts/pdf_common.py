"""Shared read-only PDF inspection and output guards; no OCR or network calls."""
import hashlib
import json
import math
import os
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError as exc:
    raise SystemExit("PyMuPDF is required. Use uv run on the CLI script, or install pymupdf==1.26.5 in a task venv.") from exc


def pages_arg(value, total):
    """Return ordered, unique 1-based physical page numbers. Fail closed."""
    if value is None or not value.strip():
        raise ValueError("An explicit physical page range is required, e.g. 1-10 or 2,5,9.")
    result = []
    for part in value.split(','):
        part = part.strip()
        if '-' in part:
            ends = part.split('-')
            if len(ends) != 2 or not all(x.isdecimal() for x in ends):
                raise ValueError(f"Invalid page range: {part!r}")
            first, last = map(int, ends)
            if first > last or first < 1 or last > total:
                raise ValueError(f"Page range {part!r} must be ascending and within 1..{total}.")
            result.extend(range(first, last + 1))
        elif part.isdecimal() and 1 <= int(part) <= total:
            result.append(int(part))
        else:
            raise ValueError(f"Invalid page {part!r}; use physical page numbers within 1..{total}.")
    if len(result) != len(set(result)):
        raise ValueError("Duplicate pages are not accepted; use an explicit one-to-one page mapping.")
    return result


def open_pdf(path, password_env=None):
    path = Path(path).expanduser().resolve(strict=True)
    doc = fitz.open(path)
    if not doc.is_pdf:
        doc.close()
        raise ValueError("Input must be a PDF.")
    if doc.needs_pass:
        password = os.environ.get(password_env, '') if password_env else ''
        if not password or not doc.authenticate(password):
            doc.close()
            raise ValueError("PDF requires a valid password; provide its environment variable using --password-env.")
    return path, doc


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def output_guard(path, inputs):
    path = Path(path).expanduser().resolve()
    for inp in inputs:
        inp = Path(inp).resolve()
        if path == inp or (path.exists() and os.path.samefile(path, inp)):
            raise ValueError("Output aliases an input PDF; input replacement is never allowed.")
    if path.exists():
        raise ValueError(f"Output already exists; use a new path: {path}")
    return path


def write_new(path, data, inputs=()):
    path = output_guard(path, inputs)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(data)


def serial(value):
    if isinstance(value, (fitz.Rect, fitz.Point, fitz.Matrix, fitz.Quad)):
        return [serial(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return {"bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
    if isinstance(value, dict):
        return {str(k): serial(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serial(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def json_bytes(value):
    return (json.dumps(serial(value), ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def structure(doc):
    catalog = doc.pdf_catalog()
    return {
        'outline': doc.get_toc(simple=False),
        'page_labels': doc.get_page_labels(),
        'catalog_entries': {key: doc.xref_get_key(catalog, key)[0] != 'null'
                            for key in ('StructTreeRoot', 'MarkInfo', 'OCProperties')},
        'ocgs': doc.get_ocgs(),
        'named_destinations': doc.resolve_names() if hasattr(doc, 'resolve_names') else None,
        'limitation': 'Presence is not validity. Tag MCID/ParentTree references and OCG membership are not audited here.',
    }


def visible_geometry(page, tolerance=0.5):
    """Conservative font-metric boxes in display coordinates, not pixel ink.

    Inspect texttrace rather than a clipped text extraction, so characters
    extending beyond the page are included. This does not detect occlusion.
    """
    bounds = page.rect + (-tolerance, -tolerance, tolerance, tolerance)
    outside = []
    for trace in page.get_texttrace():
        if trace['type'] not in (0, 1) or trace.get('opacity', 1) <= 0:
            continue
        for code, _, origin, bbox in trace['chars']:
            char = chr(code) if 0 <= code <= 0x10ffff else '\ufffd'
            if char.isspace():
                continue
            rect = fitz.Rect(bbox) * page.rotation_matrix
            if rect not in bounds:
                outside.append({'char': char, 'bbox': list(rect)})
    return outside


def page_info(doc, number, font_cache):
    p = doc[number - 1]
    traces = p.get_texttrace()
    visible = [t for t in traces if t['type'] in (0, 1) and t.get('opacity', 1) > 0]
    hidden = [t for t in traces if t['type'] == 3 or t.get('opacity', 1) == 0]
    codes = [c[0] for t in visible for c in t['chars']]
    images = []
    for im in p.get_image_info(xrefs=True):
        rect = fitz.Rect(im['bbox']) * p.rotation_matrix
        intersection = rect & p.rect
        ratio = max(intersection.width, 0) * max(intersection.height, 0) / max(p.rect.width * p.rect.height, 1)
        images.append({**im, 'display_bbox': list(rect), 'page_area_ratio': ratio})
    fonts = []
    for row in p.get_fonts(full=True):
        xref = row[0]
        if xref not in font_cache:
            try:
                font_cache[xref] = bool(doc.extract_font(xref)[3])
            except (ValueError, RuntimeError):
                font_cache[xref] = False
        fonts.append({'xref': xref, 'type': row[2], 'base_name': row[3],
                      'resource_name': row[4], 'encoding': row[5],
                      'embedded_program': font_cache[xref]})
    return {'page': number, 'label': p.get_label(), 'rect': list(p.rect),
            'mediabox': list(p.mediabox), 'cropbox': list(p.cropbox), 'rotation': p.rotation,
            'visible_candidate_chars': sum(len(t['chars']) for t in visible),
            'hidden_chars': sum(len(t['chars']) for t in hidden),
            'unknown_unicode_chars': sum(c in (0, 0xfffd) for c in codes),
            'image_info': images, 'fonts': fonts, 'links': p.get_links(),
            'annotations': [{'type': a.type, 'rect': list(a.rect)} for a in (p.annots() or [])],
            'limitation': 'Visible candidates may still be clipped or covered. Font presence and image counts do not prove fidelity.'}


def projected_outline(toc, selected):
    """Keep nodes targeting selected pages and all necessary ancestors."""
    page_map = {n: i + 1 for i, n in enumerate(selected)}
    parents, stack, keep = {}, [], set()
    for idx, row in enumerate(toc):
        while stack and toc[stack[-1]][0] >= row[0]:
            stack.pop()
        parents[idx] = stack[-1] if stack else None
        if row[2] in page_map:
            keep.add(idx)
            keep.update(stack)
        stack.append(idx)
    rows = []
    for idx in sorted(keep):
        level, title, target = toc[idx][:3]
        rows.append([level, title, page_map.get(target, -1)])
    return rows


def run(main):
    try:
        return main()
    except (ValueError, OSError, RuntimeError) as exc:
        import sys
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
