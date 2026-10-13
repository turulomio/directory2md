"""Configuration management for directory2md."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional
import yaml


@dataclass
class AIConfig:
    """Configuration for AI / Ollama processing."""

    enabled: bool = False
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


def create_default_config_file(target_file: Path) -> None:
    """Write the default configuration file template to target_file."""
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text(DEFAULT_CONFIG_TEMPLATE, encoding="utf-8")


def load_config(config_file: Path) -> Config:
    """Load configuration from a YAML file.

    Args:
        config_file: Path to YAML config file.

    Returns:
        Config instance populated with settings.
    """
    if not config_file.exists():
        return Config()

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
