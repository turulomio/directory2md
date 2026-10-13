"""AI client for Ollama API integration and media processing."""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import List, Optional
import urllib.error
import urllib.request

from directory2md.config import AIConfig

logger = logging.getLogger("directory2md.ai")


class AITimeoutError(TimeoutError):
    """Raised when an AI operation (Ollama or Whisper) exceeds its configured timeout."""


def query_ollama_vision(
    image_bytes: bytes,
    prompt: str,
    ai_config: AIConfig,
) -> Optional[str]:
    """Query Ollama vision model with an image and prompt.

    Args:
        image_bytes: Raw binary bytes of the image.
        prompt: Instruction prompt for the vision model.
        ai_config: AI configuration containing model and Ollama endpoint.

    Returns:
        Generated text response or None if failed.
    """
    if not ai_config.enabled or not ai_config.vision_model:
        return None

    b64_image = base64.b64encode(image_bytes).decode("ascii")
    endpoint = f"{ai_config.ollama_url.rstrip('/')}/api/generate"

    full_prompt = prompt
    if ai_config.language and "verbatim" not in prompt.lower():
        full_prompt = f"{prompt}\nPlease respond in language: {ai_config.language}."

    payload = {
        "model": ai_config.vision_model,
        "prompt": full_prompt,
        "images": [b64_image],
        "stream": False,
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=ai_config.timeout_seconds) as resp:
            if resp.status == 200:
                body = json.loads(resp.read().decode("utf-8"))
                return str(body.get("response", "")).strip()
    except (TimeoutError, urllib.error.URLError) as exc:
        if isinstance(exc, TimeoutError) or "timed out" in str(exc).lower():
            logger.warning("Ollama vision query timed out after %ds for model '%s'", ai_config.timeout_seconds, ai_config.vision_model)
            raise AITimeoutError(f"Ollama vision query timed out after {ai_config.timeout_seconds}s") from exc
        logger.warning("Ollama vision query failed for model '%s': %s", ai_config.vision_model, exc)
    except Exception as exc:
        if "timed out" in str(exc).lower():
            logger.warning("Ollama vision query timed out after %ds for model '%s'", ai_config.timeout_seconds, ai_config.vision_model)
            raise AITimeoutError(f"Ollama vision query timed out after {ai_config.timeout_seconds}s") from exc
        logger.warning("Ollama vision query failed for model '%s': %s", ai_config.vision_model, exc)

    return None


def query_ollama_multiple_images(
    images_bytes: List[bytes],
    prompt: str,
    ai_config: AIConfig,
) -> Optional[str]:
    """Query Ollama vision model with multiple image frames.

    Args:
        images_bytes: List of image bytes (keyframes).
        prompt: Instruction prompt.
        ai_config: AI configuration.

    Returns:
        Generated text response or None if failed.
    """
    if not ai_config.enabled or not ai_config.vision_model or not images_bytes:
        return None

    b64_images = [base64.b64encode(b).decode("ascii") for b in images_bytes]
    endpoint = f"{ai_config.ollama_url.rstrip('/')}/api/generate"

    full_prompt = prompt
    if ai_config.language:
        full_prompt = f"{prompt}\nPlease respond in language: {ai_config.language}."

    payload = {
        "model": ai_config.vision_model,
        "prompt": full_prompt,
        "images": b64_images,
        "stream": False,
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=ai_config.timeout_seconds) as resp:
            if resp.status == 200:
                body = json.loads(resp.read().decode("utf-8"))
                return str(body.get("response", "")).strip()
    except (TimeoutError, urllib.error.URLError) as exc:
        if isinstance(exc, TimeoutError) or "timed out" in str(exc).lower():
            logger.warning("Ollama multi-image vision query timed out after %ds", ai_config.timeout_seconds)
            raise AITimeoutError(f"Ollama multi-image vision query timed out after {ai_config.timeout_seconds}s") from exc
        logger.warning("Ollama multi-image vision query failed: %s", exc)
    except Exception as exc:
        if "timed out" in str(exc).lower():
            logger.warning("Ollama multi-image vision query timed out after %ds", ai_config.timeout_seconds)
            raise AITimeoutError(f"Ollama multi-image vision query timed out after {ai_config.timeout_seconds}s") from exc
        logger.warning("Ollama multi-image vision query failed: %s", exc)

    return None


def extract_video_keyframes(video_path: Path, max_frames: int = 3) -> List[bytes]:
    """Extract keyframe images from a video file using ffmpeg if available.

    Args:
        video_path: Path to video file.
        max_frames: Maximum number of frames to extract.

    Returns:
        List of raw PNG image bytes for extracted keyframes.
    """
    if not shutil.which("ffmpeg"):
        return []

    frames: List[bytes] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        output_pattern = str(tmp / "frame_%03d.png")

        try:
            # Extract up to max_frames spaced evenly across video duration
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(video_path),
                "-vf",
                f"thumbnail,fps=1/{max_frames}",
                "-vframes",
                str(max_frames),
                output_pattern,
            ]
            subprocess.run(cmd, check=True, timeout=30)

            for frame_file in sorted(tmp.glob("frame_*.png")):
                frames.append(frame_file.read_bytes())
        except Exception as exc:
            logger.debug("ffmpeg frame extraction failed for '%s': %s", video_path, exc)

    return frames


def transcribe_audio_whisper(audio_path: Path, ai_config: Optional[AIConfig] = None) -> Optional[str]:
    """Transcribe audio using local whisper CLI tool if installed.

    Args:
        audio_path: Path to audio file.
        ai_config: Optional AI configuration specifying language.

    Returns:
        Transcribed text or None.
    """
    whisper_cmd = shutil.which("whisper")
    if not whisper_cmd:
        venv_whisper = Path(sys.prefix) / "bin" / "whisper"
        if venv_whisper.exists():
            whisper_cmd = str(venv_whisper)

    if not whisper_cmd:
        return None

    timeout_val = ai_config.timeout_seconds if (ai_config and ai_config.timeout_seconds) else 120
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd = [
                whisper_cmd,
                str(audio_path),
                "--output_dir",
                tmpdir,
                "--output_format",
                "txt",
            ]
            if ai_config and ai_config.audio_model:
                cmd.extend(["--model", ai_config.audio_model])
            if ai_config and ai_config.language:
                cmd.extend(["--language", ai_config.language])

            subprocess.run(cmd, check=True, timeout=timeout_val)
            txt_files = list(Path(tmpdir).glob("*.txt"))
            if txt_files:
                return txt_files[0].read_text(encoding="utf-8").strip()
    except subprocess.TimeoutExpired as exc:
        logger.warning("Whisper transcription timed out for '%s' after %ss", audio_path, exc.timeout)
        raise AITimeoutError(f"Whisper audio transcription timed out after {exc.timeout}s") from exc
    except Exception as exc:
        if "timed out" in str(exc).lower():
            raise AITimeoutError(f"Whisper audio transcription timed out: {exc}") from exc
        logger.warning("Whisper transcription failed for '%s': %s", audio_path, exc)

    return None
