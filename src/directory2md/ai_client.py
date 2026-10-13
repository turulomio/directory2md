"""AI client for Ollama API integration and media processing."""

from __future__ import annotations

import base64
import io
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


LANGUAGE_NAMES: dict[str, str] = {
    "es": "Spanish (español)",
    "en": "English",
    "fr": "French (français)",
    "de": "German (Deutsch)",
    "it": "Italian (italiano)",
    "pt": "Portuguese (português)",
    "ca": "Catalan (català)",
    "gl": "Galician (galego)",
    "eu": "Basque (euskara)",
    "nl": "Dutch (Nederlands)",
    "ru": "Russian (русский)",
    "zh": "Chinese (中文)",
    "ja": "Japanese (日本語)",
    "ko": "Korean (한국어)",
    "ar": "Arabic (العربية)",
}

LOCALIZED_IMAGE_DESCRIPTION_PROMPTS: dict[str, str] = {
    "es": "Describe de forma exhaustiva y detallada el contenido y contexto de esta imagen en español.",
    "fr": "Décrivez de façon exhaustive et détaillée le contenu et le contexte de cette image en français.",
    "de": "Beschreiben Sie den Inhalt und Kontext dieses Bildes ausführlich und detailliert auf Deutsch.",
    "it": "Fornisci una descrizione completa e dettagliata dei contenuti e del contesto di questa immagine in italiano.",
    "pt": "Forneça uma descrição detalhada e completa do conteúdo e do contexto desta imagem em português.",
    "ca": "Descriu de manera exhaustiva i detallada el contingut i el context d'aquesta imatge en català.",
}

LOCALIZED_VIDEO_SUMMARY_PROMPTS: dict[str, str] = {
    "es": "Analiza estos fotogramas extraídos del vídeo y resume la escena, las acciones y la información visual clave en español.",
    "fr": "Analysez ces images clés extraites de la vidéo et résumez la scène, les actions et les informations visuelles clés en français.",
    "de": "Analysieren Sie diese aus dem Video extrahierten Keyframes und fassen Sie die Szene, Aktionen und visuellen Schlüsselinformationen auf Deutsch zusammen.",
    "it": "Analizza questi fotogrammi chiave estratti dal video e riassumi la scena, le azioni e le informazioni visive chiave in italiano.",
    "pt": "Analise estes quadros-chave extraídos do vídeo e resuma a cena, as ações e as principais informações visuais em português.",
    "ca": "Analitza aquests fotogrames clau extrets del vídeo i resumeix l'escena, les accions i la informació visual clau en català.",
}

LOCALIZED_VISION_SYSTEM_PROMPTS: dict[str, str] = {
    "es": (
        "Eres un asistente de inteligencia artificial experto en visión. "
        "Tu labor es describir imágenes o vídeos detalladamente y de forma exhaustiva EXCLUSIVAMENTE en español. "
        "Está terminantemente prohibido responder en inglés. Todo tu texto DEBE estar en español."
    ),
    "fr": (
        "Vous êtes un assistant visuel IA. Votre tâche est de décrire les images EXCLUSIVEMENT en français. "
        "Il est strictement interdit de répondre en anglais. Tout votre texte DOIT être en français."
    ),
    "de": (
        "Sie sind ein KI-Bildassistent. Ihre Aufgabe ist es, Bilder AUSSCHLIESSLICH auf Deutsch zu beschreiben. "
        "Es ist strengstens verboten, auf Englisch zu antworten. Ihr gesamter Text MUSS auf Deutsch sein."
    ),
    "it": (
        "Sei un assistente visivo IA. Il tuo compito è descrivere le immagini ESCLUSIVAMENTE in italiano. "
        "È severamente vietato rispondere in inglese. Tutto il tuo testo DEVE essere in italiano."
    ),
    "pt": (
        "Você é um assistente visual de IA. Sua tarefa é descrever imagens EXCLUSIVAMENTE em português. "
        "É estritamente proibido responder em inglês. Todo o seu texto DEVE ser em português."
    ),
    "ca": (
        "Ets un assistent visual d'IA. La teva tasca és descriure imatges EXCLUSIVAMENT en català. "
        "Està totalment prohibit respondre en anglès. Tot el teu text HA D'ESTAR en català."
    ),
}

