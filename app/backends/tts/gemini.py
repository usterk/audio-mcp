"""Gemini 2.5 Flash TTS adapter — REST via httpx, PCM→WAV, ffmpeg for mp3/opus."""
from __future__ import annotations

import base64
import contextlib
import struct
import subprocess
import tempfile
from pathlib import Path

import httpx

from app.backends.tts.base import Format, TTSResult

DEFAULT_VOICE = "Charon"
DEFAULT_MODEL = "gemini-2.5-flash-preview-tts"
_GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"


def _pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 24000) -> bytes:
    """Wrap raw 16-bit mono PCM bytes in a WAV container."""
    channels = 1
    bits_per_sample = 16
    data_size = len(pcm_bytes)
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,        # fmt chunk size
        1,         # PCM format
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        data_size,
    )
    return header + pcm_bytes


class GeminiBackend:
    name = "gemini"
    default_voice = DEFAULT_VOICE
    normalizes_own_text = True  # capable model — handles acronyms and punctuation itself

    def __init__(self, *, api_key: str) -> None:
        self._api_key = api_key

    async def synthesize(
        self,
        text: str,
        *,
        voice: str,
        model: str,
        output_path: Path,
        format: Format,
        style: str,
    ) -> TTSResult:
        _ = style  # Gemini TTS has no style/instruction parameter
        voice_id = voice or self.default_voice
        model_id = model or DEFAULT_MODEL

        url = f"{_GEMINI_API_BASE}/models/{model_id}:generateContent?key={self._api_key}"
        body = {
            "contents": [{"parts": [{"text": text}], "role": "user"}],
            "generationConfig": {
                "response_modalities": ["AUDIO"],
                "speech_config": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {"voiceName": voice_id}
                    }
                },
            },
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=body)
        response.raise_for_status()

        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise ValueError("No audio in Gemini TTS response: missing candidates")
        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            raise ValueError("No audio in Gemini TTS response: missing parts")

        inline = parts[0].get("inlineData", {})
        audio_b64 = inline.get("data", "")
        raw_mime = inline.get("mimeType", "")

        if not audio_b64:
            raise ValueError("No audio in Gemini TTS response: empty data field")

        pcm_bytes = base64.b64decode(audio_b64)

        # Extract sample rate from MIME type (e.g. "audio/L16;rate=24000")
        sample_rate = 24000
        if "rate=" in raw_mime:
            with contextlib.suppress(ValueError, IndexError):
                sample_rate = int(raw_mime.split("rate=")[1].split(";")[0])

        duration_sec = len(pcm_bytes) / (sample_rate * 2)  # 16-bit = 2 bytes/sample, mono
        wav_bytes = _pcm_to_wav(pcm_bytes, sample_rate=sample_rate)

        output_path.parent.mkdir(parents=True, exist_ok=True)

        if format == "wav":
            output_path.write_bytes(wav_bytes)
        else:
            with tempfile.TemporaryDirectory(prefix="gemini_tts_") as tmp:
                wav_path = Path(tmp) / "out.wav"
                wav_path.write_bytes(wav_bytes)
                codec = {"mp3": "libmp3lame", "opus": "libopus"}[format]
                subprocess.run(
                    [
                        "ffmpeg", "-y", "-loglevel", "error",
                        "-i", str(wav_path),
                        "-codec:a", codec,
                        str(output_path),
                    ],
                    check=True,
                )

        return TTSResult(
            audio_path=output_path,
            duration_sec=duration_sec,
            bytes=output_path.stat().st_size,
            voice=voice_id,
            backend="gemini",
            model=model_id,
            format=format,
        )
