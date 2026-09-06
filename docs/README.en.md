# Scan Book Retypeset

An [Agent Skills](https://agentskills.io/specification) workflow for reconstructing scanned or photographed books using **visible font text**, preserving pagination, illustrations, irregular layouts, and PDF hierarchy. Math is retypeset from editable formula source such as LaTeX.

[中文](../README.md) · [Skill](../SKILL.md) · [Releases](https://github.com/itsGa1axy/scan-book-retypeset/releases)

## Install

Download the versioned ZIP from Releases and copy the complete `scan-book-retypeset` folder into your agent's skill directory. From a clone, `python3 tools/install_skill.py` installs into `$CODEX_HOME/skills` or `~/.codex/skills`; `--destination` selects another skill parent directory. Existing destinations are never overwritten. Restart discovery or use a new conversation, then invoke `$scan-book-retypeset`.

The core instructions and detailed references are primarily in Chinese. `agents/openai.yaml` is an optional host extension.

## Scope

The workflow requires region-level transcription, layout reconstruction, protected image regions, formula verification and page-by-page review. Its 17 core constraints prohibit invisible OCR overlays being passed off as reconstruction, guessed names or symbols, silent raster fallbacks, flattened bookmarks, and unreported structure loss.

PDF structure includes heading semantics, bookmark ancestry and destinations, page labels, links, Tagged PDF references and optional-content groups. These are checked separately; a `StructTreeRoot` entry does not prove valid tagging.

## Tools

Use Python 3.9+ and `python -m pip install -r requirements.txt` in a virtual environment. Run each script with `--help`:

- `scripts/pdf_probe.py`: inspect selected physical pages and document structure; optionally render previews.
- `scripts/pdf_compare.py`: create a side-by-side PDF from a one-to-one page mapping.
- `scripts/pdf_audit.py`: report limited text/font/geometry/navigation differences as JSON.

The helpers do not perform OCR or automatic book reconstruction. Audit exit code 0 still requires content, visual and navigation review; 1 reports differences; 2 indicates an invocation/runtime failure. See the Chinese README for complete commands.

## Develop

```bash
python -m pip install -r requirements-dev.txt
python tools/validate_skill.py
python -m unittest discover -s tests -v
python tools/build_release.py
```

Tests generate their own PDFs using an embedded font provided by the dependency. No books or system fonts are required. Complex mathematical semantics and complete tagged-content migration are not covered by the limited CLI tests.

Author and contributor: [itsGa1axy](https://github.com/itsGa1axy). Original project code and documentation: [MIT](../LICENSE). External dependencies retain their own licenses.
