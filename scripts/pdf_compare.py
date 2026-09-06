#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["pymupdf==1.26.5"]
# ///
"""Make side-by-side comparison of one-to-one, same-size pages. Inputs are unchanged."""
import argparse
from pdf_common import fitz, open_pdf, output_guard, pages_arg, run, sha256, write_new


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('original')
    parser.add_argument('rebuilt')
    parser.add_argument('--source-pages', required=True, help='Source physical pages in output order; must match rebuilt page count')
    parser.add_argument('--output', required=True, help='New comparison PDF path')
    parser.add_argument('--dpi', type=int, default=180, help='Original-side raster DPI, default 180 (36..600)')
    parser.add_argument('--password-env', help='Environment variable holding original PDF password')
    args = parser.parse_args()
    if not 36 <= args.dpi <= 600:
        raise ValueError('--dpi must be within 36..600.')
    source_path, source = open_pdf(args.original, args.password_env)
    target_path, rebuilt = open_pdf(args.rebuilt)
    output_guard(args.output, [source_path, target_path])
    with source, rebuilt, fitz.open() as result:
        selected = pages_arg(args.source_pages, len(source))
        if len(selected) != len(rebuilt):
            raise ValueError('Selected source page count must equal rebuilt page count. Complex mappings require a normalized reference PDF.')
        before = [sha256(source_path), sha256(target_path)]
        for index, number in enumerate(selected):
            a, b = source[number - 1], rebuilt[index]
            w, h = a.rect.width, a.rect.height
            if abs(w - b.rect.width) > .1 or abs(h - b.rect.height) > .1:
                raise ValueError(f'Page {number} geometry differs. Create and record a same-size normalized reference before using this helper.')
            page = result.new_page(width=2*w + 48, height=h + 52)
            page.draw_rect(page.rect, color=None, fill=(.94, .945, .95))
            page.insert_text((16, 21), f'ORIGINAL | PDF page {number}', fontsize=10, color=(.25, .28, .3))
            page.insert_text((w + 32, 21), f'REBUILT | output page {index + 1}', fontsize=10, color=(.8, .22, .07))
            left, right = fitz.Rect(16, 33, w+16, h+33), fitz.Rect(w+32, 33, 2*w+32, h+33)
            page.draw_rect(right, color=None, fill=(1, 1, 1))
            pix = a.get_pixmap(dpi=args.dpi, colorspace=fitz.csRGB, alpha=False, annots=True)
            page.insert_image(left, stream=pix.tobytes('png'), keep_proportion=False)
            # Embeds visible page content, not document tags, navigation or annotations.
            if b.get_contents():
                page.show_pdf_page(right, rebuilt, index)
        result.set_toc([[1, f'Source {n} / output {i+1}', i+1] for i, n in enumerate(selected)])
        result.set_metadata({'title': 'Original / rebuilt comparison',
                             'subject': f'Left side rasterized at {args.dpi} DPI; inspect original PDF for finer evidence.'})
        if before != [sha256(source_path), sha256(target_path)]:
            raise ValueError('An input changed during comparison; retry against stable inputs.')
        write_new(args.output, result.tobytes(garbage=4, deflate=True), [source_path, target_path])
    print(f'Wrote {len(selected)} comparison pages: {args.output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(run(main))
