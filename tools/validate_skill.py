#!/usr/bin/env python3
"""Check project skill metadata and local resources; not an official certification."""
from pathlib import Path
import json
import re
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]


def validate(root=ROOT):
    raw = (root / 'SKILL.md').read_text(encoding='utf-8')
    if not raw.startswith('---\n'):
        raise ValueError('Missing YAML frontmatter')
    front, body = raw[4:].split('\n---\n', 1)
    data = yaml.safe_load(front)
    name = data.get('name', '')
    if not isinstance(name, str) or len(name) > 64 or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', name):
        raise ValueError('Invalid skill name')
    if name != root.name:
        raise ValueError('Skill name must match directory name')
    description = data.get('description')
    if not isinstance(description, str) or not description.strip() or len(description) > 1024:
        raise ValueError('Description must contain 1..1024 characters')
    allowed = {'name', 'description', 'license', 'compatibility', 'metadata', 'allowed-tools'}
    if set(data) - allowed:
        raise ValueError('Unsupported top-level frontmatter fields')
    metadata = data.get('metadata', {})
    if not isinstance(metadata, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in metadata.items()):
        raise ValueError('metadata must have string keys and values')
    if not re.fullmatch(r'\d+\.\d+\.\d+', metadata.get('version', '')):
        raise ValueError('Invalid project version')
    if data.get('license') != 'MIT' or not (root / 'LICENSE').is_file():
        raise ValueError('MIT license declaration and file must agree')
    count = 0
    for document in [root / 'SKILL.md', *(root / 'references').glob('*.md')]:
        for target in re.findall(r'\]\(([^)]+)\)', document.read_text(encoding='utf-8')):
            if '://' in target or target.startswith('#'):
                continue
            path = (document.parent / target.split('#')[0]).resolve()
            path.relative_to(root.resolve())
            if not path.is_file():
                raise ValueError(f'Missing resource: {target}')
            count += 1
    json.loads((root / 'assets/job-template.json').read_text(encoding='utf-8'))
    if not body.strip():
        raise ValueError('Empty skill instructions')
    return {'name': name, 'version': metadata['version'], 'local_references': count}


if __name__ == '__main__':
    try:
        print(json.dumps(validate(), ensure_ascii=False))
    except (ValueError, OSError, yaml.YAMLError) as exc:
        print(f'Validation failed: {exc}', file=sys.stderr)
        sys.exit(1)
