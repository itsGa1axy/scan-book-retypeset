"""Allowlisted, source-only contents of the portable skill distribution."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = ('agents', 'assets', 'references', 'scripts')
SUFFIXES = {'.md', '.py', '.yaml', '.json', '.tex'}


def skill_files(root=ROOT):
    paths = [root / 'SKILL.md', root / 'LICENSE']
    for name in DIRECTORIES:
        paths.extend(p for p in (root / name).rglob('*')
                     if p.is_file() and p.suffix in SUFFIXES)
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise ValueError(f'Invalid distribution resource: {path.name}')
        path.resolve().relative_to(root.resolve())
    return sorted(paths, key=lambda p: p.relative_to(root).as_posix())
