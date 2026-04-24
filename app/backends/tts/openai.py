"""OpenAI gpt-4o-mini-tts adapter."""
from __future__ import annotations

from pathlib import Path

from openai import AsyncOpenAI

from app.backends.tts.base import Format, TTSResult

DEFAULT_VOICE = "nova"
DEFAULT_MODEL = "gpt-4o-mini-tts"


class OpenAIBackend:
    name = "openai"
    default_voice = DEFAULT_VOICE
    normalizes_own_text = True  # handles acronyms + punctuation well on its own

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
        voice_id = voice or self.default_voice
        model_id = model or DEFAULT_MODEL
        client = AsyncOpenAI(api_key=self._api_key)

        kwargs: dict = {
            "model": model_id,
            "voice": voice_id,
            "input": text,
            "response_format": format,
        }
        if style:
            kwargs["instructions"] = style

        output_path.parent.mkdir(parents=True, exist_ok=True)
        async with await client.audio.speech.with_streaming_response.create(**kwargs) as stream:
            await stream.stream_to_file(str(output_path))

        return TTSResult(
            audio_path=output_path,
            duration_sec=0.0,
            bytes=output_path.stat().st_size,
            voice=voice_id,
            backend="openai",
            model=model_id,
            format=format,
        )
