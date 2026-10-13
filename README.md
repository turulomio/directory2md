# directory2md

A modern, high-performance command-line tool and Python library managed with **uv** that recursively mirrors a directory tree into Markdown (`.md`) format while strictly preserving file hierarchy.

---

## Key Features

- **Mirrored Directory Hierarchy**: Replicates the source directory tree into the target location, appending the `.directory2md.md` suffix to regular files (e.g., `document.pdf` $\rightarrow$ `document.pdf.directory2md.md`).
- **Smart Container Processing**:
  - Compressed archives (`.zip`, `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tbz2`) and emails with attachments (`.eml`, `.msg` containing attachments) are created as **directories** ending in `.directory2md` (e.g., `archive.zip.directory2md/`, `message.eml.directory2md/`).
  - Inside each container directory:
    - A primary summary markdown file is written (e.g., `archive.zip.directory2md/archive.zip.directory2md.md` containing the table of contents and metadata, or `message.eml.directory2md/message.eml.directory2md.md` containing message headers and body).
    - All extracted members or attachments are converted recursively into `.directory2md.md` files (and nested containers become subdirectories ending in `.directory2md`).
  - Emails without attachments are converted directly as single files (`message.eml.directory2md.md`).
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
    - `ia_timeout`: Boolean (`true`), present if AI processing timed out.
    - `original_path`: Absolute path to original file.
    - `filename`: Base name of original file.
    - `file_size_bytes`: Original file size.
    - `sha256_hash`: SHA-256 checksum.
    - `conversion_time`: Duration of file conversion in seconds (float).
    - `conversion_date`: ISO-8601 timestamp of conversion.
    - Container member indicators (`archive_member` or `attachment_name`).
- **AI-Powered Media Processing (Ollama & Media)**:
  - **Images**: Extracts OCR text and detailed visual descriptions using local Ollama vision models (e.g. `llava`, `llama3.2-vision`, `qwen2.5-vl`).
  - **Audio**: Transcribes spoken content using local Whisper.
  - **Video**: Samples keyframes using ffmpeg and summarizes scenes with Ollama vision models.
  - **Configuration File**: Automatically creates `directory2md.yaml` in the destination directory on first run to configure AI models, prompts, and settings.
- **Rich Document Parsing powered by `markdown-it-py` and `markdownify`**:
  - Robust parser registry covering PDF, DOCX, XLSX, ODS, ODT, ODP, PPTX, HTML / Web pages (including Monolith/SingleFile single-page archives), Images, Audio, Video, EML, Outlook MSG, ZIP, TAR, and plain text/code formats with multi-encoding support (UTF-8, Latin-1, CP1252).
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

# Optional: install audio transcription dependencies (OpenAI Whisper)
uv sync --extra audio
```

---

## Command-Line Interface (CLI)

The CLI command is `directory2md`:

```bash
uv run directory2md <source_directory> <destination_directory>
```

### Options

```text
usage: directory2md [-h] [-f [TARGET]] [-v] source destination

Recursively convert a directory to Markdown with matching structure.

positional arguments:
  source                Source directory containing documents to convert
  destination           Destination directory where markdown structure will be generated

options:
  -h, --help            Show this help message and exit
  -f, --force [TARGET]  Force re-conversion of all files, or a specific file or directory (recursively)
  -v, --verbose         Show detailed progress for each file and initial configuration
```

### Examples

```bash
# Standard conversion (quiet by default with progress bar; uses/creates directory2md.yaml)
uv run directory2md ~/Documents ~/Documents_md

# Verbose mode (shows configuration banner and per-file logs)
uv run directory2md ~/Documents ~/Documents_md -v

# Force re-conversion of all files
uv run directory2md ~/Documents ~/Documents_md --force

# Force re-conversion of a specific subfolder (recursively)
uv run directory2md ~/Documents ~/Documents_md --force reports/2026

