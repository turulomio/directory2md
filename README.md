# directory2md

A modern, high-performance command-line tool and Python library managed with **uv** that recursively mirrors a directory tree into Markdown (`.md`) format while strictly preserving file hierarchy.

---

## Key Features

- **Mirrored Directory Hierarchy**: Replicates the source directory tree into the target location, appending the `.md` suffix to regular files (e.g., `document.pdf` $\rightarrow$ `document.pdf.md`).
- **Smart Container Processing**:
  - Compressed archives (`.zip`, `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tbz2`) and emails with attachments (`.eml`, `.msg` containing attachments) are created as **directories** rather than single flat files (e.g., `archive.zip/`, `message.eml/`).
  - Inside each container directory:
    - A primary summary markdown file is written (e.g., `archive.zip/archive.zip.md` containing the table of contents and metadata, or `message.eml/message.eml.md` containing message headers and body).
    - All extracted members or attachments are converted recursively into `.md` files (and nested containers become subdirectories).
  - Emails without attachments are converted directly as single files (`message.eml.md`).
- **Intelligent Incremental Updates**:
  - By default, files are only converted if:
    1. The destination file does not exist.
    2. The destination file was converted more than **180 days** ago (configurable via `-d / --days`).
    3. The source file was modified more recently than the existing destination file (`src.mtime > dst.mtime`).
    4. The `--force` flag is specified.
- **Bidirectional Path Mapping**:
  - Determine destination Markdown path from any original file: `get_md_path()`.
  - Resolve original source path from any converted Markdown file (including archive members and email attachments): `get_original_path()`.
  - Retrieve detailed structural mapping information: `resolve_mapping_details()`.
- **YAML Frontmatter Metadata**:
  - Every generated `.md` file begins with clean YAML frontmatter containing:
    - `ia`: Boolean (`true` or `false`) indicating whether the document was processed/generated with AI.
    - `original_path`: Absolute path to original file.
    - `filename`: Base name of original file.
    - `file_size_bytes`: Original file size.
    - `sha256_hash`: SHA-256 checksum.
    - `conversion_date`: ISO-8601 timestamp of conversion.
    - Container member indicators (`archive_member` or `attachment_name`).
- **AI-Powered Media Processing (Ollama & Media)**:
  - **Images**: Extracts OCR text and detailed visual descriptions using local Ollama vision models (e.g. `llava`, `llama3.2-vision`, `qwen2.5-vl`).
  - **Audio**: Transcribes spoken content using local Whisper.
  - **Video**: Samples keyframes using ffmpeg and summarizes scenes with Ollama vision models.
  - **Configuration File**: Automatically creates `directory2md.yaml` in the destination directory on first run to configure AI models, prompts, and settings.
- **Rich Document Parsing powered by `markdown-it-py`**:
  - Robust parser registry covering PDF, DOCX, XLSX, ODS, ODT, ODP, PPTX, Images (embedded as base64 Data URIs), Audio, Video, EML, Outlook MSG, ZIP, TAR, and plain text/code formats with multi-encoding support (UTF-8, Latin-1, CP1252).
  - Validates and sanitizes Markdown output using `markdown-it-py`.

---

## Requirements and Installation

