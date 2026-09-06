#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["pymupdf==1.26.5"]
# ///
"""Fail closed on audit failures, unverified structures and incomplete review evidence."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from pdf_common import fitz, json_bytes, open_pdf, output_guard, pages_arg, run, sha256, structure, write_new
from pdf_style_check import check_styles


def artifact(reference, base):
    """Read only explicit task-local evidence; reject missing, stale or escaping paths."""
    if not isinstance(reference, dict) or not isinstance(reference.get('path'), str):
        raise ValueError('Evidence must name a task-local file and its SHA-256')
    relative = Path(reference['path'])
    if relative.is_absolute():
        raise ValueError('Evidence paths must be relative to the review JSON directory')
    path = (base / relative).resolve(strict=True)
    path.relative_to(base.resolve())
    if not path.is_file() or sha256(path) != reference.get('sha256'):
        raise ValueError('Evidence is not a file or its SHA-256 does not match')
    return path


def image_fingerprint(path):
    """Detect renamed/re-encoded copies by decoded pixels, not evidence filename."""
    pix = fitz.Pixmap(str(path))
    if pix.colorspace is None:
        raise ValueError('Page/detail evidence must be a decoded color or grayscale image')
    if pix.colorspace.n != 3:
        pix = fitz.Pixmap(fitz.csRGB, pix)
    if pix.alpha:
        pix = fitz.Pixmap(pix, 0)
    return pix.width, pix.height, hashlib.sha256(pix.samples).hexdigest()


def review_records(review, base, source_hash, output_hash, selected, source_structure, target_structure, target_doc):
    blockers, raster, empty, evidence_seen = [], set(), set(), set()

    def block(code, page=None, detail=None):
        blockers.append({'code': code, 'output_page': page, 'detail': detail})

    def evidence(ref, page=None):
        try:
            return artifact(ref, base)
        except (ValueError, OSError) as exc:
            block('missing-or-stale-evidence', page, str(exc))
            return None

    def image_evidence(ref, page):
        path = evidence(ref, page)
        if path is not None:
            try:
                return image_fingerprint(path)
            except (ValueError, RuntimeError, OSError) as exc:
                block('invalid-page-review-image', page, str(exc))
        return None

    if not isinstance(review, dict) or review.get('schema') != 'scan-book-retypeset/review-v2':
        block('review-v2-required', detail='Legacy narrative reports cannot authorize completion')
        return blockers, raster, empty
    for key, expected in [('source_sha256', source_hash), ('rebuilt_sha256', output_hash), ('source_pages', selected)]:
        if review.get(key) != expected:
            block('review-not-bound-to-current-inputs', detail=key)
    if not isinstance(review.get('source_pages'), list) or any(type(n) is not int for n in review['source_pages']):
        block('review-not-bound-to-current-inputs', detail='source_pages must contain integers')
    if review.get('unresolved') != []:
        block('unresolved-or-unrecorded-items')
    exceptions = review.get('exceptions', [])
    if not isinstance(exceptions, list):
        block('invalid-exceptions')
        exceptions = []
    for exception in exceptions:
        if not isinstance(exception, dict):
            block('invalid-exception')
            continue
        page, kind = exception.get('output_page'), exception.get('kind')
        if isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= len(selected) or kind not in ('blank', 'artwork', 'verified-background'):
            block('invalid-exception', detail='Only bounded blank, artwork and verified-background exceptions are supported')
            continue
        if not isinstance(exception.get('reason'), str) or not exception['reason'].strip():
            block('exception-without-reason', page)
            continue
        if evidence(exception.get('evidence'), page) is None:
            continue
        if kind == 'verified-background' and evidence(exception.get('text_removed_diagnostic'), page) is None:
            continue
        raster.add(page)
        if kind in ('blank', 'artwork'):
            empty.add(page)
    rows = review.get('pages', [])
    if not isinstance(rows, list):
        rows = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            block('invalid-page-review')
            continue
        page = row.get('output_page')
        if isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= len(selected) or page in seen:
            block('invalid-or-duplicate-page-review')
            continue
        seen.add(page)
        if type(row.get('source_page')) is not int or row['source_page'] != selected[page - 1] or row.get('status') != 'reviewed':
            block('page-not-reviewed-or-mapping-wrong', page)
        checks = row.get('checks', {})
        if not isinstance(checks, dict):
            checks = {}
        for key in ('content', 'layout', 'images', 'math'):
            allowed = ('pass', 'not-applicable') if key in ('images', 'math') else ('pass',)
            if checks.get(key) not in allowed:
                block('page-check-incomplete', page, key)
        if not isinstance(row.get('notes'), str) or not row['notes'].strip():
            block('page-review-findings-missing', page)
        full = image_evidence(row.get('full_page'), page)
        if full is not None:
            if full in evidence_seen:
                block('contact-sheet-reused-as-page-review', page)
            evidence_seen.add(full)
        details = row.get('details')
        if not isinstance(details, list) or not details:
            block('detail-review-missing', page)
        else:
            for ref in details:
                detail = image_evidence(ref, page)
                if detail is not None and detail == full:
                    block('full-page-image-is-not-detail-evidence', page)
    for page in sorted(set(range(1, len(selected) + 1)) - seen):
        block('page-review-missing', page)
    structures = review.get('structure', {})
    if not isinstance(structures, dict):
        structures = {}
    for kind, catalog_key in [('navigation', None), ('tags', 'StructTreeRoot'), ('optional_content', 'OCProperties')]:
        row = structures.get(kind, {})
        if not isinstance(row, dict):
            row = {}
        present = catalog_key is None or source_structure['catalog_entries'][catalog_key] or target_structure['catalog_entries'][catalog_key]
        expected = ('new-content-verified' if kind == 'tags' else 'verified') if present else 'not-present'
        if row.get('status') != expected:
            block('structure-verification-incomplete', detail={'kind': kind, 'required': expected})
        if present:
            evidence(row.get('evidence'))
    calibration = evidence(review.get('style_plan'))
    if calibration is not None:
        try:
            with calibration.open(encoding='utf-8') as stream:
                styles = check_styles(target_doc, json.load(stream), source_hash)
            for issue in styles['issues']:
                block('style-check-failed', issue.get('output_page'), issue)
        except (ValueError, OSError, TypeError, KeyError) as exc:
            block('invalid-style-plan', detail=str(exc))
    return blockers, raster, empty


def evaluate(original, rebuilt, selected, review_path, password_env=None):
    source_path, source = open_pdf(original, password_env)
    output_path, target = open_pdf(rebuilt)
    review_path = Path(review_path).resolve(strict=True)
    source_hash, output_hash, review_hash = sha256(source_path), sha256(output_path), sha256(review_path)
    with source, target:
        if len(selected) != len(target):
            raise ValueError('Source selection must map one-to-one to the output')
        with review_path.open(encoding='utf-8') as stream:
            review = json.load(stream)
        blockers, raster, empty = review_records(review, review_path.parent, source_hash, output_hash, selected,
                                                 structure(source), structure(target), target)
    with tempfile.TemporaryDirectory(prefix='pdf-delivery-audit-') as temporary:
        audit_path = Path(temporary) / 'audit.json'
        cmd = [sys.executable, str(Path(__file__).with_name('pdf_audit.py')), str(source_path), str(output_path),
               '--source-pages', ','.join(map(str, selected)), '--report', str(audit_path)]
        if password_env:
            cmd.extend(['--password-env', password_env])
        if raster:
            cmd.extend(['--allow-raster-pages', ','.join(map(str, sorted(raster)))])
        if empty:
            cmd.extend(['--allow-no-text-pages', ','.join(map(str, sorted(empty)))])
        proc = subprocess.run(cmd, text=True, capture_output=True)
        if proc.returncode not in (0, 1) or not audit_path.is_file():
            raise ValueError('Independent structural audit failed to run: ' + proc.stderr[-800:])
        audit = json.loads(audit_path.read_text(encoding='utf-8'))
    for issue in audit['issues']:
        blockers.append({'code': 'structural-audit-blocker', 'output_page': issue.get('output_page'), 'detail': issue['code']})
    if any(sha256(path) != expected for path, expected in [(source_path, source_hash), (output_path, output_hash), (review_path, review_hash)]):
        raise ValueError('An input changed during delivery validation')
    return {'schema': 'scan-book-retypeset/delivery-gate-v1',
            'status': 'blocked' if blockers else 'evidence-consistent-review-still-accountable',
            'source_sha256': source_hash, 'rebuilt_sha256': output_hash, 'review_sha256': review_hash,
            'source_pages': selected, 'blocker_count': len(blockers), 'blockers': blockers,
            'audit_issue_counts': dict(Counter(i['code'] for i in audit['issues'])),
            'audit_warnings': audit['warnings'],
            'limitation': 'Validates current artifacts, explicit review coverage and limited measurements. Does not prove that visual/content review was truthful, calibration is correct, or tag internals are valid.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('original')
    parser.add_argument('rebuilt')
    parser.add_argument('--source-pages', required=True)
    parser.add_argument('--review', required=True, help='Review-v2 JSON and task-local evidence root')
    parser.add_argument('--report', required=True, help='New delivery gate JSON')
    parser.add_argument('--password-env')
    args = parser.parse_args()
    inputs = [args.original, args.rebuilt, args.review]
    output_guard(args.report, inputs)
    _, source = open_pdf(args.original, args.password_env)
    with source:
        selected = pages_arg(args.source_pages, len(source))
    report = evaluate(args.original, args.rebuilt, selected, args.review, args.password_env)
    write_new(args.report, json_bytes(report), inputs)
    print(f"{report['status']}: {report['blocker_count']} blockers")
    return 1 if report['blocker_count'] else 0


if __name__ == '__main__':
    raise SystemExit(run(main))
