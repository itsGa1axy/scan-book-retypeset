"""Real PDF regressions for placement, clipping and source-calibrated line bounds."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import pymupdf as fitz

ROOT = Path(__file__).resolve().parents[1]


class CompositionTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.folder = Path(self.scratch.name)
        self.block = self.folder / 'block.pdf'
        self.make_block()

    def make_block(self, hidden=False, raster=False, overflow=False, rotate=False):
        with fitz.open() as d:
            p = d.new_page(width=110, height=40)
            p.insert_font(fontname='f', fontbuffer=fitz.Font('tiro').buffer)
            p.insert_text((95 if overflow else 5, 25), 'X = 12', fontname='f', fontsize=12,
                          render_mode=3 if hidden else 0)
            if raster:
                pix = p.get_pixmap()
                p.insert_image(p.rect, pixmap=pix)
            if rotate:
                p.set_rotation(90)
            d.save(self.block)

    def cli(self, script, *args, code=0):
        before = hashlib.sha256(self.block.read_bytes()).hexdigest()
        result = subprocess.run([sys.executable, str(ROOT/'scripts'/script), *map(str, args)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, code, result.stdout+result.stderr)
        self.assertEqual(before, hashlib.sha256(self.block.read_bytes()).hexdigest())
        return result

    def place(self, *extra, code=0, box=(30, 50, 190, 110)):
        output = self.folder/'overlay.pdf'
        self.cli('pdf_place_block.py', self.block, '--canvas', 220, 180,
                 '--box', *box, '--output', output, *extra, code=code)
        if code:
            self.assertFalse(output.exists())
        return output

    def test_native_size_unicode_and_font_preserved(self):
        output = self.place('--align', 'center')
        with fitz.open(self.block) as source, fitz.open(output) as d:
            a, b = source[0].get_texttrace()[0], d[0].get_texttrace()[0]
            self.assertEqual(d[0].get_text().strip(), 'X = 12')
            self.assertAlmostEqual(a['size'], b['size'], places=4)
            self.assertAlmostEqual(b['chars'][0][2][0]-a['chars'][0][2][0], 55, places=3)
            self.assertAlmostEqual(b['chars'][0][2][1]-a['chars'][0][2][1], 50, places=3)
            self.assertFalse(d[0].get_images())
            self.assertTrue(all(d.extract_font(f[0])[3] for f in d[0].get_fonts()))

    def test_too_wide_rejected_without_auto_shrink(self):
        self.place(code=2, box=(30, 50, 120, 110))

    def test_too_tall_rejected(self):
        self.place(code=2, box=(30, 50, 190, 70))

    def test_protected_region_rejected(self):
        self.place('--protect', 50, 60, 80, 80, code=2)

    def test_disjoint_protected_region_allowed(self):
        self.place('--protect', 160, 120, 180, 160)

    def test_hidden_or_raster_or_rotated_block_rejected(self):
        for option in ('hidden', 'raster', 'rotate', 'overflow'):
            with self.subTest(option=option):
                self.block.unlink()
                self.make_block(**{option: True})
                self.place(code=2)

    def test_existing_output_not_replaced(self):
        output = self.place()
        before = output.read_bytes()
        self.cli('pdf_place_block.py', self.block, '--canvas', 220, 180,
                 '--box', 30, 50, 190, 110, '--output', output, code=2)
        self.assertEqual(before, output.read_bytes())

    def test_nan_geometry_rejected(self):
        self.place(code=2, box=(30, 50, float('nan'), 110))

    def test_audit_finds_text_clipped_at_page_edge(self):
        self.block.unlink()
        self.make_block(overflow=True)
        report = self.folder/'audit.json'
        self.cli('pdf_audit.py', self.block, self.block, '--source-pages', 1,
                 '--report', report, code=1)
        codes = [r['code'] for r in json.loads(report.read_text())['issues']]
        self.assertIn('visible-text-outside-page', codes)

    def test_audit_handles_rotation(self):
        self.block.unlink()
        self.make_block(rotate=True)
        self.cli('pdf_audit.py', self.block, self.block, '--source-pages', 1,
                 '--report', self.folder/'audit.json')

    def test_bounds_catches_tail_outside_column_with_correct_style(self):
        plan = {'schema':'scan-book-retypeset/style-plan-v1',
                'source_sha256':hashlib.sha256(self.block.read_bytes()).hexdigest(),
                'output_page_count':1,
                'regions':[{'id':'line', 'output_page':1, 'role':'body',
                            'basis':'Independent synthetic column width', 'bbox':[0,0,110,40],
                            'expected':{'fonts':['NimbusRoman-Regular'], 'size_pt':[11.9,12.1],
                                        'color_rgb':[0,0,0], 'content_bbox':[0,0,23,40]}}]}
        plan_path = self.folder/'plan.json'
        plan_path.write_text(json.dumps(plan))
        report = self.folder/'style.json'
        self.cli('pdf_style_check.py', self.block, '--plan', plan_path, '--report', report, code=1)
        codes = [r['code'] for r in json.loads(report.read_text())['issues']]
        self.assertEqual(codes, ['calibrated-bounds-mismatch'])

if __name__ == '__main__':
    unittest.main()