LOCALIZED_USER_DIRECTIVES: dict[str, str] = {
    "es": "\nIMPORTANTE: Escribe toda la respuesta obligatoriamente y exclusivamente en español. No uses el idioma inglés.",
    "fr": "\nIMPORTANT: Écrivez toute la réponse obligatoirement et exclusivement en français. N'utilisez pas l'anglais.",
    "de": "\nWICHTIG: Schreiben Sie die gesamte Antwort ausschließlich auf Deutsch. Verwenden Sie kein Englisch.",
    "it": "\nIMPORTANTE: Scrivi l'intera risposta esclusivamente in italiano. Non usare l'inglese.",
    "pt": "\nIMPORTANTE: Escreva toda a resposta obrigatoriamente e exclusivamente em português. Não use o inglês.",
    "ca": "\nIMPORTANT: Escriu tota la resposta exclusivament en català. No facis servir l'anglès.",
}

ENGLISH_STOPWORDS = {
    "the", "is", "are", "was", "were", "this", "that", "these", "those",
    "with", "and", "of", "in", "on", "at", "to", "for", "from", "by",
    "an", "shows", "depicts", "image", "picture", "photo", "features",
    "background", "foreground", "there", "has", "have", "can", "see",
    "appears", "holding", "wearing", "standing", "sitting", "looking",
}

SPANISH_STOPWORDS = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "es", "son",
    "era", "eran", "está", "están", "este", "esta", "estos", "estas",
    "con", "y", "de", "en", "para", "por", "imagen", "foto",
    "fotografía", "muestra", "representa", "aparece", "fondo", "primer",
    "plano", "hay", "tiene", "tienen", "puede", "ver", "observa", "observar",
    "sosteniendo", "llevando", "vistiendo", "persona", "personas", "se", "del", "al",
}

FRENCH_STOPWORDS = {
    "le", "la", "les", "un", "une", "des", "est", "sont", "cette", "ce",
    "ces", "avec", "et", "de", "du", "dans", "sur", "pour", "par",
    "image", "photo", "montre", "affiche", "fond", "il", "y", "a",
}

GERMAN_STOPWORDS = {
    "der", "die", "das", "ein", "eine", "einer", "ist", "sind", "mit",
    "und", "von", "in", "auf", "für", "bild", "foto", "zeigt", "hintergrund",
}

ITALIAN_STOPWORDS = {
    "il", "lo", "la", "i", "gli", "le", "un", "uno", "una", "è", "sono",
    "questo", "questa", "con", "e", "di", "in", "su", "per", "immagine",
    "foto", "mostra", "sfondo", "c'è", "ci",
}

PORTUGUESE_STOPWORDS = {
    "o", "a", "os", "as", "um", "uma", "uns", "umas", "é", "são",
    "este", "esta", "com", "e", "de", "do", "da", "em", "no", "na",
    "para", "por", "imagen", "foto", "mostra", "fundo", "há",
}

CATALAN_STOPWORDS = {
    "el", "la", "els", "les", "un", "una", "uns", "unes", "és", "són",
    "aquest", "aquesta", "amb", "i", "de", "del", "en", "per", "imatge",
    "foto", "mostra", "fons", "hi", "ha",
}


