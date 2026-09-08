# Scan Book Retypeset

An [Agent Skills](https://agentskills.io/specification) workflow for reconstructing scanned or photographed books using **visible font text**, preserving pagination, illustrations, irregular layouts, and PDF hierarchy. Math is retypeset from editable formula source such as LaTeX.

[中文](../README.md) · [Skill](../SKILL.md) · [Releases](https://github.com/itsGa1axy/scan-book-retypeset/releases)

## Install

Download the versioned ZIP from Releases and copy the complete `scan-book-retypeset` folder into your agent's skill directory. From a clone, `python3 tools/install_skill.py` installs into `$CODEX_HOME/skills` or `~/.codex/skills`; `--destination` selects another skill parent directory. Existing destinations are never overwritten. Restart discovery or use a new conversation, then invoke `$scan-book-retypeset`.

The core instructions and detailed references are primarily in Chinese. `agents/openai.yaml` is an optional host extension.

## v1.1 quality gates

Calibrate semantic style roles against source images or an approved sample before processing the full book. OCR font names, bounding boxes and reported sizes are not a typesetting specification. New tools detect region-level font/size/color mismatches and validate current-file review evidence. A prose exception does not turn failed checks or old OCR tagging into a completed reconstruction.

## Scope

The workflow requires region-level transcription, layout reconstruction, protected image regions, formula verification and page-by-page review. Its 17 core constraints prohibit invisible OCR overlays being passed off as reconstruction, guessed names or symbols, silent raster fallbacks, flattened bookmarks, and unreported structure loss.

PDF structure includes heading semantics, bookmark ancestry and destinations, page labels, links, Tagged PDF references and optional-content groups. These are checked separately; a `StructTreeRoot` entry does not prove valid tagging.

## Tools

Use Python 3.9+ and `python -m pip install -r requirements.txt` in a virtual environment. Run each script with `--help`:

- `scripts/pdf_probe.py`: inspect selected physical pages and document structure; optionally render previews.
- `scripts/pdf_compare.py`: create a side-by-side PDF from a one-to-one page mapping.
- `scripts/pdf_audit.py`: report limited text/font/geometry/navigation differences as JSON.
- `scripts/pdf_style_check.py`: check explicitly calibrated regions for font, size, color and optional visible character count.
- `scripts/pdf_delivery_gate.py`: rerun audit/style checks and require current artifact hashes, per-page review evidence and explicit structure verification.

The helpers do not perform OCR or automatic book reconstruction. Audit exit code 0 still requires content, visual and navigation review; 1 reports differences; 2 indicates an invocation/runtime failure. The delivery gate also refuses legacy narrative review reports, missing page/detail records and unverified tag migration. Its success means limited checks and declared evidence are consistent, not that semantic review was truthful. See the Chinese README for complete commands and the review-v2 format.

## Develop

```bash
python -m pip install -r requirements-dev.txt
python tools/validate_skill.py
python -m unittest discover -s tests -v
python tools/build_release.py
```

Tests generate their own PDFs using an embedded font provided by the dependency. No books or system fonts are required. Complex mathematical semantics and complete tagged-content migration are not covered by the limited CLI tests.

Author and contributor: [itsGa1axy](https://github.com/itsGa1axy). Original project code and documentation: [MIT](../LICENSE). External dependencies retain their own licenses.

## v1.2: mixed math before batch expansion

Do not retain entire lines simply because they contain Latin variables. Pilot actual mixed CJK/math, display formulas, independent chapter titles and tables before expanding those classes. A synthetic TeX template and `pdf_place_block.py` provide a concrete route to native-size vector/text overlays, with overflow and protected-region rejection. The helper does not erase scans or transfer book navigation/tags. The audit now checks visible font-metric boxes beyond page edges; style plans optionally check `expected.content_bbox`. See [workflow](../references/pilot-and-mixed-math.md).
