#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["pymupdf==1.26.5"]
# ///
"""Inspect an explicit PDF page range; optional preview rendering. No OCR."""
import argparse
from pathlib import Path
from pdf_common import fitz, json_bytes, open_pdf, output_guard, page_info, pages_arg, run, sha256, structure, write_new


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input')
    parser.add_argument('--pages', required=True, help='1-based physical pages: 1-10 or 2,5,9')
    parser.add_argument('--output', help='New JSON output path; default prints JSON')
    parser.add_argument('--render-dir', help='Optional directory for selected-page PNG previews')
    parser.add_argument('--dpi', type=int, default=144, help='Preview DPI (36..600), default 144')
    parser.add_argument('--password-env', help='Name of environment variable containing the input PDF password')
    args = parser.parse_args()
    if not 36 <= args.dpi <= 600:
        raise ValueError('--dpi must be within 36..600.')
    path, doc = open_pdf(args.input, args.password_env)
    with doc:
        selected = pages_arg(args.pages, len(doc))
        targets = []
        if args.output:
            targets.append(output_guard(args.output, [path]))
        if args.render_dir:
            targets.extend(output_guard(Path(args.render_dir) / f'page-{n:04d}.png', [path]) for n in selected)
        if len(targets) != len(set(targets)):
            raise ValueError('Report and preview output paths must be distinct.')
        before = sha256(path)
        cache = {}
        report = {'source_name': path.name, 'source_sha256': before, 'page_count': len(doc),
                  'selected_pages': selected, 'pymupdf_version': fitz.VersionBind,
                  'structure': structure(doc), 'pages': [page_info(doc, n, cache) for n in selected]}
        for number in selected if args.render_dir else []:
            pix = doc[number - 1].get_pixmap(dpi=args.dpi, colorspace=fitz.csRGB, alpha=False)
            write_new(Path(args.render_dir) / f'page-{number:04d}.png', pix.tobytes('png'), [path])
        if before != sha256(path):
            raise ValueError('Input changed during inspection; discard the report and inspect the new revision.')
        data = json_bytes(report)
        if args.output:
            write_new(args.output, data, [path])
            print(f'Inspected {len(selected)} selected pages; report: {args.output}')
        else:
            print(data.decode('utf-8'), end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(run(main))
