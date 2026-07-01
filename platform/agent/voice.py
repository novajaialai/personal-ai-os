import os
from pathlib import Path

import httpx

_VOICE_CHOICE_FILE = Path("/state/voice_choice.txt")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # "Rachel", a stock voice
# 0.7 = slowest ElevenLabs allows, 1.2 = fastest, 1.0 = default. Jake found the
# default too fast; slowed down. Override with ELEVENLABS_SPEED if needed.
ELEVENLABS_SPEED = float(os.getenv("ELEVENLABS_SPEED", "0.85"))

# A handful of ElevenLabs' well-known premade voices, for the /voice-picker page —
# lets Jake actually hear and choose rather than guess from a name.
STOCK_VOICES = {
    "Adam": "pNInz6obpgDQGcFmaJgB",
    "Antoni": "ErXwobaYiN019PkySvjV",
    "Arnold": "VR6AewLTigWG4xSOukaG",
    "Bella": "EXAVITQu4vr4xnSDxMaL",
    "Josh": "TxGEqnHWrfWFTfGW9XjX",
    "Sam": "yoZ06aMxZJJ28mfd3POQ",
    "Rachel (current default)": "21m00Tcm4TlvDq8ikWAM",
}


class VoiceNotConfigured(RuntimeError):
    pass


def current_voice_id() -> str:
    """Jake's saved pick from /voice-picker, if any, else the env default."""
    if _VOICE_CHOICE_FILE.exists():
        saved = _VOICE_CHOICE_FILE.read_text().strip()
        if saved:
            return saved
    return ELEVENLABS_VOICE_ID


def set_voice_id(voice_id: str) -> None:
    _VOICE_CHOICE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _VOICE_CHOICE_FILE.write_text(voice_id)


def transcribe(audio_bytes: bytes, filename: str = "audio.webm") -> str:
    """Speech-to-text via Groq's hosted Whisper (streaming API, per Phase 5 design)."""
    if not GROQ_API_KEY:
        raise VoiceNotConfigured("GROQ_API_KEY not set")
    resp = httpx.post(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
        files={"file": (filename, audio_bytes)},
        data={"model": "whisper-large-v3"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["text"]


def synthesize(text: str, voice_id: str | None = None) -> bytes:
    """Text-to-speech via ElevenLabs. Returns MP3 bytes."""
    if not ELEVENLABS_API_KEY:
        raise VoiceNotConfigured("ELEVENLABS_API_KEY not set")
    resp = httpx.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id or current_voice_id()}",
        headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"},
        json={
            "text": text,
            "model_id": "eleven_turbo_v2_5",
            "voice_settings": {"speed": ELEVENLABS_SPEED, "stability": 0.5, "similarity_boost": 0.75},
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.content
