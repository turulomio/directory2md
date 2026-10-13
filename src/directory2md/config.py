"""Configuration management for directory2md."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
import yaml



@dataclass
class AIConfig:
    """Configuration for AI / Ollama processing."""

    enabled: bool = False
    language: str = "es"
    ollama_url: str = "http://localhost:11434"
    vision_model: str = ""
    audio_model: str = ""
    prompt_image_ocr: str = "Extract all readable text from this image verbatim. Do not add conversational filler."
    prompt_image_description: str = "Provide a comprehensive and detailed description of the contents and context of this image."
    prompt_video_summary: str = "Analyze these extracted video keyframes and summarize the scene, actions, and key visual information."
    max_video_frames: int = 3
    timeout_seconds: int = 60

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Config:
    """Root configuration for directory2md."""

    days: int = 180
    force: bool = False
    verbose: bool = False
    ai: AIConfig = field(default_factory=AIConfig)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "days": self.days,
            "force": self.force,
            "verbose": self.verbose,
            "ai": self.ai.to_dict(),
        }


DEFAULT_CONFIG_TEMPLATE = """# directory2md configuration file
# This file was generated automatically. Edit your settings below.

# General conversion settings
days: 180                 # Age threshold in days to re-convert existing markdown files (default: 180)
force: false              # Force re-conversion of all files regardless of age
verbose: false            # Show detailed progress for each file

# AI & Ollama settings
ai:
  enabled: false          # Set to true to enable AI processing (OCR, descriptions for images, audio, video)
  language: "es"          # Language of AI results, summaries, and descriptions (e.g., "es", "en", "fr")
  ollama_url: "http://localhost:11434"  # Default Ollama endpoint (localhost:11434)
  
  # Models (configure freely according to the models you have in Ollama)
  # Examples for vision: "llava", "llama3.2-vision", "qwen2.5-vl", "minicpm-v"
  # Examples for audio: "whisper"
  vision_model: ""        # e.g., "llava" or "llama3.2-vision"
  audio_model: ""         # e.g., "whisper"
  
  # Custom prompts
  prompt_image_ocr: "Extract all readable text from this image verbatim. Do not add conversational filler."
  prompt_image_description: "Provide a comprehensive and detailed description of the contents and context of this image."
  prompt_video_summary: "Analyze these extracted video keyframes and summarize the scene, actions, and key visual information."
  
  # Extraction options
  max_video_frames: 3     # Maximum keyframes to sample from a video for AI analysis
  timeout_seconds: 60     # Request timeout in seconds for Ollama requests