This project is built for **Python 3.14+** using [`uv`](https://docs.astral.sh/uv/):

```bash
# Clone the repository
git clone https://github.com/turulomio/directory2md.git
cd directory2md

# Install dependencies and sync virtual environment with uv
uv sync
```

---

## Command-Line Interface (CLI)

The CLI command is `directory2md`:

```bash
uv run directory2md <source_directory> <destination_directory>
```

### Options

```text
usage: directory2md [-h] [-d DAYS] [-f [TARGET]] [-v] [-q] [--no-progress] source destination

Recursively convert a directory to Markdown with matching structure.

positional arguments:
  source                Source directory containing documents to convert
  destination           Destination directory where markdown structure will be generated

options:
  -h, --help            Show this help message and exit
  -d, --days DAYS       Age threshold in days to re-convert existing markdown files (default: 180)
  -f, --force [TARGET]  Force re-conversion of all files, or a specific file or directory (recursively)
  -v, --verbose         Show detailed progress for each file
  -q, --quiet           Suppress informational output and show only errors
  --no-progress         Disable interactive progress bar
```

### Examples

```bash
# Standard conversion (uses/creates directory2md.yaml in destination)
uv run directory2md ~/Documents ~/Documents_md

# Verbose mode with a custom 30-day age threshold
uv run directory2md ~/Documents ~/Documents_md --days 30 -v

# Force re-conversion of all files
uv run directory2md ~/Documents ~/Documents_md --force

# Force re-conversion of a specific subfolder (recursively)
uv run directory2md ~/Documents ~/Documents_md --force reports/2026

# Force re-conversion of a specific single file
uv run directory2md ~/Documents ~/Documents_md --force invoice.pdf
```

---

## Python API Usage

The library exposes the main converter and bidirectional mapping helpers directly from `directory2md`:

```python
from pathlib import Path
from directory2md import (
    convert_directory,
    get_md_path,
    get_original_path,
    resolve_mapping_details,
)

src_dir = Path("/data/documents")
dst_dir = Path("/data/documents_md")

# 1. Run conversion programmatically
stats = convert_directory(
    src_dir=src_dir,
    dst_dir=dst_dir,
    max_age_days=180,
    force=False,
    verbose=True,
)
print(f"Scanned: {stats.total_scanned}, Converted: {stats.converted}, Skipped: {stats.skipped}")

# 2. Map original file path -> Markdown path in destination
pdf_md = get_md_path(src_dir / "report.pdf", src_dir, dst_dir)
# -> /data/documents_md/report.pdf.md

zip_dir = get_md_path(src_dir / "archive.zip", src_dir, dst_dir)
# -> /data/documents_md/archive.zip (directory)

zip_primary = get_md_path(src_dir / "archive.zip", src_dir, dst_dir, primary_file=True)
# -> /data/documents_md/archive.zip/archive.zip.md

# 3. Map destination Markdown file -> original file path
orig_pdf = get_original_path(dst_dir / "report.pdf.md", src_dir, dst_dir)
# -> /data/documents/report.pdf

orig_zip_member = get_original_path(dst_dir / "archive.zip" / "nested" / "notes.txt.md", src_dir, dst_dir)
# -> /data/documents/archive.zip

# 4. Resolve full mapping details
details = resolve_mapping_details(dst_dir / "archive.zip" / "nested" / "notes.txt.md", src_dir, dst_dir)
print(details.is_container_member)        # True
print(details.container_original_path)   # Path("/data/documents/archive.zip")
print(details.member_subpath)            # "nested/notes.txt.md"
```

---

## Supported Formats

| Format / Extensions | Parser Class | Output Representation |
| :--- | :--- | :--- |
| **PDF** (`.pdf`) | `PDFParser` | Extracted text per page with markdown headings (`pypdf`). |
| **Word** (`.docx`) | `DocxParser` | Headings, styled paragraphs, and markdown tables (`python-docx`). |
| **Spreadsheets** (`.csv`, `.tsv`, `.xlsx`, `.ods`) | `SpreadsheetParser` | Markdown tables and formatted cell data. |
| **OpenDocument** (`.odt`, `.odp`) | `OpenDocumentParser` | Structured text, sections, and slide notes. |
| **PowerPoint** (`.pptx`, `.potx`, `.ppt`, etc.) | `PPTXParser` | Slide titles, text shapes, notes, and tables. |
| **Images** (`.png`, `.jpg`, `.webp`, `.svg`, etc.) | `ImageParser` | Embedded base64 Data URI with image dimensions and format info. |
| **Archives** (`.zip`, `.tar`, `.tar.gz`, `.tgz`, `.tbz2`) | `ArchiveParser` | Directory created with table of contents markdown and recursive child files. |
| **Emails** (`.eml`, `.msg`) | `EmailParser` | Headers, decoded HTML/text body. If attachments present, creates container folder. |
| **Text & Code** (`.txt`, `.md`, `.json`, `.log`, etc.) | `TextParser` | Multi-encoding text decoding with `markdown-it-py` token analysis. |

---

## Frontmatter Metadata Format

Every generated markdown document begins with a YAML frontmatter block:

```yaml
---
filepath: /data/documents/financial_report.pdf
relative_path: financial_report.pdf
filename: financial_report.pdf
extension: .pdf
title: Financial Report
file_size_bytes: 489210
sha256_hash: a1b2c3d4e5f6...
word_count: 1420
origin_type: file
conversion_date: '2026-10-13T07:15:00'
original_path: /data/documents/financial_report.pdf
---

# Document Title

Document text content...
```

For extracted archive members or email attachments, specific origin details are added:

```yaml
---
original_path: /data/documents/bundle.zip
archive_member: subfolder/data.csv
filename: data.csv
file_size_bytes: 1042
sha256_hash: f0e1d2c3...
conversion_date: '2026-10-13T07:15:00'
---
```

---

## Development and Testing

Run test suite with `pytest`:

```bash
uv run pytest
```

Build binary wheel and source distribution:

```bash
uv build
```

---

## License

This project is licensed under the terms of the GNU General Public License v3 (GPLv3). See [LICENSE](LICENSE) for details.