# Force re-conversion of a specific single file
uv run directory2md ~/Documents ~/Documents_md --force invoice.pdf
```

### Configuration (`directory2md.yaml`)

On the first run, `directory2md` automatically generates a `directory2md.yaml` configuration file in the destination directory:

```yaml
# General conversion settings
days: 180                 # Age threshold in days to re-convert existing markdown files (default: 180)
force: false              # Force re-conversion of all files regardless of age
verbose: false            # Show detailed progress for each file

# AI & Ollama settings
ai:
  enabled: false          # Set to true to enable AI processing (OCR, descriptions for images, audio, video)
  language: "en"          # Language of AI results, summaries, and descriptions (e.g., "en", "es", "fr")
  ollama_url: "http://localhost:11434"
  
  # Models
  vision_model: ""        # Ollama model for image OCR/descriptions & video keyframe analysis (e.g., "llama3.2-vision:11b")
  audio_model: ""         # Whisper model size for audio/video speech transcription (e.g., "small", "base")
  
  # Custom prompts
  prompt_image_ocr: "Extract all readable text from this image verbatim. Do not add conversational filler."
  prompt_image_description: "Provide a comprehensive and detailed description of the contents and context of this image."
  prompt_video_summary: "Analyze these extracted video keyframes and summarize the scene, actions, and key visual information."
  
  # Extraction options
  max_video_frames: 3     # Maximum keyframes to sample from a video for AI analysis
  timeout_seconds: 60     # Request timeout in seconds for Ollama requests
```

---

## AI Configuration and Model Guide

`directory2md` supports local, privacy-first AI enrichment without sending any data to external cloud services. AI processing is split into two specialized engines:

1. **Vision Engine (Ollama)**: Handles optical character recognition (OCR) and scene descriptions for **images** (`.png`, `.jpg`, `.webp`, `.svg`, etc.), as well as visual keyframe analysis for **videos** (`.mp4`, `.mkv`, `.avi`, `.mov`, etc.). Note that raw images are never dumped as Base64 data URIs; instead, clean markdown text summaries and OCR extracts are generated.
2. **Audio Engine (Whisper)**: Handles speech-to-text transcription with timestamped segments for **audio files** (`.mp3`, `.wav`, `.m4a`, etc.) and the extracted audio tracks of **video files**.

---

### 1. Vision & Video Models (via Ollama)

Vision models are served locally through [Ollama](https://ollama.com). Set `vision_model` (or `video_model`) in `directory2md.yaml` to any vision-capable model pulled in your Ollama instance.

#### Recommended Vision Models & Sizing

| Model Tag | Parameters | Download / Disk Size | Recommended VRAM / RAM | Strengths & Recommendations |
| :--- | :---: | :---: | :---: | :--- |
| **`llama3.2-vision:11b`** *(Recommended)* | 11B | ~7.9 GB | ~8 GB VRAM | **Best overall balance.** Meta's flagship open multimodal model. Excellent multilingual text OCR, chart interpretation, and visual scene description. |
| **`qwen2.5-vl:7b`** | 7B | ~4.5 GB | ~6 GB VRAM | **Best for document OCR.** Alibaba's Qwen2.5-VL excels at reading dense typography, tables, scanned receipts, and multilingual documents. |
| **`llava:7b`** | 7B | ~4.7 GB | ~6 GB VRAM | **Lightweight baseline.** Standard open-source multimodal model. Fast execution on consumer laptops and entry-level GPUs. |
| **`llava:13b`** | 13B | ~8.0 GB | ~10 GB VRAM | **Higher visual fidelity.** Noticeably fewer visual hallucinations than the 7B variant; good for detailed diagram descriptions. |
| **`minicpm-v:8b`** | 8B | ~5.5 GB | ~8 GB VRAM | **Efficient OCR & multi-frame.** Strong document OCR, high image token efficiency, and fast multi-frame keyframe comparison. |
| **`llama3.2-vision:90b`** | 90B | ~55 GB | 64+ GB VRAM / Unified RAM | **Maximum quality.** For workstation or multi-GPU environments needing high-accuracy document reasoning and nuance. |

#### Setting Up Ollama

1. Install and launch Ollama:
   ```bash
   # Start Ollama service (if not running as a system daemon)
   ollama serve
   ```
2. Pull your chosen vision model:
   ```bash
   ollama pull llama3.2-vision:11b
   # or for document-heavy OCR:
   ollama pull qwen2.5-vl:7b
   ```
3. Enable in `directory2md.yaml`:
   ```yaml
   ai:
     enabled: true
     vision_model: "llama3.2-vision:11b"
   ```

---

### 2. Audio & Video Transcription Models (via Whisper)

Audio transcription is performed locally using OpenAI's Whisper engine. Set `audio_model` in `directory2md.yaml` to specify the model size according to your hardware budget.

#### Available Whisper Models & Trade-Offs

| Model Size | Parameters | Download Size | VRAM / RAM Req. | Relative Speed | Recommendations & Trade-Offs |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **`tiny`** | 39 M | ~75 MB | ~1 GB | ~32x | Ultra-fast. Suitable for CPU-only systems or quick document previews. May struggle with accents or background noise. |
| **`base`** | 74 M | ~142 MB | ~1 GB | ~16x | Good default for low-resource environments. Reliable for clean English recordings. |
| **`small`** *(Recommended)* | 244 M | ~466 MB | ~2 GB | ~6x | **Best balance of speed and accuracy.** Recommended for general desktop/laptop use. Strong multilingual transcription. |
| **`medium`** | 769 M | ~1.5 GB | ~5 GB | ~2x | High accuracy for technical vocabulary, diverse accents, and non-English recordings. |
| **`turbo`** | 809 M | ~1.6 GB | ~6 GB | ~8x | **Fast high-accuracy.** Pruned version of Large-v3 providing near large-model accuracy at 8x real-time speed. |
| **`large-v3`** | 1550 M | ~3.0 GB | ~10 GB | 1x | **State of the art.** Highest transcription accuracy across 100+ languages, resistant to background noise and music. |

#### Setting Up Whisper

1. Install the audio transcription extra dependencies:
   ```bash
   uv sync --extra audio
   ```
   *(Alternatively, `directory2md` also supports system-installed `whisper` CLI or `whisper.cpp` binaries if present in your `PATH`).*
2. Configure your desired model size in `directory2md.yaml`:
   ```yaml
   ai:
     enabled: true
     audio_model: "small"   # or "turbo", "medium", "base"
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
# -> /data/documents_md/report.pdf.directory2md.md

