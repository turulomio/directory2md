"""Tests for AI configuration, media parsers (image, audio, video), and YAML ia attribute."""

import base64
from pathlib import Path
from unittest.mock import patch
import pytest

from directory2md.ai_client import (
    AIError,
    prepare_image_for_vision,
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
    dst_file = dst / "document.txt.directory2md.md"
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


def test_config_video_model_alias(tmp_path: Path):
    cfg_file = tmp_path / "directory2md.yaml"
    cfg_file.write_text("ai:\n  video_model: 'llama3.2-vision'\n", encoding="utf-8")
    config = load_config(cfg_file)
    assert config.ai.vision_model == "llama3.2-vision"


def test_ai_language_prompt_and_whisper_args(tmp_path: Path):
    ai_cfg = AIConfig(enabled=True, vision_model="llava", language="fr", audio_model="medium")

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

    # 2. Test whisper gets --model and --language arguments
    dummy_audio = tmp_path / "test.mp3"
    dummy_audio.write_bytes(b"audio")

    with patch("shutil.which", return_value="/usr/bin/whisper"):
        with patch("subprocess.run") as mock_run:
            transcribe_audio_whisper(dummy_audio, ai_config=ai_cfg)
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert "--model" in cmd
            assert cmd[cmd.index("--model") + 1] == "medium"
            assert "--language" in cmd
            assert cmd[cmd.index("--language") + 1] == "fr"

    # 3. AudioParser passes ai_config to transcribe_audio_whisper
    cfg = Config(ai=ai_cfg)
    audio_parser = AudioParser(config=cfg)
    with patch("directory2md.parsers.media_parser.transcribe_audio_whisper") as mock_transcribe:
        mock_transcribe.return_value = "Bonjour tout le monde"
        meta, _ = audio_parser.parse(dummy_audio)
        mock_transcribe.assert_called_once_with(dummy_audio, ai_config=ai_cfg)
        assert meta.ia is True


def test_ai_timeout_handling(tmp_path: Path):
    from directory2md.ai_client import AITimeoutError

    cfg = Config(ai=AIConfig(enabled=True, vision_model="llava", audio_model="base", timeout_seconds=30))

    # 1. Image timeout raises and leaves no markdown file
    img_file = tmp_path / "timeout.png"
    img_file.write_bytes(b"\x89PNG\r\n\x1a\n...")
    with patch("directory2md.parsers.image_parser.query_ollama_vision", side_effect=AITimeoutError("Ollama query timed out after 30s")):
        img_parser = ImageParser(config=cfg)
        with pytest.raises(AITimeoutError):
            img_parser.parse(img_file)

    # 2. Audio timeout raises
    audio_file = tmp_path / "timeout.mp3"
    audio_file.write_bytes(b"audio_bytes")
    with patch("directory2md.parsers.media_parser.transcribe_audio_whisper", side_effect=AITimeoutError("Whisper timed out after 30s")):
        audio_parser = AudioParser(config=cfg)
        with pytest.raises(AITimeoutError):
            audio_parser.parse(audio_file)

    # 3. Video timeout raises
    video_file = tmp_path / "timeout.mp4"
    video_file.write_bytes(b"video_bytes")
    with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        with patch("directory2md.parsers.media_parser.extract_video_keyframes", return_value=[b"frame1"]):
            with patch("directory2md.parsers.media_parser.query_ollama_multiple_images", side_effect=AITimeoutError("Ollama timed out after 30s")):
                video_parser = VideoParser(config=cfg)
                with pytest.raises(AITimeoutError):
                    video_parser.parse(video_file)

    # 4. Conversion of directory on AI timeout deletes markdown and logs error with timestamp
    src_dir = tmp_path / "src_ai_timeout"
    dst_dir = tmp_path / "dst_ai_timeout"
    src_dir.mkdir()
    (src_dir / "timeout.png").write_bytes(b"\x89PNG\r\n\x1a\n...")

    logged_messages = []
    with patch("directory2md.parsers.image_parser.query_ollama_vision", side_effect=AITimeoutError("Ollama timeout")):
        stats = convert_directory(src_dir, dst_dir, config=cfg, log_callback=logged_messages.append)

    assert stats.has_errors
    assert len(stats.errors) == 1
    err_path, err_str = stats.errors[0]
    assert "timeout.png" in err_path
    error_msgs = [msg for msg in logged_messages if "[ERROR]" in msg]
    assert len(error_msgs) == 1
    assert "timeout.png" in error_msgs[0]
    # Verify no markdown file is left behind
    assert not (dst_dir / "timeout.png.directory2md.md").exists()


def test_image_ai_description_in_config_language(tmp_path: Path):
    """Test that image descriptions use the language from the config (e.g. Spanish)."""
    cfg = Config(ai=AIConfig(enabled=True, vision_model="llama3.2-vision", language="es"))

    captured_prompt = None

    def fake_query(img_bytes, prompt, ai_config):
        nonlocal captured_prompt
        captured_prompt = prompt
        return "Una fotografía en color que muestra un paisaje montañoso con un lago claro."

    with patch("directory2md.parsers.image_parser.query_ollama_vision", side_effect=fake_query):
        img_file = tmp_path / "foto.jpg"
        img_file.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb")

        parser = ImageParser(config=cfg)
        meta, text = parser.parse(img_file)

        assert meta.ia is True
        assert "## AI Image Description" in text
        assert "paisaje montañoso" in text


def test_html_embedded_images_ai_container_conversion(tmp_path: Path):
    """Test that HTML with embedded images converts to container and describes images with AI."""
    src_dir = tmp_path / "html_in"
    src_dir.mkdir()
    dst_dir = tmp_path / "html_out"
    dst_dir.mkdir()

    cfg = Config(ai=AIConfig(enabled=True, vision_model="llama3.2-vision", language="es"))

    html_file = src_dir / "article.html"
    html_file.write_text(
        """<html><body>
        <h1>Artículo con Gráfico</h1>
        <p>A continuación se muestra el gráfico estadístico:</p>
        <img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=" alt="Gráfico 1">
        </body></html>""",
        encoding="utf-8",
    )

    with patch(
        "directory2md.parsers.image_parser.query_ollama_vision",
        return_value="Gráfico de barras mostrando el crecimiento anual en español.",
    ):
        convert_directory(src_dir, dst_dir, config=cfg)

    # 1. Container directory created
    container = dst_dir / "article.html.directory2md"
    assert container.is_dir()

    # 2. Primary markdown
    primary = container / "article.html.directory2md.md"
    assert primary.exists()
    primary_text = primary.read_text(encoding="utf-8")
    assert "data:image" not in primary_text
    assert "image_001.png" in primary_text

    # 3. Member markdown with AI description
    member = container / "image_001.png.directory2md.md"
    assert member.exists()
    member_text = member.read_text(encoding="utf-8")
    assert "ia: true" in member_text
    assert "ia_model: llama3.2-vision" in member_text
    assert "ia_version: latest" in member_text
    assert "- **AI Model:** `llama3.2-vision` (version: `latest`)" in member_text
    assert "Gráfico de barras mostrando el crecimiento anual" in member_text


def test_resolve_ai_model_and_version():
    from directory2md.ai_client import resolve_ai_model_and_version

    assert resolve_ai_model_and_version("llama3.2-vision:11b") == ("llama3.2-vision", "11b")
    assert resolve_ai_model_and_version("llama3.2-vision") == ("llama3.2-vision", "latest")
    assert resolve_ai_model_and_version("llava:7b") == ("llava", "7b")
    assert resolve_ai_model_and_version("llava") == ("llava", "latest")
    assert resolve_ai_model_and_version("base", default_model="whisper") == ("whisper", "base")
    assert resolve_ai_model_and_version("medium", default_model="whisper") == ("whisper", "medium")
    assert resolve_ai_model_and_version("whisper:large-v3") == ("whisper", "large-v3")
    assert resolve_ai_model_and_version("whisper-turbo", default_model="whisper") == ("whisper", "turbo")
    assert resolve_ai_model_and_version("") == ("", "")


def test_ia_model_and_version_in_media_parsers(tmp_path: Path):
    from directory2md.markdown_utils import serialize_document

    cfg_image = Config(ai=AIConfig(enabled=True, vision_model="llama3.2-vision:11b"))
    img_file = tmp_path / "sample.png"
    img_file.write_bytes(b"\x89PNG\r\n\x1a\n...")

    with patch("directory2md.parsers.image_parser.query_ollama_vision", return_value="Visual description text"):
        img_parser = ImageParser(config=cfg_image)
        meta, text = img_parser.parse(img_file)
        assert meta.ia is True
        assert meta.ia_model == "llama3.2-vision"
        assert meta.ia_version == "11b"
        assert "- **AI Model:** `llama3.2-vision` (version: `11b`)" in text

        serialized = serialize_document(meta, text)
        assert "ia: true" in serialized
        assert "ia_model: llama3.2-vision" in serialized
        assert "ia_version: 11b" in serialized

    cfg_audio = Config(ai=AIConfig(enabled=True, audio_model="medium"))
    audio_file = tmp_path / "sample.mp3"
    audio_file.write_bytes(b"audio_bytes")

    with patch("directory2md.parsers.media_parser.transcribe_audio_whisper", return_value="Audio speech text"):
        aud_parser = AudioParser(config=cfg_audio)
        a_meta, a_text = aud_parser.parse(audio_file)
        assert a_meta.ia is True
        assert a_meta.ia_model == "whisper"
        assert a_meta.ia_version == "medium"
        assert "- **AI Model:** `whisper` (version: `medium`)" in a_text

        a_serialized = serialize_document(a_meta, a_text)
        assert "ia: true" in a_serialized
        assert "ia_model: whisper" in a_serialized
        assert "ia_version: medium" in a_serialized

    cfg_video = Config(ai=AIConfig(enabled=True, vision_model="llava:13b"))
    video_file = tmp_path / "sample.mp4"
    video_file.write_bytes(b"video_bytes")

    with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        with patch("directory2md.parsers.media_parser.extract_video_keyframes", return_value=[b"f1"]):
            with patch("directory2md.parsers.media_parser.query_ollama_multiple_images", return_value="Video scene text"):
                vid_parser = VideoParser(config=cfg_video)
                v_meta, v_text = vid_parser.parse(video_file)
                assert v_meta.ia is True
                assert v_meta.ia_model == "llava"
                assert v_meta.ia_version == "13b"
                assert "- **AI Model:** `llava` (version: `13b`)" in v_text

                v_serialized = serialize_document(v_meta, v_text)
                assert "ia: true" in v_serialized
                assert "ia_model: llava" in v_serialized
                assert "ia_version: 13b" in v_serialized


def test_ollama_http_400_unsupported_vision_model_error():
    """Verify that Ollama HTTP 400 errors extract the body message and provide vision model guidance."""
    import io
    import urllib.error

    ai_cfg = AIConfig(enabled=True, vision_model="gemma4:e2b")

    err_body = b'{"error": "model \'gemma4:e2b\' does not support images"}'
    err_fp = io.BytesIO(err_body)
    http_error = urllib.error.HTTPError(
        "http://localhost:11434/api/generate",
        400,
        "Bad Request",
        {},
        err_fp,
    )

    with patch("urllib.request.urlopen", side_effect=http_error):
        with pytest.raises(AIError) as exc_info:
            query_ollama_vision(b"fake_image_bytes", prompt="Describe image", ai_config=ai_cfg)

        err_str = str(exc_info.value)
        assert "HTTP Error 400: Bad Request" in err_str
        assert "model 'gemma4:e2b' does not support images" in err_str
        assert "[HINT]" in err_str
        assert "multimodal vision model" in err_str


def test_prepare_image_for_vision():
    """Verify image normalization with Pillow (skipping spacers, converting RGBA to RGB JPEG)."""
    import io
    from PIL import Image

    # 1. Empty bytes
    assert prepare_image_for_vision(b"") is None

    # 2. Tiny spacer image (2x2) -> Should be skipped (None)
    tiny = Image.new("RGBA", (2, 2), (255, 255, 255, 0))
    buf = io.BytesIO()
    tiny.save(buf, format="PNG")
    assert prepare_image_for_vision(buf.getvalue()) is None

    # 3. Valid RGBA image (20x20) -> Should be converted to RGB JPEG
    valid_rgba = Image.new("RGBA", (20, 20), (255, 0, 0, 128))
    buf_valid = io.BytesIO()
    valid_rgba.save(buf_valid, format="PNG")
    prepared = prepare_image_for_vision(buf_valid.getvalue())
    assert prepared is not None
    assert prepared != buf_valid.getvalue()
    with Image.open(io.BytesIO(prepared)) as out_img:
        assert out_img.format == "JPEG"
        assert out_img.mode == "RGB"
        assert out_img.size == (20, 20)

    # 4. Unknown/mock bytes -> Passed through unchanged
    mock_bytes = b"mock_dummy_bytes_here"
    assert prepare_image_for_vision(mock_bytes) == mock_bytes


def test_is_text_in_english():
    from directory2md.ai_client import is_text_in_english

    # English text when target is Spanish
    eng_text = "The image shows a modern laptop on a wooden desk with a white coffee mug."
    assert is_text_in_english(eng_text, "es") is True

    # Spanish text when target is Spanish
    es_text = "La imagen muestra un portátil moderno sobre un escritorio de madera con una taza de café blanca."
    assert is_text_in_english(es_text, "es") is False

    # Short texts or English target
    assert is_text_in_english("ok", "es") is False
    assert is_text_in_english(eng_text, "en") is False


def test_vision_system_prompt_and_auto_translation_fallback():
    import json
    from unittest.mock import MagicMock

    ai_cfg = AIConfig(enabled=True, vision_model="llama3.2-vision", language="es")
    captured_payloads = []

    def mock_urlopen(req, timeout):
        payload = json.loads(req.data.decode("utf-8"))
        captured_payloads.append(payload)

        # First call is vision query, returns English text
        # Second call is translation query, returns Spanish translation
        if len(captured_payloads) == 1:
            resp_data = {"response": "The image shows a blue car parked on the street with trees in the background."}
        else:
            resp_data = {"response": "La imagen muestra un coche azul aparcado en la calle con árboles al fondo."}

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(resp_data).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        result = query_ollama_vision(
            b"dummy_image_bytes",
            prompt="Provide a comprehensive and detailed description of the contents and context of this image.",
            ai_config=ai_cfg,
        )

        # 1. Vision payload had system prompt in Spanish
        assert len(captured_payloads) == 2
        assert "system" in captured_payloads[0]
        assert "español" in captured_payloads[0]["system"].lower()
        assert "Describe de forma exhaustiva" in captured_payloads[0]["prompt"]

        # 2. Second payload was translation request
        assert "Translate the following text into Spanish" in captured_payloads[1]["prompt"]

        # 3. Final result returned is translated Spanish text
        assert "La imagen muestra un coche azul" in result



