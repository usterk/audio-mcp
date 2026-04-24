"""Google Cloud TTS Standard adapter."""
from __future__ import annotations

import asyncio
import wave
from pathlib import Path

from google.cloud import texttospeech as tts  # type: ignore[import-untyped]

from app.backends.tts.base import Format, TTSResult

DEFAULT_VOICE = "pl-PL-Standard-A"


def _language_of(voice: str) -> str:
    # voice ids are formed like "pl-PL-Standard-A"; the language code is the first two segments.
    parts = voice.split("-")
    return "-".join(parts[:2]) if len(parts) >= 2 else "en-US"


class GCloudBackend:
    name = "gcloud"
    default_voice = DEFAULT_VOICE
    normalizes_own_text = False

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
        _ = model, style
        voice_id = voice or self.default_voice

        def _run() -> TTSResult:
            client = tts.TextToSpeechClient()
            encoding = {
                "mp3": tts.AudioEncoding.MP3,
                "wav": tts.AudioEncoding.LINEAR16,
                "opus": tts.AudioEncoding.OGG_OPUS,
            }[format]
            audio_cfg = tts.AudioConfig(audio_encoding=encoding)
            voice_cfg = tts.VoiceSelectionParams(
                language_code=_language_of(voice_id),
                name=voice_id,
            )
            response = client.synthesize_speech(
                input=tts.SynthesisInput(text=text),
                voice=voice_cfg,
                audio_config=audio_cfg,
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(response.audio_content)
            duration = _audio_duration(output_path, format)
            return TTSResult(
                audio_path=output_path,
                duration_sec=duration,
                bytes=len(response.audio_content),
                voice=voice_id,
                backend="gcloud",
                format=format,
            )

        return await asyncio.to_thread(_run)


def _audio_duration(path: Path, format: Format) -> float:
    if format == "wav":
        try:
            wf = wave.open(str(path), "rb")  # noqa: SIM115
            try:
                return wf.getnframes() / float(wf.getframerate())
            finally:
                wf.close()
        except Exception:
            return 0.0
    return 0.0
