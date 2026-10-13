"""Tests for AI configuration, media parsers (image, audio, video), and YAML ia attribute."""

import base64
from pathlib import Path
from unittest.mock import patch
import pytest

from directory2md.ai_client import (
    query_ollama_multiple_images,
    query_ollama_vision,
    transcribe_audio_whisper,
)
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
    assert config.ai.language == "en"
    assert config.ai.ollama_url == "http://localhost:11434"
    assert config.ai.vision_model == ""


def test_config_custom_language(tmp_path: Path):
    cfg_file = tmp_path / "directory2md.yaml"
    cfg_file.write_text("ai:\n  language: 'es'\n", encoding="utf-8")
    config = load_config(cfg_file)
    assert config.ai.language == "es"


def test_update_missing_config_keys_in_old_config(tmp_path: Path):
    from directory2md.config import update_missing_config_keys
    import yaml

    cfg_file = tmp_path / "directory2md.yaml"
    # Older config missing language, audio_model, prompts, force, verbose
    old_content = """# Old configuration file
days: 90
ai:
  enabled: true
  vision_model: "llama3.2-vision"
"""
    cfg_file.write_text(old_content, encoding="utf-8")

    added = update_missing_config_keys(cfg_file)
    assert "force" in added
    assert "verbose" in added
    assert "ai.language" in added
    assert "ai.audio_model" in added

    # Read updated file and verify values
    updated_text = cfg_file.read_text(encoding="utf-8")
    assert "# Old configuration file" in updated_text  # Comment preserved
    assert "days: 90" in updated_text  # Custom value preserved
    assert 'vision_model: "llama3.2-vision"' in updated_text  # Custom value preserved
    assert 'language: "en"' in updated_text  # Default missing key added

    # Load with load_config
    config = load_config(cfg_file)
    assert config.days == 90
    assert config.force is False
    assert config.verbose is False
    assert config.ai.enabled is True
    assert config.ai.language == "en"
    assert config.ai.vision_model == "llama3.2-vision"

    # Second run should detect no missing keys
    assert update_missing_config_keys(cfg_file) == []


def test_update_missing_config_keys_completely_missing_ai(tmp_path: Path):
    from directory2md.config import update_missing_config_keys

    cfg_file = tmp_path / "directory2md.yaml"
    cfg_file.write_text("days: 45\nforce: true\n", encoding="utf-8")

    added = update_missing_config_keys(cfg_file)
    assert "verbose" in added
    assert "ai.enabled" in added
    assert "ai.language" in added

    config = load_config(cfg_file)
    assert config.days == 45
    assert config.force is True
    assert config.verbose is False
    assert config.ai.language == "en"
    assert config.ai.enabled is False




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
    assert "base64" not in text
    assert "data:image" not in text
    assert "# Image: test.png" in text
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
        assert "base64" not in text
        assert "data:image" not in text
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


def test_ai_language_prompt_and_whisper_args(tmp_path: Path):
    ai_cfg = AIConfig(enabled=True, vision_model="llava", language="fr")

    # 1. Test query_ollama_vision appends language instruction for non-verbatim prompts
    captured_payloads = []

    def fake_urlopen(req, timeout):
        import json
        from unittest.mock import MagicMock
        data = json.loads(req.data.decode("utf-8"))
        captured_payloads.append(data)
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"response": "ok"}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        # Description prompt should have language appended
        query_ollama_vision(b"image_bytes", prompt="Describe the scene.", ai_config=ai_cfg)
        assert len(captured_payloads) == 1
        assert "Please respond in language: fr." in captured_payloads[0]["prompt"]

        # Verbatim prompt should NOT have language appended
        query_ollama_vision(b"image_bytes", prompt="Extract text verbatim.", ai_config=ai_cfg)
        assert len(captured_payloads) == 2
        assert "Please respond in language: fr." not in captured_payloads[1]["prompt"]

        # Multiple images query should have language appended
        query_ollama_multiple_images([b"f1"], prompt="Summarize frames.", ai_config=ai_cfg)
        assert len(captured_payloads) == 3
        assert "Please respond in language: fr." in captured_payloads[2]["prompt"]

    # 2. Test whisper gets --language argument and AudioParser passes ai_config
    dummy_audio = tmp_path / "test.mp3"
    dummy_audio.write_bytes(b"audio")

    with patch("shutil.which", return_value="/usr/bin/whisper"):
        with patch("subprocess.run") as mock_run:
            transcribe_audio_whisper(dummy_audio, ai_config=ai_cfg)
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert "--language" in cmd
            lang_idx = cmd.index("--language")
            assert cmd[lang_idx + 1] == "fr"

    # 3. AudioParser passes ai_config to transcribe_audio_whisper
    cfg = Config(ai=ai_cfg)
    audio_parser = AudioParser(config=cfg)
    with patch("directory2md.parsers.media_parser.transcribe_audio_whisper") as mock_transcribe:
        mock_transcribe.return_value = "Bonjour tout le monde"
        meta, _ = audio_parser.parse(dummy_audio)
        mock_transcribe.assert_called_once_with(dummy_audio, ai_config=ai_cfg)
        assert meta.ia is True

