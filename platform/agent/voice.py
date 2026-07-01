import os

import httpx

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # "Rachel", a stock voice


class VoiceNotConfigured(RuntimeError):
    pass


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


def synthesize(text: str) -> bytes:
    """Text-to-speech via ElevenLabs. Returns MP3 bytes."""
    if not ELEVENLABS_API_KEY:
        raise VoiceNotConfigured("ELEVENLABS_API_KEY not set")
    resp = httpx.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}",
        headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"},
        json={"text": text, "model_id": "eleven_turbo_v2_5"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.content
