"""Audio and video media document parsers."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Optional, Tuple

from directory2md.ai_client import (
    extract_video_keyframes,
    query_ollama_multiple_images,
    transcribe_audio_whisper,
)
from directory2md.config import Config
from directory2md.models import DocumentMetadata
from directory2md.parsers.base import BaseParser

AUDIO_MIME_TYPES = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".aac": "audio/aac",
    ".wma": "audio/x-ms-wma",
}

VIDEO_MIME_TYPES = {
    ".mp4": "video/mp4",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".flv": "video/x-flv",
    ".wmv": "video/x-ms-wmv",
}


def _format_size(size_bytes: int) -> str:
    """Format bytes into human-readable size string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


class AudioParser(BaseParser):
    """Parser for audio files with optional Whisper / AI transcription."""

    def __init__(self, config: Optional[Config] = None) -> None:
        self.config = config

    def parse(self, filepath: Path) -> Tuple[DocumentMetadata, str]:
        metadata = self.build_initial_metadata(filepath)
        suffix = filepath.suffix.lower()
        mime_type = AUDIO_MIME_TYPES.get(suffix) or mimetypes.guess_type(str(filepath))[0] or "audio/unknown"
        size_str = _format_size(metadata.file_size_bytes)

        lines = [
            f"# Audio: {filepath.name}",
            "",
            f"- **Format:** {suffix.upper().lstrip('.')} (`{mime_type}`)",
            f"- **File Size:** {size_str} ({metadata.file_size_bytes:,} bytes)",
            f"- **Path:** `{filepath.name}`",
            "",
        ]

        transcription = None
        if self.config and self.config.ai.enabled:
            transcription = transcribe_audio_whisper(filepath, ai_config=self.config.ai)

        if transcription:
            metadata.ia = True
            lines.extend([
                "## Audio Transcription",
                "",
                transcription,
                "",
            ])
            words = transcription.split()
            metadata.word_count = len(words)
            metadata.text_snippet = " ".join(words[:60])
        else:
            metadata.ia = False
            lines.extend([
                "> *Audio transcription not available (Whisper not installed or AI disabled).* ",
                "",
            ])
            metadata.word_count = 0
            metadata.text_snippet = f"[Audio ({suffix.upper().lstrip('.')}) • {size_str}]"

        clean_text = "\n".join(lines).strip()
        metadata.extracted_text = clean_text
        return metadata, clean_text


class VideoParser(BaseParser):
    """Parser for video files with keyframe extraction and Ollama vision analysis."""

    def __init__(self, config: Optional[Config] = None) -> None:
        self.config = config

    def parse(self, filepath: Path) -> Tuple[DocumentMetadata, str]:
        metadata = self.build_initial_metadata(filepath)
        suffix = filepath.suffix.lower()
        mime_type = VIDEO_MIME_TYPES.get(suffix) or mimetypes.guess_type(str(filepath))[0] or "video/unknown"
        size_str = _format_size(metadata.file_size_bytes)

        lines = [
            f"# Video: {filepath.name}",
            "",
            f"- **Format:** {suffix.upper().lstrip('.')} (`{mime_type}`)",
            f"- **File Size:** {size_str} ({metadata.file_size_bytes:,} bytes)",
            f"- **Path:** `{filepath.name}`",
            "",
        ]

        summary = None
        if self.config and self.config.ai.enabled and self.config.ai.vision_model:
            frames = extract_video_keyframes(filepath, max_frames=self.config.ai.max_video_frames)
            if frames:
                summary = query_ollama_multiple_images(
                    frames,
                    prompt=self.config.ai.prompt_video_summary,
                    ai_config=self.config.ai,
                )

        if summary:
            metadata.ia = True
            lines.extend([
                "## AI Video Scene Analysis",
                "",
                summary,
                "",
            ])
            words = summary.split()
            metadata.word_count = len(words)
            metadata.text_snippet = " ".join(words[:60])
        else:
            metadata.ia = False
            lines.extend([
                "> *Video AI summary not available (ffmpeg or Ollama vision model unavailable).* ",
                "",
            ])
            metadata.word_count = 0
            metadata.text_snippet = f"[Video ({suffix.upper().lstrip('.')}) • {size_str}]"

        clean_text = "\n".join(lines).strip()
        metadata.extracted_text = clean_text
        return metadata, clean_text
