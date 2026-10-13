"""Tests for AI configuration, media parsers (image, audio, video), and YAML ia attribute."""

import base64
from pathlib import Path
from unittest.mock import patch
import pytest

from directory2md.config import AIConfig, Config, create_default_config_file, load_config
from directory2md.converter import convert_directory
from directory2md.markdown_utils import parse_frontmatter
from directory2md.parsers.image_parser import ImageParser
from directory2md.parsers.media_parser import AudioParser, VideoParser


def test_config_create_and_load(tmp_path: Path):
    cfg_file = tmp_path / "directory2md.yaml"
    create_default_config_file(cfg_file)
    assert cfg_file.exists()

    config = load_config(cfg_file)
    assert config.days == 180
    assert not config.ai.enabled
    assert config.ai.ollama_url == "http://localhost:11434"
    assert config.ai.vision_model == ""


def test_ia_frontmatter_attribute_default_false(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    (src / "document.txt").write_text("Regular non-AI document")

    convert_directory(src, dst)
    dst_file = dst / "document.txt.md"
    assert dst_file.exists()

    fm, _ = parse_frontmatter(dst_file.read_text(encoding="utf-8"))
    assert "ia" in fm
    assert fm["ia"] is False


def test_image_parser_without_ai(tmp_path: Path):
    img_file = tmp_path / "test.png"
    # Minimal 1x1 PNG
    img_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    )
    img_file.write_bytes(img_bytes)

    parser = ImageParser()
    meta, text = parser.parse(img_file)
    assert meta.ia is False
    assert "data:image/png;base64," in text
    assert "## AI OCR" not in text


def test_image_parser_with_ai_mocked(tmp_path: Path):
    img_file = tmp_path / "bill.png"
    img_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    )
    img_file.write_bytes(img_bytes)

    config = Config(
        ai=AIConfig(
            enabled=True,
            vision_model="llava",
            ollama_url="http://localhost:11434",
        )
    )

    def fake_ollama_vision(raw_bytes, prompt, ai_config):
        if "verbatim" in prompt.lower() or "readable text" in prompt.lower():
            return "FACTURA TOTAL: 150.00 EUR"
        return "Una factura digital con desglose de importes e impuestos."

    with patch("directory2md.parsers.image_parser.query_ollama_vision", side_effect=fake_ollama_vision):
        parser = ImageParser(config=config)
        meta, text = parser.parse(img_file)

        assert meta.ia is True
        assert "## AI OCR (Extracted Text)" in text
        assert "FACTURA TOTAL: 150.00 EUR" in text
        assert "## AI Image Description" in text
        assert "Una factura digital" in text


def test_audio_and_video_parsers(tmp_path: Path):
    audio_file = tmp_path / "clip.mp3"
    audio_file.write_bytes(b"FAKE_AUDIO_DATA")

    video_file = tmp_path / "movie.mp4"
    video_file.write_bytes(b"FAKE_VIDEO_DATA")

    # 1. Without AI
    audio_parser = AudioParser()
    audio_meta, audio_text = audio_parser.parse(audio_file)
    assert audio_meta.ia is False
    assert "Audio: clip.mp3" in audio_text

    video_parser = VideoParser()
    video_meta, video_text = video_parser.parse(video_file)
    assert video_meta.ia is False
    assert "Video: movie.mp4" in video_text

    # 2. With AI mocks
    config = Config(
        ai=AIConfig(
            enabled=True,
            vision_model="llava",
            audio_model="whisper",
        )
    )

    with patch(
        "directory2md.parsers.media_parser.transcribe_audio_whisper",
        return_value="Bienvenidos a la grabación de prueba.",
    ):
        ai_audio_parser = AudioParser(config=config)
        a_meta, a_text = ai_audio_parser.parse(audio_file)
        assert a_meta.ia is True
        assert "## Audio Transcription" in a_text
        assert "Bienvenidos a la grabación" in a_text

    with patch("directory2md.parsers.media_parser.extract_video_keyframes", return_value=[b"frame1"]):
        with patch(
            "directory2md.parsers.media_parser.query_ollama_multiple_images",
            return_value="El vídeo muestra una presentación técnica con diapositivas.",
        ):
            ai_video_parser = VideoParser(config=config)
            v_meta, v_text = ai_video_parser.parse(video_file)
            assert v_meta.ia is True
            assert "## AI Video Scene Analysis" in v_text
            assert "presentación técnica" in v_text