def is_text_in_english(text: str, target_lang: str) -> bool:
    """Check if generated response is predominantly in English instead of target language."""
    if not text:
        return False
    clean_target = target_lang.strip().lower()
    if clean_target in ("en", "english"):
        return False

    words = [w.strip(".,;:!?\"'()[]{}«»—-_/\n\t").lower() for w in text.split()]
    words = [w for w in words if w]
    if len(words) < 3:
        return False

    eng_count = sum(1 for w in words if w in ENGLISH_STOPWORDS)

    target_stopwords_map = {
        "es": SPANISH_STOPWORDS,
        "fr": FRENCH_STOPWORDS,
        "de": GERMAN_STOPWORDS,
        "it": ITALIAN_STOPWORDS,
        "pt": PORTUGUESE_STOPWORDS,
        "ca": CATALAN_STOPWORDS,
    }
    target_words = target_stopwords_map.get(clean_target)

    if target_words:
        target_count = sum(1 for w in words if w in target_words)
        if eng_count >= 2 and target_count == 0:
            return True
        if eng_count >= 3 and eng_count > target_count:
            return True
    else:
        if eng_count >= 4 and (eng_count / len(words)) > 0.15:
            return True

    return False


def translate_text_with_ollama(
    text: str,
    target_lang: str,
    ai_config: AIConfig,
) -> Optional[str]:
    """Translate text into target language using Ollama model.

    Args:
        text: Text to translate.
        target_lang: Target language code (e.g. 'es', 'fr').
        ai_config: AI configuration.

    Returns:
        Translated text or None if translation failed.
    """
    if not text.strip() or not ai_config.vision_model:
        return None

    lang_name = get_language_name(target_lang)
    endpoint = f"{ai_config.ollama_url.rstrip('/')}/api/generate"

    prompt = (
        f"Translate the following text into {lang_name}. "
        f"Provide ONLY the direct translation in {lang_name}, without any introductory comments, "
        f"explanations, or surrounding quotes:\n\n{text.strip()}"
    )
    system = (
        f"You are a professional translator. You must translate the user's text into {lang_name}. "
        f"Output exclusively the translation in {lang_name}."
    )

    payload = {
        "model": ai_config.vision_model,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {
            "temperature": 0.2,
        },
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=min(30, ai_config.timeout_seconds)) as resp:
            if resp.status == 200:
                body = json.loads(resp.read().decode("utf-8"))
                translated = str(body.get("response", "")).strip()
                if translated:
                    return translated
    except Exception as exc:
        logger.warning("Failed translating text to %s with Ollama: %s", target_lang, exc)

    return None


def get_language_name(code_or_name: str) -> str:
    """Resolve ISO code or language string to descriptive language name."""
    clean = code_or_name.strip().lower()
    return LANGUAGE_NAMES.get(clean, code_or_name.strip())


class AIError(Exception):
    """Base exception for AI-related errors."""


class AITimeoutError(AIError, TimeoutError):
    """Raised when an AI operation (Ollama or Whisper) exceeds its configured timeout."""


def resolve_ai_model_and_version(model_spec: str, default_model: str = "") -> Tuple[str, str]:
    """Parse a model specification into (model_name, version).

    Args:
        model_spec: Configured model string (e.g. 'llama3.2-vision:11b', 'llava', 'base').
        default_model: Default model name if model_spec is just a size/tag (e.g. 'whisper').

    Returns:
        Tuple of (model_name, version).
    """
    spec = model_spec.strip()
    if not spec:
        return "", ""

    if ":" in spec:
        name, ver = spec.split(":", 1)
        return name.strip(), ver.strip()

    # Whisper model sizes
    whisper_sizes = {"tiny", "base", "small", "medium", "large", "large-v1", "large-v2", "large-v3", "turbo"}
    if default_model == "whisper":
        lower = spec.lower()
        if lower.startswith("whisper-"):
            return "whisper", spec[8:].strip()
        if lower == "whisper":
            return "whisper", "base"
        return "whisper", spec

    if default_model and spec.lower() in whisper_sizes:
        return default_model, spec

    return spec, "latest"