"""


logger = logging.getLogger("directory2md.config")

ROOT_KEYS_ORDER = ["days", "force", "verbose", "ai"]

AI_KEYS_ORDER = [
    "enabled",
    "language",
    "ollama_url",
    "vision_model",
    "audio_model",
    "prompt_image_ocr",
    "prompt_image_description",
    "prompt_video_summary",
    "max_video_frames",
    "timeout_seconds",
]

ROOT_TEMPLATES = {
    "days": "days: 180                 # Age threshold in days to re-convert existing markdown files (default: 180)\n",
    "force": "force: false              # Force re-conversion of all files regardless of age\n",
    "verbose": "verbose: false            # Show detailed progress for each file\n",
    "ai": "\n# AI & Ollama settings\nai:\n",
}

AI_TEMPLATES = {
    "enabled": '  enabled: false          # Set to true to enable AI processing (OCR, descriptions for images, audio, video)\n',
    "language": '  language: "es"          # Language of AI results, summaries, and descriptions (e.g., "es", "en", "fr")\n',
    "ollama_url": '  ollama_url: "http://localhost:11434"  # Default Ollama endpoint (localhost:11434)\n',
    "vision_model": '  vision_model: ""        # e.g., "llava" or "llama3.2-vision"\n',
    "audio_model": '  audio_model: ""         # e.g., "whisper"\n',
    "prompt_image_ocr": '  prompt_image_ocr: "Extract all readable text from this image verbatim. Do not add conversational filler."\n',
    "prompt_image_description": '  prompt_image_description: "Provide a comprehensive and detailed description of the contents and context of this image."\n',
    "prompt_video_summary": '  prompt_video_summary: "Analyze these extracted video keyframes and summarize the scene, actions, and key visual information."\n',
    "max_video_frames": '  max_video_frames: 3     # Maximum keyframes to sample from a video for AI analysis\n',
    "timeout_seconds": '  timeout_seconds: 60     # Request timeout in seconds for Ollama requests\n',
}


def create_default_config_file(target_file: Path) -> None:
    """Write the default configuration file template to target_file."""
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text(DEFAULT_CONFIG_TEMPLATE, encoding="utf-8")


def _find_key_line_index(lines: List[str], key: str, start: int = 0, end: Optional[int] = None) -> Optional[int]:
    """Find line index matching a YAML key definition."""
    if end is None:
        end = len(lines)
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*:")
    for idx in range(start, end):
        if pattern.match(lines[idx]):
            return idx
    return None


def _find_section_end(lines: List[str], start_idx: int) -> int:
    """Find the insertion index at the end of an indented YAML section."""
    idx = start_idx + 1
    last_content_idx = idx
    while idx < len(lines):
        line = lines[idx]
        stripped = line.strip()
        if stripped and not line.startswith((" ", "\t")) and not stripped.startswith("#"):
            return idx
        if stripped and not stripped.startswith("#"):
            last_content_idx = idx + 1
        idx += 1
    return last_content_idx


def update_missing_config_keys(config_file: Path) -> List[str]:
    """Check if config_file is missing any configuration keys and update it in-place.

    Preserves all existing comments, formatting, and user values while inserting
    missing keys with default values and descriptive comments.

    Args:
        config_file: Path to YAML configuration file.

    Returns:
        List of missing key names that were added to the file.
    """
    if not config_file.exists():
        return []

    try:
        content = config_file.read_text(encoding="utf-8")
    except OSError:
        return []

    if not content.strip():
        create_default_config_file(config_file)
        return ["days", "force", "verbose", "ai"]

    try:
        data = yaml.safe_load(content)
    except Exception:
        return []

    if not isinstance(data, dict):
        return []

    missing_root: List[str] = [k for k in ROOT_KEYS_ORDER if k not in data]
    ai_data = data.get("ai")
    if ai_data is None or not isinstance(ai_data, dict):
        missing_ai: List[str] = list(AI_KEYS_ORDER)
    else:
        missing_ai: List[str] = [k for k in AI_KEYS_ORDER if k not in ai_data]

    if not missing_root and not missing_ai:
        return []

    added_keys: List[str] = []
    file_lines = content.splitlines(keepends=True)
    if file_lines and not file_lines[-1].endswith("\n"):
        file_lines[-1] += "\n"

    # 1. Update missing root keys (days, force, verbose)
    for root_key in ["days", "force", "verbose"]:
        if root_key in missing_root:
            target_idx = None
            for next_key in ROOT_KEYS_ORDER[ROOT_KEYS_ORDER.index(root_key) + 1:]:
                target_idx = _find_key_line_index(file_lines, next_key)
                if target_idx is not None:
                    break
            if target_idx is not None:
                file_lines.insert(target_idx, ROOT_TEMPLATES[root_key])
            else:
                file_lines.append(ROOT_TEMPLATES[root_key])
            added_keys.append(root_key)

    # 2. Update AI section
    if "ai" in missing_root:
        file_lines.append(ROOT_TEMPLATES["ai"])
        for ai_key in AI_KEYS_ORDER:
            file_lines.append(AI_TEMPLATES[ai_key])
            added_keys.append(f"ai.{ai_key}")
    elif missing_ai:
        ai_idx = _find_key_line_index(file_lines, "ai")
        if ai_idx is not None:
            ai_end = _find_section_end(file_lines, ai_idx)
            for ai_key in missing_ai:
                inserted = False
                key_pos = AI_KEYS_ORDER.index(ai_key)
                for next_ai_key in AI_KEYS_ORDER[key_pos + 1:]:
                    target_idx = _find_key_line_index(file_lines, next_ai_key, start=ai_idx + 1, end=ai_end)
                    if target_idx is not None:
                        file_lines.insert(target_idx, AI_TEMPLATES[ai_key])
                        ai_end += 1
                        inserted = True
                        break
                if not inserted:
                    file_lines.insert(ai_end, AI_TEMPLATES[ai_key])
                    ai_end += 1
                added_keys.append(f"ai.{ai_key}")

    new_content = "".join(file_lines)
    try:
        reparsed = yaml.safe_load(new_content)
        if isinstance(reparsed, dict):
            config_file.write_text(new_content, encoding="utf-8")
            return added_keys
    except Exception as exc:
        logger.warning("Failed to validate updated config file '%s': %s", config_file, exc)

    return []


def load_config(config_file: Path, update_if_missing: bool = True) -> Config:
    """Load configuration from a YAML file.

    If update_if_missing is True, any missing keys will be automatically
    added to config_file with their default values and comments.

    Args:
        config_file: Path to YAML config file.
        update_if_missing: Whether to add missing keys to config_file.

    Returns:
        Config instance populated with settings.
    """
    if not config_file.exists():
        return Config()

    if update_if_missing:
        update_missing_config_keys(config_file)

    try:
        content = config_file.read_text(encoding="utf-8")
        data = yaml.safe_load(content) or {}
        if not isinstance(data, dict):
            return Config()

        ai_data = data.get("ai", {})
        if not isinstance(ai_data, dict):
            ai_data = {}

        ai_config = AIConfig(
            enabled=bool(ai_data.get("enabled", False)),
            language=str(ai_data.get("language", "es")),
            ollama_url=str(ai_data.get("ollama_url", "http://localhost:11434")),
            vision_model=str(ai_data.get("vision_model", "")),
            audio_model=str(ai_data.get("audio_model", "")),
            prompt_image_ocr=str(ai_data.get("prompt_image_ocr", AIConfig.prompt_image_ocr)),
            prompt_image_description=str(ai_data.get("prompt_image_description", AIConfig.prompt_image_description)),
            prompt_video_summary=str(ai_data.get("prompt_video_summary", AIConfig.prompt_video_summary)),
            max_video_frames=int(ai_data.get("max_video_frames", 3)),
            timeout_seconds=int(ai_data.get("timeout_seconds", 60)),
        )

        return Config(
            days=int(data.get("days", 180)),
            force=bool(data.get("force", False)),
            verbose=bool(data.get("verbose", False)),
            ai=ai_config,
        )
    except Exception:
        return Config()

