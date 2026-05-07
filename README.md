# PLF Python — Core parser library

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Status: Pre-alpha](https://img.shields.io/badge/status-pre--alpha-red.svg)]()

Python library for reading, writing, validating, and querying PLF (PromptLine Format) files.

## Installation

```bash
pip install plf  # (not yet published)
```

## Quick start

```python
from plf import PLFParser, PLFQuery

plf = PLFParser.parse("mi_video.edit.plf")

shots = plf.get_entries(track="SH")
active = plf.get_entries_at(seconds=60.0)
scene = plf.get_scene_at(seconds=200.0)
carlos_actions = plf.get_entries(track="ACT", subj="A1")

writer = PLFWriter(plf)
writer.write("output.plf")
```

## Modules

- `plf.parser` — Parse `.plf` text → Python dataclasses
- `plf.writer` — Python dataclasses → valid `.plf` text
- `plf.validator` — Format validation (vocabulary, cross-references, structure)
- `plf.schema` — All dataclasses
- `plf.query` — Filter entries by type, range, subject, tag

## Format spec

See [PLF Format Specification](https://github.com/tu-org/plf-spec).
