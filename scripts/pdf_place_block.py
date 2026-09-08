#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["pymupdf==1.26.5"]
# ///
"""Place one precompiled text/math PDF block at natural size on a blank overlay.

No OCR, scan erasure, implicit shrinking, rasterization or hierarchy migration.
Use a task-authored TeX block with calibrated size and reviewed content.
"""
import argparse
import math
from pdf_common import fitz, open_pdf, output_guard, page_info, run, sha256, visible_geometry, write_new


def checked_rect(values, label):
    if len(values) != 4 or any(not math.isfinite(x) for x in values):
        raise ValueError(label + ' requires four finite coordinates')
    rect = fitz.Rect(values)
    if rect.is_empty or rect.is_infinite:
        raise ValueError(label + ' must be a nonempty ascending rectangle')
    return rect


def place_block(page, block, box, align='left', protected=()):
    """Validate before modifying page. Caller owns background and document structure."""
    if len(block) != 1 or block[0].rotation or page.rotation:
        raise ValueError('Use single-page, unrotated blocks and an unrotated working canvas')
    if align not in ('left', 'center', 'right'):
        raise ValueError('Unknown alignment')
    box = checked_rect(list(box), 'box')
    if box not in page.rect:
        raise ValueError('Placement box must be inside canvas')
    source = block[0]
    info = page_info(block, 1, {})
    if info['image_info'] or info['hidden_chars'] or not info['visible_candidate_chars']:
        raise ValueError('Block must contain visible font text, without raster or hidden text')
    if info['unknown_unicode_chars'] or any(not f['embedded_program'] for f in info['fonts']):
        raise ValueError('Block needs readable Unicode and embedded font programs')
    if visible_geometry(source):
        raise ValueError('Compiled block already has text beyond its page; fix TeX overflow')
    if source.rect.width > box.width + 0.01 or source.rect.height > box.height + 0.01:
        raise ValueError('Natural block size exceeds target box; fix source layout, do not shrink')
    offset = {'left': 0, 'center': 0.5, 'right': 1}[align]
    x = box.x0 + (box.width - source.rect.width) * offset
    target = fitz.Rect(x, box.y0, x + source.rect.width, box.y0 + source.rect.height)
    for values in protected:
        protection = checked_rect(list(values), 'protected region')
        if protection not in page.rect:
            raise ValueError('Protected region must be inside canvas')
        if not (target & protection).is_empty:
            raise ValueError('Placement intersects a protected region')
    page.show_pdf_page(target, block, 0, keep_proportion=True)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('block', help='Reviewed, single-page compiled PDF block')
    parser.add_argument('--canvas', type=float, nargs=2, required=True, metavar=('WIDTH', 'HEIGHT'))
    parser.add_argument('--box', type=float, nargs=4, required=True, metavar=('X0', 'Y0', 'X1', 'Y1'))
    parser.add_argument('--align', choices=('left', 'center', 'right'), default='left')
    parser.add_argument('--protect', type=float, nargs=4, action='append', default=[])
    parser.add_argument('--output', required=True, help='New overlay PDF; not a rebuilt book')
    args = parser.parse_args()
    if any(not math.isfinite(x) or x <= 0 for x in args.canvas):
        raise ValueError('Canvas dimensions must be finite and positive')
    path, block = open_pdf(args.block)
    output_guard(args.output, [path])
    before = sha256(path)
    with block, fitz.open() as doc:
        page = doc.new_page(width=args.canvas[0], height=args.canvas[1])
        target = place_block(page, block, args.box, args.align, args.protect)
        if before != sha256(path):
            raise ValueError('Input changed during placement')
        write_new(args.output, doc.tobytes(garbage=4, deflate=True), [path])
    print('Overlay only; natural-size placement:', list(target))
    return 0


if __name__ == '__main__':
    raise SystemExit(run(main))
