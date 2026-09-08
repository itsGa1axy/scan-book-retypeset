#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["pymupdf==1.26.5"]
# ///
"""Report limited structural differences. Exit 0 still requires content, visual and navigation review."""
import argparse
import json
from collections import Counter
from pdf_common import fitz, json_bytes, open_pdf, output_guard, page_info, pages_arg, projected_outline, run, serial, sha256, structure, visible_geometry, write_new


def outline_paths(rows):
    result, stack = [], []
    for row in rows:
        level, title, target = row[:3]
        while stack and stack[-1][0] >= level:
            stack.pop()
        path = tuple(x[1] for x in stack) + (title,)
        result.append((path, level, target))
        stack.append((level, title))
    return result


def link_targets(links, mapping=None):
    values = []
    for link in links:
        kind = link.get('kind')
        if kind == fitz.LINK_URI:
            values.append(('uri', link.get('uri')))
        elif kind == fitz.LINK_GOTO:
            target = link.get('page', -1) + 1
            if mapping is not None:
                if target not in mapping:
                    continue
                target = mapping[target]
            values.append(('goto', target))
        else:
            # A URI may be exposed as Launch / GoToR (e.g. malformed file: URLs).
            # Never silently omit unsupported actions from the loss check.
            target_fields = {key: serial(link[key]) for key in
                             ('uri', 'file', 'page', 'to', 'nameddest', 'name', 'zoom') if key in link}
            values.append(('other-action', kind, json.dumps(target_fields, ensure_ascii=False, sort_keys=True)))
    return Counter(values)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('original')
    parser.add_argument('rebuilt')
    parser.add_argument('--source-pages', required=True, help='1-based original pages in output order')
    parser.add_argument('--report', required=True, help='New JSON report path')
    parser.add_argument('--allow-raster-pages', help='Output pages with documented full-page image exceptions, e.g. a cover')
    parser.add_argument('--allow-no-text-pages', help='Output pages verified as blank, pure artwork or outline-only formulas')
    parser.add_argument('--password-env', help='Environment variable holding original PDF password')
    args = parser.parse_args()
    source_path, source = open_pdf(args.original, args.password_env)
    target_path, rebuilt = open_pdf(args.rebuilt)
    output_guard(args.report, [source_path, target_path])
    issues, warnings, results = [], [], []

    def issue(code, page=None, detail=None):
        issues.append({'code': code, 'output_page': page, 'detail': detail})

    with source, rebuilt:
        selected = pages_arg(args.source_pages, len(source))
        if len(selected) != len(rebuilt):
            raise ValueError('Selected source page count must equal rebuilt page count; complex mapping needs a normalized reference.')
        allowed_raster = set(pages_arg(args.allow_raster_pages, len(rebuilt))) if args.allow_raster_pages else set()
        allowed_empty = set(pages_arg(args.allow_no_text_pages, len(rebuilt))) if args.allow_no_text_pages else set()
        original_hash, rebuilt_hash = sha256(source_path), sha256(target_path)
        st, rt = structure(source), structure(rebuilt)
        for key in ('StructTreeRoot', 'OCProperties'):
            if st['catalog_entries'][key] and not rt['catalog_entries'][key]:
                issue('document-structure-entry-removed', detail=key)
            elif st['catalog_entries'][key]:
                warnings.append({'code': 'structure-internals-review-required', 'detail': key})
        expected_outline = projected_outline(st['outline'], selected)
        expected_paths, actual_paths = outline_paths(expected_outline), outline_paths(rt['outline'])
        remaining = iter(actual_paths)
        # Subsequence permits newly added, justified nodes without accepting reordered originals.
        for path, level, target in expected_paths:
            match = next((row for row in remaining if row[0] == path and row[1] == level), None)
            if match is None:
                issue('outline-node-or-hierarchy-missing', detail={'path': path, 'level': level})
                break
            if target > 0 and match[2] != target:
                issue('outline-destination-mismatch', detail={'path': path, 'expected': target, 'actual': match[2]})
        for row in rt['outline']:
            if row[2] > len(rebuilt):
                issue('outline-destination-out-of-range', detail=row[:3])
        if not expected_outline and not rt['outline']:
            warnings.append({'code': 'no-outline', 'detail': 'Inspect heading hierarchy; construct navigation when warranted by the source.'})

        source_cache, rebuilt_cache = {}, {}
        mapping = {n: i + 1 for i, n in enumerate(selected)}
        for index, number in enumerate(selected):
            outnum = index + 1
            a, b = page_info(source, number, source_cache), page_info(rebuilt, outnum, rebuilt_cache)
            if any(abs(a['rect'][j] - b['rect'][j]) > .1 for j in range(4)):
                issue('page-size-mismatch', outnum, {'source': a['rect'], 'output': b['rect']})
            if (a['rotation'], a['cropbox']) != (b['rotation'], b['cropbox']):
                warnings.append({'code': 'page-transform-review-required', 'output_page': outnum})
            if b['hidden_chars']:
                issue('hidden-text-in-output', outnum, b['hidden_chars'])
            outside = visible_geometry(rebuilt[index])
            if outside:
                issue('visible-text-outside-page', outnum,
                      {'count': len(outside), 'examples': outside[:12], 'tolerance_pt': 0.5})
            if not b['visible_candidate_chars'] and outnum not in allowed_empty:
                issue('no-visible-text-candidates', outnum)
            if b['unknown_unicode_chars']:
                issue('unknown-unicode', outnum, b['unknown_unicode_chars'])
            unembedded = [f['base_name'] for f in b['fonts'] if not f['embedded_program']]
            if unembedded:
                issue('font-program-not-embedded-or-unreadable', outnum, unembedded)
            large = [im for im in b['image_info'] if im['page_area_ratio'] >= .8]
            if large and outnum not in allowed_raster:
                issue('large-raster-needs-documented-exception', outnum, len(large))
            if a['label'] and a['label'] != b['label']:
                issue('page-label-mismatch', outnum, {'source': a['label'], 'output': b['label']})
            required_links = link_targets(a['links'], mapping)
            missing_links = required_links - link_targets(b['links'])
            if missing_links:
                issue('link-target-missing', outnum, [[k, v] for k, v in missing_links.items()])
            unusual_links = [link for link in a['links'] if link.get('kind') not in (fitz.LINK_URI, fitz.LINK_GOTO)]
            if unusual_links:
                warnings.append({'code': 'nonstandard-link-action-review-required', 'output_page': outnum,
                                 'detail': 'Inspect the raw action without executing it; preserve or repair from source evidence and record changes.'})
            if len(b['annotations']) < len(a['annotations']):
                issue('annotation-count-decreased', outnum)
            results.append({'source_page': number, 'output_page': outnum,
                            'visible_candidate_chars': b['visible_candidate_chars'], 'hidden_chars': b['hidden_chars'],
                            'raster_count': len(b['image_info']), 'large_raster_count': len(large),
                            'link_count': len(b['links']), 'unembedded_fonts': unembedded})
        if original_hash != sha256(source_path) or rebuilt_hash != sha256(target_path):
            raise ValueError('An input changed during audit; rerun against stable inputs.')
        report = {
            'status': 'structural-differences-found' if issues else 'limited-structural-checks-passed-review-required',
            'source_sha256': original_hash, 'rebuilt_sha256': rebuilt_hash, 'source_pages': selected,
            'pymupdf_version': fitz.VersionBind,
            'exceptions': {'allow_raster_output_pages': sorted(allowed_raster), 'allow_no_text_output_pages': sorted(allowed_empty)},
            'expected_outline_subset': expected_outline, 'actual_outline': rt['outline'],
            'issues': issues, 'warnings': warnings, 'pages': results,
            'not_verified': ['OCR/content correctness', 'math semantics', 'text occlusion/clipping',
                             'image fidelity and placement', 'tag-tree internal references', 'OCG membership',
                             'all named destinations, actions and link rectangles', 'full reading order'],
        }
        write_new(args.report, json_bytes(report), [source_path, target_path])
    print(f"{report['status']}: {len(issues)} issues, {len(warnings)} review notices; report: {args.report}")
    return 1 if issues else 0


if __name__ == '__main__':
    raise SystemExit(run(main))
