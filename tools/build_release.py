#!/usr/bin/env python3
"""Build a deterministic, source-only skill ZIP and SHA256SUMS."""
import argparse
import hashlib
import io
from pathlib import Path
import re
import zipfile
from skill_files import ROOT, skill_files


def version():
    match = re.search(r'^  version: "(\d+\.\d+\.\d+)"$',
                      (ROOT / 'SKILL.md').read_text(encoding='utf-8'), re.MULTILINE)
    if not match:
        raise ValueError('Expected metadata.version in MAJOR.MINOR.PATCH format')
    return match.group(1)


def build(output_dir, tag=None):
    current = version()
    if tag is not None and tag != 'v' + current:
        raise ValueError(f'Tag {tag!r} does not match skill version v{current}')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for source in skill_files():
            name = 'scan-book-retypeset/' + source.relative_to(ROOT).as_posix()
            entry = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, source.read_bytes(), compresslevel=9)
    data = buffer.getvalue()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f'scan-book-retypeset-v{current}.zip'
    checksums = output_dir / 'SHA256SUMS'
    if output.exists() or checksums.exists():
        raise FileExistsError('Release outputs already exist; use a fresh output directory')
    with output.open('xb') as stream:
        stream.write(data)
    with checksums.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(hashlib.sha256(data).hexdigest() + '  ' + output.name + '\n')
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'dist')
    parser.add_argument('--tag', help='Require exact match with the skill version, e.g. v1.1.0')
    args = parser.parse_args()
    try:
        print(build(args.output_dir, args.tag))
    except (OSError, ValueError) as exc:
        parser.exit(2, f'Build failed: {exc}\n')


if __name__ == '__main__':
    main()
