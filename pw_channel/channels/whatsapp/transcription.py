import httpx
import logging
from typing import Optional
from pw_channel.channels.whatsapp.settings import settings

logger = logging.getLogger(__name__)

WHISPER_URL = "https://api.openai.com/v1/audio/transcriptions"


async def transcribe_audio(audio_bytes: bytes, mime_type: str = "audio/ogg") -> Optional[str]:
    if not settings.openai_api_key:
        logger.error("[TRANSCRIPTION] OPENAI_API_KEY not set")
        return None

    ext = _ext_from_mime(mime_type)
    filename = f"audio.{ext}"

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                WHISPER_URL,
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                files={"file": (filename, audio_bytes, mime_type)},
                data={"model": "whisper-1","prompt":"Transcribe naturally in the language spoken by the user. If Hindi is spoken, use Devanagari script. If English is spoken, use English Latin script. Preserve the original meaning and do not translate in anny other language other than hindi or english"},
            )
            response.raise_for_status()
            text = response.json().get("text", "").strip()
            logger.info(f"[TRANSCRIPTION] Whisper result: {text!r}")
            return text or None
    except Exception as e:
        logger.error(f"[TRANSCRIPTION] Whisper API failed: {e}")
        return None


async def download_and_transcribe(
    url: str,
    headers: Optional[dict] = None,
    auth: Optional[tuple] = None,
) -> Optional[str]:
    try:
        async with httpx.AsyncClient(timeout=60.0, auth=auth) as client:
            response = await client.get(url, headers=headers or {}, follow_redirects=True)
            response.raise_for_status()
            audio_bytes = response.content
            mime_type = response.headers.get("content-type", "audio/ogg").split(";")[0]
    except Exception as e:
        logger.error(f"[TRANSCRIPTION] Audio download failed from {url}: {e}")
        return None

    return await transcribe_audio(audio_bytes, mime_type)


def _ext_from_mime(mime_type: str) -> str:
    mapping = {
        "audio/ogg": "ogg",
        "audio/mpeg": "mp3",
        "audio/mp4": "mp4",
        "audio/wav": "wav",
        "audio/webm": "webm",
        "audio/aac": "aac",
        "audio/amr": "amr",
    }
    return mapping.get(mime_type, "ogg")