zip_dir = get_md_path(src_dir / "archive.zip", src_dir, dst_dir)
# -> /data/documents_md/archive.zip.directory2md (directory)

zip_primary = get_md_path(src_dir / "archive.zip", src_dir, dst_dir, primary_file=True)
# -> /data/documents_md/archive.zip.directory2md/archive.zip.directory2md.md

# 3. Map destination Markdown file -> original file path
orig_pdf = get_original_path(dst_dir / "report.pdf.directory2md.md", src_dir, dst_dir)
# -> /data/documents/report.pdf

orig_zip_member = get_original_path(dst_dir / "archive.zip.directory2md" / "nested" / "notes.txt.directory2md.md", src_dir, dst_dir)
# -> /data/documents/archive.zip

# 4. Resolve full mapping details
details = resolve_mapping_details(dst_dir / "archive.zip.directory2md" / "nested" / "notes.txt.directory2md.md", src_dir, dst_dir)
print(details.is_container_member)        # True
print(details.container_original_path)   # Path("/data/documents/archive.zip")
print(details.member_subpath)            # "nested/notes.txt.directory2md.md"
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
| **Images** (`.png`, `.jpg`, `.webp`, `.svg`, etc.) | `ImageParser` | Dimensions and metadata; OCR text and visual scene description if AI enabled (no Base64 embedding). |
| **Audio** (`.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg`) | `MediaParser` | Audio metadata, duration, channels; speech transcription with timestamps if AI enabled. |
| **Video** (`.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`) | `MediaParser` | Video metadata, resolution, duration; scene keyframe descriptions and transcribed speech if AI enabled. |
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
ia: false
conversion_time: 0.042
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
ia: false
conversion_time: 0.015
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