def prepare_image_for_vision(
    image_bytes: bytes,
    min_dimension: int = 5,
    max_dimension: int = 2048,
) -> Optional[bytes]:
    """Prepare and normalize raw image bytes for Ollama vision models.

    - Validates image dimensions (skips tiny/spacer images < min_dimension).
    - Converts RGBA / CMYK / palette / greyscale images to clean RGB JPEG.
    - Resizes excessively large images exceeding max_dimension to preserve memory and speed.
    - Returns None if image is too small or empty.
    - If Pillow cannot open (e.g. mock data or unrecognized format), returns original bytes.
    """
    if not image_bytes:
        return None

    try:
        from PIL import Image

        with Image.open(io.BytesIO(image_bytes)) as img:
            if img.width < min_dimension or img.height < min_dimension:
                logger.debug(
                    "Skipping tiny image (%dx%d) for vision model",
                    img.width,
                    img.height,
                )
                return None

            # Resize if dimensions exceed max_dimension
            orig_w, orig_h = img.size
            if max(orig_w, orig_h) > max_dimension:
                img = img.copy()
                img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

            # Convert to RGB (handling alpha channel with white background)
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                bg = Image.new("RGB", img.size, (255, 255, 255))
                rgba_img = img.convert("RGBA")
                bg.paste(rgba_img, mask=rgba_img.split()[3])
                rgb_img = bg
            elif img.mode != "RGB":
                rgb_img = img.convert("RGB")
            else:
                rgb_img = img

            buf = io.BytesIO()
            rgb_img.save(buf, format="JPEG", quality=90)
            return buf.getvalue()
    except Exception as exc:
        logger.debug("Image normalization skipped (PIL open failed): %s", exc)
        return image_bytes


