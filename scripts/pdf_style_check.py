#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["pymupdf==1.26.5"]
# ///
"""Check visible font text against independently calibrated region styles."""
import argparse
import json
import math
import re
from pdf_common import fitz, json_bytes, open_pdf, output_guard, run, sha256, write_new


def finite_list(value, count, label):
    if not isinstance(value, list) or len(value) != count or any(
            isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in value):
        raise ValueError(f'{label} must contain {count} finite numbers')
    return value


def rgb(trace):
    color = trace.get('color', ())
    if isinstance(color, (float, int)):
        color = [color]
    if len(color) == 1:
        return list(color) * 3
    if len(color) == 3:
        return list(color)
    if len(color) == 4:
        c, m, y, k = color
        return [(1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k)]
    return None


def check_styles(doc, plan, source_hash=None):
    if not isinstance(plan, dict) or plan.get('schema') != 'scan-book-retypeset/style-plan-v1':
        raise ValueError('Unsupported or missing style-plan schema')
    if not re.fullmatch('[0-9a-f]{64}', str(plan.get('source_sha256', ''))):
        raise ValueError('Style plan requires a source SHA-256')
    if source_hash is not None and plan['source_sha256'] != source_hash:
        raise ValueError('Style plan belongs to a different source PDF')
    if type(plan.get('output_page_count')) is not int or plan['output_page_count'] != len(doc):
        raise ValueError('Style plan output page count does not match PDF')
    regions = plan.get('regions')
    if not isinstance(regions, list) or not regions:
        raise ValueError('Style plan needs at least one calibrated region')
    issues, results, cache, ids = [], [], {}, set()
    for region in regions:
        if not isinstance(region, dict):
            raise ValueError('Each style region must be an object')
        ident = region.get('id')
        if not isinstance(ident, str) or not ident.strip() or ident in ids:
            raise ValueError('Region IDs must be nonempty and unique')
        ids.add(ident)
        number = region.get('output_page')
        if isinstance(number, bool) or not isinstance(number, int) or not 1 <= number <= len(doc):
            raise ValueError('Invalid output page in style region')
        if not isinstance(region.get('basis'), str) or not region['basis'].strip():
            raise ValueError('Each region needs its independent calibration basis')
        if not isinstance(region.get('role'), str) or not region['role'].strip():
            raise ValueError('Each region needs a semantic role')
        bounds = finite_list(region.get('bbox'), 4, 'bbox')
        box = fitz.Rect(bounds)
        page = doc[number - 1]
        if box.is_empty or box not in page.rect:
            raise ValueError('Region bbox must lie inside the display page')
        expected = region.get('expected', {})
        if not isinstance(expected, dict):
            raise ValueError('Region expected style must be an object')
        low, high = finite_list(expected.get('size_pt'), 2, 'size_pt')
        if not 0 < low <= high:
            raise ValueError('size_pt must be a positive ascending interval')
        fonts = expected.get('fonts')
        if not isinstance(fonts, list) or not fonts or not all(isinstance(f, str) and f.strip() for f in fonts):
            raise ValueError('Expected fonts must be explicit PDF font names')
        color = finite_list(expected.get('color_rgb'), 3, 'color_rgb')
        tolerance = expected.get('color_tolerance', 0.08)
        if any(not 0 <= x <= 1 for x in color) or isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or not math.isfinite(tolerance) or not 0 <= tolerance <= 1:
            raise ValueError('RGB and color tolerance must be finite values in 0..1')
        expected_count = expected.get('nonspace_chars')
        if 'nonspace_chars' in expected and (isinstance(expected_count, bool) or not isinstance(expected_count, int) or expected_count < 1):
            raise ValueError('nonspace_chars must be a positive integer when supplied')
        content_box = None
        if 'content_bbox' in expected:
            content_box = fitz.Rect(finite_list(expected['content_bbox'], 4, 'content_bbox'))
            if content_box.is_empty or content_box not in box:
                raise ValueError('content_bbox must be inside the selection bbox')
        if number not in cache:
            cache[number] = page.get_texttrace()
        count, mismatches = 0, {'size': [], 'font': [], 'color': []}
        if content_box is not None:
            mismatches['bounds'] = []
        for trace in cache[number]:
            if trace['type'] not in (0, 1) or trace.get('opacity', 1) <= 0:
                continue
            font = re.sub(r'^[A-Z]{6}\+', '', trace['font'])
            actual_rgb = rgb(trace)
            for code, _, origin, bbox in trace['chars']:
                char = chr(code) if 0 <= code <= 0x10ffff else '\ufffd'
                if char.isspace():
                    continue
                rect = fitz.Rect(bbox) * page.rotation_matrix
                midpoint = (rect.tl + rect.br) / 2
                if midpoint not in box:
                    continue
                count += 1
                item = {'char': char, 'bbox': list(rect), 'size_pt': trace['size'], 'font': font, 'color_rgb': actual_rgb}
                if content_box is not None and rect not in content_box:
                    mismatches['bounds'].append(item)
                if not low <= trace['size'] <= high:
                    mismatches['size'].append(item)
                if font not in fonts:
                    mismatches['font'].append(item)
                if actual_rgb is None or max(abs(a-b) for a, b in zip(actual_rgb, color)) > tolerance:
                    mismatches['color'].append(item)
        if not count:
            issues.append({'code': 'calibrated-region-has-no-visible-text', 'output_page': number, 'region_id': ident})
        if expected_count is not None and count != expected_count:
            issues.append({'code': 'calibrated-character-count-mismatch', 'output_page': number,
                           'region_id': ident, 'expected': expected_count, 'actual': count})
        for key, items in mismatches.items():
            if items:
                issues.append({'code': f'calibrated-{key}-mismatch', 'output_page': number,
                               'region_id': ident, 'count': len(items), 'examples': items[:12]})
        results.append({'region_id': ident, 'output_page': number, 'visible_chars_checked': count,
                        'mismatch_counts': {k: len(v) for k, v in mismatches.items()}})
    return {'schema': 'scan-book-retypeset/style-check-v1',
            'status': 'style-differences-found' if issues else 'calibrated-regions-passed',
            'issues': issues, 'regions': results,
            'not_verified': ['calibration truth', 'unlisted regions', 'text content', 'occlusion', 'horizontal glyph distortion', 'raster fidelity', 'tag associations']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf')
    parser.add_argument('--plan', required=True, help='Independent region style plan JSON')
    parser.add_argument('--report', required=True, help='New JSON output path')
    args = parser.parse_args()
    path, doc = open_pdf(args.pdf)
    inputs = [path, args.plan]
    output_guard(args.report, inputs)
    before, plan_hash = sha256(path), sha256(args.plan)
    with doc:
        with open(args.plan, encoding='utf-8') as stream:
            report = check_styles(doc, json.load(stream))
    if before != sha256(path) or plan_hash != sha256(args.plan):
        raise ValueError('PDF or plan changed during style check')
    report.update(rebuilt_sha256=before, plan_sha256=plan_hash)
    write_new(args.report, json_bytes(report), inputs)
    print(f"{report['status']}: {len(report['issues'])} issues")
    return 1 if report['issues'] else 0


if __name__ == '__main__':
    raise SystemExit(run(main))
