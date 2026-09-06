"""Installation and reproducible distribution behavior, without touching user skills."""
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from build_release import build
from install_skill import install
from skill_files import skill_files
from validate_skill import validate


class DistributionTests(unittest.TestCase):
    def test_valid_metadata_and_resources(self):
        self.assertEqual(validate()['name'], 'scan-book-retypeset')

    def test_install_complete_and_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as scratch:
            target = install(scratch)
            for source in skill_files():
                self.assertEqual(source.read_bytes(), (target / source.relative_to(ROOT)).read_bytes())
            marker = target / 'local-edit.txt'
            marker.write_text('keep me', encoding='utf-8')
            with self.assertRaises(FileExistsError):
                install(scratch)
            self.assertEqual(marker.read_text(encoding='utf-8'), 'keep me')

    def test_install_cli_custom_destination(self):
        with tempfile.TemporaryDirectory() as scratch:
            cmd = [sys.executable, str(ROOT / 'tools/install_skill.py'), '--destination', scratch]
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 2)

    def test_zip_determinism_contents_and_checksum(self):
        with tempfile.TemporaryDirectory() as scratch:
            a = build(Path(scratch) / 'a')
            b = build(Path(scratch) / 'b')
            self.assertEqual(a.read_bytes(), b.read_bytes())
            expected = {'scan-book-retypeset/' + p.relative_to(ROOT).as_posix() for p in skill_files()}
            with zipfile.ZipFile(a) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(set(archive.namelist()), expected)
                for path in skill_files():
                    self.assertEqual(archive.read('scan-book-retypeset/' + path.relative_to(ROOT).as_posix()), path.read_bytes())
            checksums = (a.parent / 'SHA256SUMS').read_text(encoding='utf-8')
            self.assertEqual(checksums, hashlib.sha256(a.read_bytes()).hexdigest() + '  ' + a.name + '\n')
            with self.assertRaises(FileExistsError):
                build(a.parent)

    def test_mismatched_tag_does_not_publish(self):
        with tempfile.TemporaryDirectory() as scratch:
            with self.assertRaises(ValueError):
                build(Path(scratch) / 'out', tag='v0.0.0')
            self.assertFalse((Path(scratch) / 'out').exists())

    def test_tool_help(self):
        for name in ('install_skill.py', 'build_release.py'):
            with self.subTest(tool=name):
                result = subprocess.run([sys.executable, str(ROOT / 'tools' / name), '--help'], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0)
                self.assertIn('usage:', result.stdout)


if __name__ == '__main__':
    unittest.main()
