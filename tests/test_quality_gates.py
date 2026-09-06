"""Behavioral CLI checks using temporary PDFs and PyMuPDF's bundled fonts.

These tests verify measured styles, evidence bookkeeping and an independent
audit. They do not certify calibration truth, text semantics or tag internals.
No production helper is imported, and every CLI call checks existing inputs
byte-for-byte so failures cannot quietly damage fixtures or evidence.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import pymupdf as fitz


ROOT = Path(__file__).resolve().parents[1]
REGION = [25, 45, 180, 105]
BODY_COLOR = [0.125, 0.25, 0.375]
BODY_FONT = 'NimbusRoman-Regular'
OTHER_FONT = 'NimbusSans-Regular'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def make_pdf(path, page_count=2, size=12, color=BODY_COLOR, font='tiro',
             empty=False, hidden=False, rotation=0, tags=False,
             names=('Alice', 'Bob')):
    """Embed bundled programs, including on deliberately bad style variants."""
    with fitz.open() as doc:
        for index in range(page_count):
            page = doc.new_page(width=300, height=400)
            page.insert_font(fontname='body', fontbuffer=fitz.Font(font).buffer)
            page.insert_font(fontname='heading', fontbuffer=fitz.Font('helv').buffer)
            # An uncalibrated heading deliberately differs from the name list.
            page.insert_text((30, 30), 'Page {}'.format(index + 1),
                             fontname='heading', fontsize=20, color=(0.7, 0, 0))
            if not empty:
                for y, name in zip((70, 90), names):
                    page.insert_text((30, y), '{} {}'.format(name, index + 1),
                                     fontname='body', fontsize=size, color=color)
            if hidden:
                page.insert_text((30, 140), 'Hidden transcription',
                                 fontname='body', fontsize=12, render_mode=3)
            page.set_rotation(rotation)
        if tags:
            # Catalog presence alone gives no proof of a valid content tree.
            xref = doc.get_new_xref()
            doc.update_object(xref, '<< /Type /StructTreeRoot /K [] >>')
            doc.xref_set_key(doc.pdf_catalog(), 'StructTreeRoot', '{} 0 R'.format(xref))
            doc.xref_set_key(doc.pdf_catalog(), 'MarkInfo', '<< /Marked true >>')
        doc.save(path)


class QualityGateFixture(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix='quality-gates-test-')
        self.addCleanup(scratch.cleanup)
        self.directory = Path(scratch.name)
        self.source = self.directory / 'source.pdf'
        self.rebuilt = self.directory / 'rebuilt.pdf'
        self.plan_path = self.directory / 'style-plan.json'
        self.review_path = self.directory / 'review.json'
        self.sequence = 0
        make_pdf(self.source)
        shutil.copyfile(self.source, self.rebuilt)
        self.plan = self.make_plan()
        write_json(self.plan_path, self.plan)

    def make_plan(self, page_count=2, rotation=0):
        bbox = list(REGION)
        if rotation:
            with fitz.open(self.rebuilt) as doc:
                bbox = list(fitz.Rect(REGION) * doc[0].rotation_matrix)
        return {
            'schema': 'scan-book-retypeset/style-plan-v1',
            'source_sha256': digest(self.source),
            'output_page_count': page_count,
            'regions': [{
                'id': 'names-{}'.format(page),
                'output_page': page,
                'role': 'name-list',
                'basis': 'Fixture list independently specified at 12 pt in embedded Times.',
                'bbox': list(bbox),
                'expected': {
                    'size_pt': [11.9, 12.1],
                    'fonts': [BODY_FONT],
                    'color_rgb': list(BODY_COLOR),
                    'color_tolerance': 0.01,
                },
            } for page in range(1, page_count + 1)],
        }

    def reference(self, path):
        return {'path': path.relative_to(self.directory).as_posix(),
                'sha256': digest(path)}

    def make_review(self):
        evidence = self.directory / 'evidence'
        evidence.mkdir(exist_ok=True)
        rows = []
        with fitz.open(self.rebuilt) as doc:
            for index, page in enumerate(doc):
                full = evidence / 'page-{}.png'.format(index + 1)
                detail = evidence / 'detail-{}.png'.format(index + 1)
                page.get_pixmap().save(full)
                page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=fitz.Rect(REGION)).save(detail)
                rows.append({
                    'output_page': index + 1,
                    'source_page': index + 1,
                    'status': 'reviewed',
                    'checks': {'content': 'pass', 'layout': 'pass',
                               'images': 'not-applicable', 'math': 'not-applicable'},
                    'notes': 'Two names and the page heading were compared with the fixture source.',
                    'full_page': self.reference(full),
                    'details': [self.reference(detail)],
                })
        navigation = evidence / 'navigation.json'
        write_json(navigation, {'source_outline': [], 'rebuilt_outline': [],
                                'source_pages': list(range(1, len(rows) + 1))})
        return {
            'schema': 'scan-book-retypeset/review-v2',
            'source_sha256': digest(self.source),
            'rebuilt_sha256': digest(self.rebuilt),
            'source_pages': list(range(1, len(rows) + 1)),
            'unresolved': [],
            'exceptions': [],
            'pages': rows,
            'structure': {
                'navigation': {'status': 'verified', 'evidence': self.reference(navigation)},
                'tags': {'status': 'not-present'},
                'optional_content': {'status': 'not-present'},
            },
            'style_plan': self.reference(self.plan_path),
        }

    def new_report(self):
        self.sequence += 1
        return self.directory / 'report-{}.json'.format(self.sequence)

    def cli(self, script, arguments, expected):
        before = {path: path.read_bytes() for path in self.directory.rglob('*') if path.is_file()}
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        result = subprocess.run(
            [sys.executable, str(ROOT / 'scripts' / script)] + [str(arg) for arg in arguments],
            cwd=self.directory, env=env, text=True, capture_output=True, timeout=30,
        )
        for path, original in before.items():
            self.assertTrue(path.is_file(), 'CLI removed input {}'.format(path.name))
            self.assertEqual(path.read_bytes(), original, 'CLI modified input {}'.format(path.name))
        self.assertEqual(result.returncode, expected,
                         '{}\nstdout: {}\nstderr: {}'.format(script, result.stdout, result.stderr))
        return result

    def style(self, expected=0, report_path=None):
        report_path = report_path if report_path is not None else self.new_report()
        self.cli('pdf_style_check.py',
                 [self.rebuilt, '--plan', self.plan_path, '--report', report_path], expected)
        if expected == 2:
            self.assertFalse(report_path.exists())
            return None
        report = json.loads(report_path.read_text(encoding='utf-8'))
        self.assertEqual(report['rebuilt_sha256'], digest(self.rebuilt))
        self.assertEqual(report['plan_sha256'], digest(self.plan_path))
        self.assertEqual(bool(report['issues']), expected == 1)
        return report

    def delivery_arguments(self, report_path, pages='1-2'):
        return [self.source, self.rebuilt, '--source-pages', pages,
                '--review', self.review_path, '--report', report_path]

    def gate(self, review, expected=0, pages='1-2'):
        write_json(self.review_path, review)
        report_path = self.new_report()
        self.cli('pdf_delivery_gate.py', self.delivery_arguments(report_path, pages), expected)
        if expected == 2:
            self.assertFalse(report_path.exists())
            return None
        report = json.loads(report_path.read_text(encoding='utf-8'))
        self.assertEqual(report['source_sha256'], digest(self.source))
        self.assertEqual(report['rebuilt_sha256'], digest(self.rebuilt))
        self.assertEqual(report['review_sha256'], digest(self.review_path))
        self.assertEqual(report['blocker_count'], len(report['blockers']))
        self.assertEqual(bool(report['blockers']), expected == 1)
        return report

    def assert_blocker(self, report, code, page=None):
        matches = [item for item in report['blockers'] if item['code'] == code]
        self.assertTrue(matches, report)
        if page is not None:
            self.assertIn(page, [item['output_page'] for item in matches])
        return matches


class StyleCheckTests(QualityGateFixture):
    def test_calibrated_name_regions_pass_with_measured_character_counts(self):
        report = self.style()
        self.assertEqual(report['issues'], [])
        self.assertEqual(len(report['regions']), 2)
        for row in report['regions']:
            # Alice + Bob + two page digits; spaces and the heading are excluded.
            self.assertEqual(row['visible_chars_checked'], 10)
            self.assertEqual(row['mismatch_counts'], {'size': 0, 'font': 0, 'color': 0})

    def test_larger_name_list_is_rejected_with_actual_sizes(self):
        make_pdf(self.rebuilt, size=16)
        report = self.style(expected=1)
        self.assertEqual({item['code'] for item in report['issues']}, {'calibrated-size-mismatch'})
        for issue in report['issues']:
            self.assertEqual(issue['count'], 10)
            self.assertTrue(all(item['size_pt'] == 16 for item in issue['examples']))

    def test_inconsistent_name_color_is_rejected_with_actual_rgb(self):
        make_pdf(self.rebuilt, color=(0.8, 0.1, 0.2))
        report = self.style(expected=1)
        self.assertEqual({item['code'] for item in report['issues']}, {'calibrated-color-mismatch'})
        for issue in report['issues']:
            self.assertEqual(issue['count'], 10)
            for item in issue['examples']:
                for actual, expected in zip(item['color_rgb'], (0.8, 0.1, 0.2)):
                    self.assertAlmostEqual(actual, expected, places=5)

    def test_wrong_name_font_is_rejected_with_actual_font(self):
        make_pdf(self.rebuilt, font='helv')
        report = self.style(expected=1)
        self.assertEqual({item['code'] for item in report['issues']}, {'calibrated-font-mismatch'})
        for issue in report['issues']:
            self.assertEqual(issue['count'], 10)
            self.assertEqual({item['font'] for item in issue['examples']}, {OTHER_FONT})

    def test_empty_calibrated_regions_rejected_despite_heading_text(self):
        make_pdf(self.rebuilt, empty=True)
        report = self.style(expected=1)
        self.assertEqual({item['code'] for item in report['issues']},
                         {'calibrated-region-has-no-visible-text'})
        self.assertEqual({item['output_page'] for item in report['issues']}, {1, 2})
        self.assertTrue(all(row['visible_chars_checked'] == 0 for row in report['regions']))

    def test_font_allowlist_and_inclusive_measurement_boundaries(self):
        make_pdf(self.rebuilt, font='helv', color=(0.1875, 0.25, 0.375))
        for row in self.plan['regions']:
            row['expected'].update(size_pt=[12, 12], fonts=[BODY_FONT, OTHER_FONT],
                                   color_tolerance=0.0625)
        write_json(self.plan_path, self.plan)
        self.assertEqual(self.style()['issues'], [])
        make_pdf(self.rebuilt, font='helv', color=(0.2, 0.25, 0.375))
        self.assertEqual({item['code'] for item in self.style(expected=1)['issues']},
                         {'calibrated-color-mismatch'})

    def test_rotated_page_uses_display_coordinates(self):
        make_pdf(self.rebuilt, rotation=90)
        self.plan = self.make_plan(rotation=90)
        write_json(self.plan_path, self.plan)
        self.assertEqual([row['visible_chars_checked'] for row in self.style()['regions']], [10, 10])

    def test_explicit_nonspace_character_count_passes(self):
        for region in self.plan['regions']:
            region['expected']['nonspace_chars'] = 10
        write_json(self.plan_path, self.plan)
        report = self.style()
        self.assertEqual(report['issues'], [])
        self.assertEqual([row['visible_chars_checked'] for row in report['regions']], [10, 10])

    def test_three_missing_name_characters_fail_despite_matching_styles(self):
        for region in self.plan['regions']:
            region['expected']['nonspace_chars'] = 10
        write_json(self.plan_path, self.plan)
        make_pdf(self.rebuilt, names=('Al', 'Bob'))
        report = self.style(expected=1)
        self.assertEqual({issue['code'] for issue in report['issues']},
                         {'calibrated-character-count-mismatch'})
        self.assertEqual({issue['output_page'] for issue in report['issues']}, {1, 2})
        for issue in report['issues']:
            self.assertEqual(issue['expected'], 10)
            self.assertEqual(issue['actual'], 7)
        for row in report['regions']:
            self.assertEqual(row['visible_chars_checked'], 7)
            self.assertEqual(row['mismatch_counts'], {'size': 0, 'font': 0, 'color': 0})

    def test_invalid_declared_character_counts_fail_without_report(self):
        for value in (0, -1, True, False, 10.0, '10', [], {}, float('inf'), float('nan'), None):
            with self.subTest(nonspace_chars=value):
                plan = copy.deepcopy(self.plan)
                plan['regions'][0]['expected']['nonspace_chars'] = value
                write_json(self.plan_path, plan)
                self.style(expected=2)

    def test_invalid_or_empty_plans_fail_without_a_report(self):
        invalid = [None, [], {}, {'schema': 'scan-book-retypeset/style-plan-v0'}]
        for patch in ({'regions': []}, {'regions': None}, {'regions': [None]},
                      {'output_page_count': 3}, {'source_sha256': 'not-a-digest'}):
            plan = copy.deepcopy(self.plan)
            plan.update(patch)
            invalid.append(plan)
        for index, plan in enumerate(invalid):
            with self.subTest(case=index):
                write_json(self.plan_path, plan)
                self.style(expected=2)
        self.plan_path.write_text('{', encoding='utf-8')
        self.style(expected=2)

    def test_invalid_region_bounds_and_fields_fail_closed(self):
        cases = [
            ('bbox', [-1, 45, 180, 105]),
            ('bbox', [25, 45, 301, 105]),
            ('bbox', [25, 45, 180, 401]),
            ('bbox', [25, 45, 25, 105]),
            ('bbox', [180, 45, 25, 105]),
            ('bbox', [25, 45, 180]),
            ('bbox', [True, 45, 180, 105]),
            ('bbox', [float('nan'), 45, 180, 105]),
            ('bbox', [25, 45, float('inf'), 105]),
            ('output_page', 0), ('output_page', 3), ('output_page', True),
            ('basis', ''), ('role', ''), ('id', ''), ('expected', []),
        ]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                plan = copy.deepcopy(self.plan)
                plan['regions'][0][field] = value
                write_json(self.plan_path, plan)
                self.style(expected=2)
        plan = copy.deepcopy(self.plan)
        plan['regions'][1]['id'] = plan['regions'][0]['id']
        write_json(self.plan_path, plan)
        self.style(expected=2)

    def test_invalid_expected_style_values_fail_closed(self):
        cases = [
            ('size_pt', [0, 12]), ('size_pt', [13, 12]),
            ('size_pt', [12, float('inf')]), ('size_pt', [False, 12]),
            ('fonts', []), ('fonts', ['']), ('fonts', 'Times-Roman'),
            ('color_rgb', [-0.01, 0, 0]), ('color_rgb', [0, 0, 1.01]),
            ('color_rgb', [0, 0]), ('color_tolerance', -0.1),
            ('color_tolerance', 1.1), ('color_tolerance', True),
            ('color_tolerance', float('nan')),
        ]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                plan = copy.deepcopy(self.plan)
                plan['regions'][0]['expected'][field] = value
                write_json(self.plan_path, plan)
                self.style(expected=2)


class DeliveryGateTests(QualityGateFixture):
    def test_complete_review_v2_evidence_passes(self):
        report = self.gate(self.make_review())
        self.assertEqual(report['blockers'], [])
        self.assertEqual(report['audit_issue_counts'], {})
        self.assertEqual(report['source_pages'], [1, 2])

    def test_legacy_completion_narrative_cannot_authorize_delivery(self):
        for schema in (None, 'scan-book-retypeset/review-v1'):
            with self.subTest(schema=schema):
                review = self.make_review()
                if schema is None:
                    del review['schema']
                else:
                    review['schema'] = schema
                review.update(status='complete', completed=True)
                report = self.gate(review, expected=1)
                self.assert_blocker(report, 'review-v2-required')
                self.assertEqual(report['audit_issue_counts'], {})

    def test_stale_pdf_hashes_and_wrong_page_mapping_rejected(self):
        for field, value in (('source_sha256', '0' * 64),
                             ('rebuilt_sha256', '0' * 64), ('source_pages', [2, 1])):
            with self.subTest(field=field):
                review = self.make_review()
                review[field] = value
                report = self.gate(review, expected=1)
                issues = self.assert_blocker(report, 'review-not-bound-to-current-inputs')
                self.assertIn(field, [item['detail'] for item in issues])

    def test_stale_or_missing_artifact_is_rejected(self):
        for field, operation in (('full_page', 'stale'), ('full_page', 'missing'),
                                  ('detail', 'stale'), ('style_plan', 'stale')):
            with self.subTest(field=field, operation=operation):
                review = self.make_review()
                if field == 'style_plan':
                    reference = review['style_plan']
                elif field == 'detail':
                    reference = review['pages'][0]['details'][0]
                else:
                    reference = review['pages'][0][field]
                path = self.directory / reference['path']
                if operation == 'missing':
                    path.unlink()
                else:
                    path.write_bytes(path.read_bytes() + b'\nchanged after review')
                report = self.gate(review, expected=1)
                self.assert_blocker(report, 'missing-or-stale-evidence')
                # Restore the style plan before the next independent case.
                write_json(self.plan_path, self.plan)

    def test_missing_page_review_is_rejected(self):
        review = self.make_review()
        review['pages'].pop()
        self.assert_blocker(self.gate(review, expected=1), 'page-review-missing', 2)

    def test_missing_detail_review_is_rejected(self):
        for value in (None, []):
            with self.subTest(details=value):
                review = self.make_review()
                if value is None:
                    del review['pages'][0]['details']
                else:
                    review['pages'][0]['details'] = value
                self.assert_blocker(self.gate(review, expected=1), 'detail-review-missing', 1)

    def test_reusing_one_full_page_evidence_path_is_rejected(self):
        review = self.make_review()
        review['pages'][1]['full_page'] = copy.deepcopy(review['pages'][0]['full_page'])
        self.assert_blocker(self.gate(review, expected=1), 'contact-sheet-reused-as-page-review', 2)

    def test_copying_full_page_evidence_to_a_new_filename_is_rejected(self):
        review = self.make_review()
        first = self.directory / review['pages'][0]['full_page']['path']
        duplicate = self.directory / 'evidence' / 'renamed-full-page.png'
        shutil.copyfile(first, duplicate)
        review['pages'][1]['full_page'] = self.reference(duplicate)
        self.assertEqual(review['pages'][0]['full_page']['sha256'],
                         review['pages'][1]['full_page']['sha256'])
        self.assert_blocker(self.gate(review, expected=1), 'contact-sheet-reused-as-page-review', 2)

    def test_full_page_cannot_substitute_for_a_detail_crop(self):
        review = self.make_review()
        review['pages'][0]['details'] = [copy.deepcopy(review['pages'][0]['full_page'])]
        self.assert_blocker(self.gate(review, expected=1), 'full-page-image-is-not-detail-evidence', 1)

    def test_renamed_full_page_cannot_substitute_for_a_detail_crop(self):
        review = self.make_review()
        first = self.directory / review['pages'][0]['full_page']['path']
        duplicate = self.directory / 'evidence' / 'renamed-detail.png'
        shutil.copyfile(first, duplicate)
        review['pages'][0]['details'] = [self.reference(duplicate)]
        self.assert_blocker(self.gate(review, expected=1), 'full-page-image-is-not-detail-evidence', 1)

    def test_catalog_tag_presence_does_not_substitute_for_new_content_review(self):
        make_pdf(self.source, tags=True)
        shutil.copyfile(self.source, self.rebuilt)
        self.plan = self.make_plan()
        write_json(self.plan_path, self.plan)
        review = self.make_review()
        review['structure']['tags'] = {
            'status': 'preserved',
            'evidence': copy.deepcopy(review['structure']['navigation']['evidence']),
        }
        report = self.gate(review, expected=1)
        issues = self.assert_blocker(report, 'structure-verification-incomplete')
        self.assertIn({'kind': 'tags', 'required': 'new-content-verified'},
                      [item['detail'] for item in issues])
        self.assertEqual(report['audit_issue_counts'], {})

    def test_claimed_completion_still_runs_audit_and_detects_hidden_text(self):
        # A truthful hash binding and otherwise complete review must not bypass
        # the fresh audit, even when a supplied old audit claims zero issues.
        review = self.make_review()
        self.gate(review)
        make_pdf(self.rebuilt, hidden=True)
        review = self.make_review()
        fake_audit = self.directory / 'old-audit.json'
        write_json(fake_audit, {'status': 'passed', 'issues': [],
                                'rebuilt_sha256': digest(self.rebuilt)})
        review.update(status='complete', completed=True, audit=self.reference(fake_audit))
        # Visible names themselves still match their independently fixed styles.
        self.assertEqual(self.style()['issues'], [])
        report = self.gate(review, expected=1)
        self.assertEqual(report['audit_issue_counts'], {'hidden-text-in-output': 2})
        issues = self.assert_blocker(report, 'structural-audit-blocker')
        self.assertEqual({item['output_page'] for item in issues}, {1, 2})
        self.assertEqual({item['detail'] for item in issues}, {'hidden-text-in-output'})

    def test_style_measurement_is_rerun_by_delivery_gate(self):
        make_pdf(self.rebuilt, size=16)
        report = self.gate(self.make_review(), expected=1)
        issues = self.assert_blocker(report, 'style-check-failed')
        self.assertEqual({item['detail']['code'] for item in issues}, {'calibrated-size-mismatch'})
        self.assertEqual({item['output_page'] for item in issues}, {1, 2})
        self.assertEqual(report['audit_issue_counts'], {})

    def test_delivery_rejects_missing_characters_in_a_reviewed_name_list(self):
        for region in self.plan['regions']:
            region['expected']['nonspace_chars'] = 10
        write_json(self.plan_path, self.plan)
        make_pdf(self.rebuilt, names=('Al', 'Bob'))
        report = self.gate(self.make_review(), expected=1)
        issues = self.assert_blocker(report, 'style-check-failed')
        self.assertEqual({item['output_page'] for item in issues}, {1, 2})
        self.assertEqual({item['detail']['code'] for item in issues},
                         {'calibrated-character-count-mismatch'})
        self.assertTrue(all(item['detail']['expected'] == 10 and item['detail']['actual'] == 7
                            for item in issues))
        self.assertEqual(report['audit_issue_counts'], {})

    def test_invalid_or_foreign_calibration_plan_blocks_delivery(self):
        for patch in ({'source_sha256': '0' * 64}, {'regions': []},
                      {'output_page_count': 3}):
            with self.subTest(patch=patch):
                plan = copy.deepcopy(self.plan)
                plan.update(patch)
                write_json(self.plan_path, plan)
                report = self.gate(self.make_review(), expected=1)
                self.assert_blocker(report, 'invalid-style-plan')
        plan = copy.deepcopy(self.plan)
        plan['regions'][0]['bbox'] = [25, 45, 301, 105]
        write_json(self.plan_path, plan)
        self.assert_blocker(self.gate(self.make_review(), expected=1), 'invalid-style-plan')

    def test_incomplete_checks_findings_and_unresolved_items_block_delivery(self):
        cases = [
            ('checks', {'content': 'pass', 'layout': 'pass', 'images': 'not-applicable'}),
            ('checks', {'content': 'not-applicable', 'layout': 'pass',
                        'images': 'not-applicable', 'math': 'not-applicable'}),
            ('notes', ''), ('status', 'rebuilt'), ('source_page', 2),
        ]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                review = self.make_review()
                review['pages'][0][field] = value
                report = self.gate(review, expected=1)
                self.assertTrue(any(item['output_page'] == 1 for item in report['blockers']))
        review = self.make_review()
        review['unresolved'] = [{'output_page': 1, 'issue': 'Name remains uncertain'}]
        self.assert_blocker(self.gate(review, expected=1), 'unresolved-or-unrecorded-items')

    def test_duplicate_page_rows_do_not_cover_a_missing_page(self):
        review = self.make_review()
        review['pages'][1] = copy.deepcopy(review['pages'][0])
        report = self.gate(review, expected=1)
        self.assert_blocker(report, 'invalid-or-duplicate-page-review')
        self.assert_blocker(report, 'page-review-missing', 2)

    def test_evidence_paths_must_stay_inside_review_directory(self):
        with tempfile.TemporaryDirectory(prefix='quality-gates-outside-') as scratch:
            outside = Path(scratch) / 'evidence.png'
            review = self.make_review()
            outside.write_bytes((self.directory / review['pages'][0]['full_page']['path']).read_bytes())
            original = outside.read_bytes()
            alias = self.directory / 'outside-evidence.png'
            alias.symlink_to(outside)
            paths = [str(outside), os.path.relpath(outside, self.directory), alias.name]
            for path in paths:
                with self.subTest(path=path):
                    review = self.make_review()
                    review['pages'][0]['full_page'] = {'path': path, 'sha256': digest(outside)}
                    self.assert_blocker(self.gate(review, expected=1), 'missing-or-stale-evidence', 1)
                    self.assertEqual(outside.read_bytes(), original)

    def test_source_selection_must_be_valid_and_one_to_one(self):
        review = self.make_review()
        for pages in ('', '1', '1,1', '0,2', '1,3', '2-1'):
            with self.subTest(pages=pages):
                self.gate(review, expected=2, pages=pages)


class InputProtectionTests(QualityGateFixture):
    def test_style_refuses_input_aliases_and_existing_reports(self):
        existing = self.directory / 'existing-style-report.json'
        existing.write_bytes(b'preserve this report\n')
        for source in (self.rebuilt, self.plan_path):
            for alias_kind in ('direct', 'symlink', 'hardlink'):
                with self.subTest(input=source.name, alias=alias_kind):
                    target = source
                    if alias_kind != 'direct':
                        target = self.directory / '{}-{}'.format(alias_kind, source.name)
                        if alias_kind == 'symlink':
                            target.symlink_to(source)
                        else:
                            os.link(source, target)
                    self.cli('pdf_style_check.py',
                             [self.rebuilt, '--plan', self.plan_path, '--report', target], 2)
        self.cli('pdf_style_check.py',
                 [self.rebuilt, '--plan', self.plan_path, '--report', existing], 2)

    def test_delivery_refuses_input_evidence_aliases_and_existing_reports(self):
        review = self.make_review()
        write_json(self.review_path, review)
        evidence = self.directory / review['pages'][0]['full_page']['path']
        existing = self.directory / 'existing-gate-report.json'
        existing.write_bytes(b'preserve this report\n')
        for source in (self.source, self.rebuilt, self.review_path, self.plan_path, evidence):
            for alias_kind in ('direct', 'symlink', 'hardlink'):
                with self.subTest(input=source.name, alias=alias_kind):
                    target = source
                    if alias_kind != 'direct':
                        target = self.directory / '{}-{}'.format(alias_kind, source.name)
                        if alias_kind == 'symlink':
                            target.symlink_to(source)
                        else:
                            os.link(source, target)
                    self.cli('pdf_delivery_gate.py', self.delivery_arguments(target), 2)
        self.cli('pdf_delivery_gate.py', self.delivery_arguments(existing), 2)


if __name__ == '__main__':
    unittest.main()
