#!/usr/bin/env python3
"""Install the complete skill into a new directory; refuse any existing target."""
import argparse
import os
from pathlib import Path
import shutil
from skill_files import ROOT, skill_files


def install(destination):
    target = Path(destination).expanduser() / 'scan-book-retypeset'
    paths = skill_files()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir()  # Atomic refusal if any file/directory already occupies the name.
    try:
        for path in paths:
            output = target / path.relative_to(ROOT)
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, output)
    except Exception:
        shutil.rmtree(target)
        raise
    return target.resolve()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    codex_dir = Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex')
    parser.add_argument('--destination', type=Path, default=codex_dir / 'skills',
                        help='Parent skills directory; existing skill is never replaced')
    args = parser.parse_args()
    try:
        print(install(args.destination))
    except (OSError, ValueError) as exc:
        parser.exit(2, f'Installation failed: {exc}\n')


if __name__ == '__main__':
    main()
