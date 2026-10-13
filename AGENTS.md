# AGENTS.md - Architecture, Guidelines, and Lessons Learned

This document outlines the architecture, conventions, workflows, and lessons learned during the development of **`directory2md`**. It serves as an authoritative guide for AI coding agents and human developers working in this repository.

---

## 1. Project Overview

`directory2md` is a Python CLI tool and library managed with **uv** that recursively mirrors a source directory tree into a target destination, converting all document contents to **Markdown** (`.md`) format.

### Key Transformation Rules
1. **Regular Files**:
   - The `.md` suffix is appended to the original filename: `report.pdf` $\rightarrow$ `report.pdf.md`.
2. **Container Files** (`.zip`, `.tar.gz`, `.tar`, `.tgz`, `.tbz2`, and `.eml`/`.msg` containing attachments):
   - A destination **directory** matching the container name is created instead of a single `.md` file (e.g. `archive.zip/`, `message.eml/`).
   - Inside the container directory:
     - The container's primary Markdown summary is created: `<container_name>.md` (e.g. `archive.zip.md` containing the table of contents and stats, or `message.eml.md` with message headers and body).
     - All contained members or attachments are extracted and converted recursively to `.md` (nested containers create subdirectories).
3. **Emails Without Attachments**:
   - Plain `.eml` or `.msg` files with no attachments are treated as regular files and converted directly to `<name>.eml.md` without creating a container directory.
4. **YAML Frontmatter Headers**:
   - Every generated `.md` file includes frontmatter containing:
     - `ia`: Boolean (`true`/`false`) flag indicating whether the output was generated with AI.
     - `original_path`: Absolute path to original file.
     - `filename`: Base filename.
     - `file_size_bytes`: Original file size in bytes.
     - `sha256_hash`: SHA-256 checksum.
     - `conversion_date`: ISO-8601 conversion timestamp.
     - For extracted container members: `archive_member` or `attachment_name`.
5. **Incremental Update Policy** (Default 180 Days):
   - A destination file is only re-converted if:
     a) Destination does not exist.
     b) Destination file age exceeds `max_age_days` (default: 180 days).
     c) Source file modification timestamp (`src.mtime`) is newer than destination timestamp (`dst.mtime`).
     d) The `--force` flag is specified (optionally targeting a specific file or directory recursively).

---

## 2. Codebase Architecture

The project adheres to the standard **`src` layout** for full compatibility with `uv_build`:

```text
directory2md/
├── src/
│   └── directory2md/
│       ├── __init__.py           # Public API and exports
│       ├── ai_client.py          # Ollama REST API client, keyframe extraction & Whisper
│       ├── cli.py                # Command-line interface with interactive progress bar
│       ├── config.py             # Config & AIConfig models and YAML configuration loader
│       ├── converter.py          # DirectoryConverter engine and convert_directory
│       ├── mapper.py             # Bidirectional get_original_path and get_md_path
│       ├── markdown_utils.py     # markdown-it-py and PyYAML frontmatter helpers
│       ├── models.py             # DocumentMetadata and EmailHeaders dataclasses
│       ├── extractors/
│       │   └── filename_parser.py # Date, time, and title extractor from filenames
│       └── parsers/              # Specialized format parsers
│           ├── __init__.py       # PARSER_MAP registry and container detection
│           ├── base.py           # BaseParser abstract interface & calculate_sha256
│           ├── archive_parser.py # ZIP, TAR, TGZ
│           ├── docx_parser.py    # DOCX (python-docx)
│           ├── email_parser.py   # EML (email) and MSG (extract-msg)
│           ├── image_parser.py   # PNG, JPG, WEBP, SVG (Base64 Data URI + Ollama OCR/description)
│           ├── media_parser.py   # Audio (MP3/WAV/etc.) & Video (MP4/MKV/etc.) with AI summaries
│           ├── opendocument_parser.py # ODT, ODP
│           ├── pdf_parser.py     # PDF (pypdf)
│           ├── pptx_parser.py    # PPTX, PPT (olefile)
│           ├── spreadsheet_parser.py  # CSV, TSV, XLSX, ODS
│           └── text_parser.py    # TXT, MD, LOG, JSON (markdown-it-py)
├── tests/                        # Automated pytest test suites
├── pyproject.toml                # UV package configuration
└── README.md                     # User documentation
```

---

## 3. Bidirectional Mapping Utilities (`mapper.py`)

- **`get_md_path(original_path, src_dir=None, dst_dir=None, primary_file=False) -> Path`**:
  Calculates the destination path. If the target is a container, returns the container directory (or primary summary `.md` if `primary_file=True`).
- **`get_original_path(md_path, src_dir=None, dst_dir=None) -> Path`**:
  Resolves the original source file.
  - If the `.md` file exists on disk and contains `original_path` in YAML frontmatter, reads it directly.
  - For abstract paths, detects whether the file is nested inside a container folder (`.zip`, `.tar.gz`, etc.) or simply strips `.md`.
- **`resolve_mapping_details(md_path, src_dir, dst_dir) -> PathMapping`**:
  Returns structured information indicating whether the target is an internal container member, providing the container source path and inner subpath.

---

## 4. `markdown-it-py` Integration

The `markdown-it-py` library is required across the project:
- In `TextParser` to parse token trees and extract titles from `h1`/`h2` headings.
- In `markdown_utils.validate_markdown` to verify that generated text parses cleanly.
- In `markdown_utils.extract_title_from_markdown` to detect headings as a fallback when filenames lack descriptive titles.

---

## 5. Development Workflows with `uv`

- **Run CLI**:
  ```bash
  uv run directory2md <source_dir> <destination_dir>
  uv run directory2md <source_dir> <destination_dir> -v
  uv run directory2md <source_dir> <destination_dir> --force
  ```
- **Run Tests**:
  ```bash
  uv run pytest
  ```
- **Build Distribution Wheel**:
  ```bash
  uv build
  ```
- **Add Dependencies**:
  ```bash
  uv add <package>
  uv add --dev <package>
  ```
- **Code Conventions**:
  - Python 3.14+ with full type annotations (`from __future__ import annotations`).
  - Dataclasses for models (`DocumentMetadata`, `EmailHeaders`).
  - Safe fallbacks for optional binary formats so missing parser dependencies do not halt execution.