def _format_ollama_http_error(exc: urllib.error.HTTPError, model_name: str) -> str:
    """Extract detailed error message from Ollama HTTP response and add guidance."""
    detail = ""
    try:
        raw_body = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw_body)
            if isinstance(body, dict) and "error" in body:
                detail = str(body["error"]).strip()
            else:
                detail = raw_body.strip()
        except Exception:
            detail = raw_body.strip()
    except Exception:
        pass

    msg = f"HTTP Error {exc.code}: {exc.reason}"
    if detail:
        msg = f"{msg} - {detail}"

    # Provide targeted hints for common Ollama configuration issues
    lower_detail = detail.lower()
    if exc.code == 400 and ("does not support images" in lower_detail or not detail):
        msg += (
            f"\n[HINT] The model '{model_name}' does not support images/vision in Ollama. "
            "Please configure a multimodal vision model in directory2md.yaml under 'ai.vision_model' "
            "(e.g., 'llama3.2-vision:11b', 'qwen2.5-vl:7b', 'llava:7b', or 'minicpm-v:8b'). "
            "Alternatively, disable AI vision processing by setting 'ai.enabled: false'."
        )
    elif exc.code == 404:
        msg += (
            f"\n[HINT] The model '{model_name}' was not found in Ollama. "
            f"You may need to pull it first using: 'ollama pull {model_name}'."
        )

    return msg


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

    prepared_bytes = prepare_image_for_vision(image_bytes)
    if prepared_bytes is None:
        logger.debug("Image skipped for vision model (empty or too small)")
        return None

    b64_image = base64.b64encode(prepared_bytes).decode("ascii")
    endpoint = f"{ai_config.ollama_url.rstrip('/')}/api/generate"

    full_prompt = prompt
    system_prompt = None

    if ai_config.language and "verbatim" not in prompt.lower():
        lang_code = ai_config.language.strip().lower()
        lang_name = get_language_name(ai_config.language)

        if (
            "comprehensive and detailed description of the contents and context of this image" in prompt.lower()
            or "describe" in prompt.lower()
            or "description" in prompt.lower()
        ):
            localized = LOCALIZED_IMAGE_DESCRIPTION_PROMPTS.get(lang_code)
            if localized:
                full_prompt = localized

        user_directive = LOCALIZED_USER_DIRECTIVES.get(
            lang_code,
            f"\nIMPORTANT: Respond entirely in {lang_name}. The entire description must be written in {lang_name}."
        )

        full_prompt = (
            f"{full_prompt}\n"
            f"Please respond in language: {ai_config.language}."
            f"{user_directive}"
        )

        if lang_code not in ("en", "english"):
            system_prompt = LOCALIZED_VISION_SYSTEM_PROMPTS.get(
                lang_code,
                f"You are an expert visual AI assistant. You must describe images EXCLUSIVELY in {lang_name}. Never respond in English. All output must be in {lang_name}."
            )

    payload = {
        "model": ai_config.vision_model,
        "prompt": full_prompt,
        "images": [b64_image],
        "stream": False,
    }
    if system_prompt:
        payload["system"] = system_prompt

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
                response_text = str(body.get("response", "")).strip()
                if (
                    response_text
                    and ai_config.language
                    and "verbatim" not in prompt.lower()
                    and ai_config.language.strip().lower() not in ("en", "english")
                ):
                    target_code = ai_config.language.strip().lower()
                    if is_text_in_english(response_text, target_code):
                        target_name = get_language_name(ai_config.language)
                        logger.info(
                            "Ollama vision model generated response in English instead of %s; translating automatically...",
                            target_name,
                        )
                        translated = translate_text_with_ollama(response_text, target_code, ai_config)
                        if translated:
                            return translated
                return response_text
            raise AIError(f"Ollama vision query returned HTTP {resp.status}")
    except urllib.error.HTTPError as exc:
        if exc.code == 504:
            logger.warning(
                "Ollama vision query timed out after %ds for model '%s'",
                ai_config.timeout_seconds,
                ai_config.vision_model,
            )
            raise AITimeoutError(
                f"Ollama vision query timed out after {ai_config.timeout_seconds}s"
            ) from exc
        err_msg = _format_ollama_http_error(exc, ai_config.vision_model)
        logger.warning(
            "Ollama vision query failed for model '%s': %s",
            ai_config.vision_model,
            err_msg,
        )
        raise AIError(
            f"Ollama vision query failed for model '{ai_config.vision_model}': {err_msg}"
        ) from exc
    except (TimeoutError, urllib.error.URLError) as exc:
        if isinstance(exc, TimeoutError) or "timed out" in str(exc).lower():
            logger.warning(
                "Ollama vision query timed out after %ds for model '%s'",
                ai_config.timeout_seconds,
                ai_config.vision_model,
            )
            raise AITimeoutError(
                f"Ollama vision query timed out after {ai_config.timeout_seconds}s"
            ) from exc
        logger.warning(
            "Ollama vision query failed for model '%s': %s",
            ai_config.vision_model,
            exc,
        )
        raise AIError(
            f"Ollama vision query failed for model '{ai_config.vision_model}': {exc}"
        ) from exc
    except Exception as exc:
        if "timed out" in str(exc).lower():
            logger.warning(
                "Ollama vision query timed out after %ds for model '%s'",
                ai_config.timeout_seconds,
                ai_config.vision_model,
            )
            raise AITimeoutError(
                f"Ollama vision query timed out after {ai_config.timeout_seconds}s"
            ) from exc
        logger.warning(
            "Ollama vision query failed for model '%s': %s",
            ai_config.vision_model,
            exc,
        )
        raise AIError(
            f"Ollama vision query failed for model '{ai_config.vision_model}': {exc}"
        ) from exc


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

    valid_images: List[bytes] = []
    for b in images_bytes:
        prep = prepare_image_for_vision(b)
        if prep:
            valid_images.append(prep)

    if not valid_images:
        return None

    b64_images = [base64.b64encode(b).decode("ascii") for b in valid_images]
    endpoint = f"{ai_config.ollama_url.rstrip('/')}/api/generate"

    full_prompt = prompt
    system_prompt = None

    if ai_config.language:
        lang_code = ai_config.language.strip().lower()
        lang_name = get_language_name(ai_config.language)

        if (
            "analyze these extracted video keyframes" in prompt.lower()
            or "summarize" in prompt.lower()
        ):
            localized = LOCALIZED_VIDEO_SUMMARY_PROMPTS.get(lang_code)
            if localized:
                full_prompt = localized

        user_directive = LOCALIZED_USER_DIRECTIVES.get(
            lang_code,
            f"\nIMPORTANT: Respond entirely in {lang_name}. The entire summary must be written in {lang_name}."
        )

        full_prompt = (
            f"{full_prompt}\n"
            f"Please respond in language: {ai_config.language}."
            f"{user_directive}"
        )

        if lang_code not in ("en", "english"):
            system_prompt = LOCALIZED_VISION_SYSTEM_PROMPTS.get(
                lang_code,
                f"You are an expert visual AI assistant. You must summarize video keyframes EXCLUSIVELY in {lang_name}. Never respond in English. All output must be in {lang_name}."
            )

    payload = {
        "model": ai_config.vision_model,
        "prompt": full_prompt,
        "images": b64_images,
        "stream": False,
    }
    if system_prompt:
        payload["system"] = system_prompt

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
                response_text = str(body.get("response", "")).strip()
                if (
                    response_text
                    and ai_config.language
                    and ai_config.language.strip().lower() not in ("en", "english")
                ):
                    target_code = ai_config.language.strip().lower()
                    if is_text_in_english(response_text, target_code):
                        target_name = get_language_name(ai_config.language)
                        logger.info(
                            "Ollama video summary generated response in English instead of %s; translating automatically...",
                            target_name,
                        )
                        translated = translate_text_with_ollama(response_text, target_code, ai_config)
                        if translated:
                            return translated
                return response_text
            raise AIError(f"Ollama multi-image vision query returned HTTP {resp.status}")
    except urllib.error.HTTPError as exc:
        if exc.code == 504:
            logger.warning(
                "Ollama multi-image vision query timed out after %ds for model '%s'",
                ai_config.timeout_seconds,
                ai_config.vision_model,
            )
            raise AITimeoutError(
                f"Ollama multi-image vision query timed out after {ai_config.timeout_seconds}s"
            ) from exc
        err_msg = _format_ollama_http_error(exc, ai_config.vision_model)
        logger.warning(
            "Ollama multi-image vision query failed for model '%s': %s",
            ai_config.vision_model,
            err_msg,
        )
        raise AIError(
            f"Ollama multi-image vision query failed for model '{ai_config.vision_model}': {err_msg}"
        ) from exc
    except (TimeoutError, urllib.error.URLError) as exc:
        if isinstance(exc, TimeoutError) or "timed out" in str(exc).lower():
            logger.warning("Ollama multi-image vision query timed out after %ds", ai_config.timeout_seconds)
            raise AITimeoutError(f"Ollama multi-image vision query timed out after {ai_config.timeout_seconds}s") from exc
        logger.warning("Ollama multi-image vision query failed: %s", exc)
        raise AIError(f"Ollama multi-image vision query failed: {exc}") from exc
    except Exception as exc:
        if "timed out" in str(exc).lower():
            logger.warning("Ollama multi-image vision query timed out after %ds", ai_config.timeout_seconds)
            raise AITimeoutError(f"Ollama multi-image vision query timed out after {ai_config.timeout_seconds}s") from exc
        logger.warning("Ollama multi-image vision query failed: %s", exc)
        raise AIError(f"Ollama multi-image vision query failed: {exc}") from exc


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
        if ai_config and ai_config.enabled and ai_config.audio_model:
            raise AIError("Whisper CLI is not installed or not found in PATH")
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
            return ""
    except subprocess.TimeoutExpired as exc:
        logger.warning("Whisper transcription timed out for '%s' after %ss", audio_path, exc.timeout)
        raise AITimeoutError(f"Whisper audio transcription timed out after {exc.timeout}s") from exc
    except Exception as exc:
        if "timed out" in str(exc).lower():
            raise AITimeoutError(f"Whisper audio transcription timed out: {exc}") from exc
        logger.warning("Whisper transcription failed for '%s': %s", audio_path, exc)
        raise AIError(f"Whisper audio transcription failed for '{audio_path}': {exc}") from exc
