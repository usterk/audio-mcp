"""Piper TTS adapter — wraps the piper binary + ffmpeg for format conversion."""
from __future__ import annotations

import asyncio
import subprocess
import tempfile
import wave
from pathlib import Path

from app.backends.tts.base import Format, TTSResult

DEFAULT_VOICE = "gosia-medium"
_VOICE_FILE: dict[str, str] = {
    "gosia-medium": "pl_PL-gosia-medium.onnx",
}


def _wav_duration(path: str) -> float:
    wf = wave.open(path, "rb")  # noqa: SIM115
    try:
        return wf.getnframes() / float(wf.getframerate())
    finally:
        wf.close()


class PiperBackend:
    name = "piper"
    default_voice = DEFAULT_VOICE
    normalizes_own_text = False

    def __init__(self, *, binary: str, voice_dir: Path) -> None:
        self._binary = binary
        self._voice_dir = voice_dir

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
        _ = model, style  # piper has no model dimension or style prompt
        voice_id = voice or self.default_voice
        voice_file = self._voice_dir / _VOICE_FILE.get(voice_id, f"{voice_id}.onnx")
        if not voice_file.exists():
            raise ValueError(f"piper voice not installed: {voice_id} (expected {voice_file})")

        def _run() -> TTSResult:
            output_path.parent.mkdir(parents=True, exist_ok=True)

            if format == "wav":
                # write directly to output_path
                subprocess.run(
                    [
                        self._binary,
                        "--model",
                        str(voice_file),
                        "--output_file",
                        str(output_path),
                    ],
                    input=text.encode("utf-8"),
                    capture_output=True,
                    check=True,
                )
                duration = _wav_duration(str(output_path))
            else:
                with tempfile.TemporaryDirectory(prefix="piper_") as tmp:
                    wav_path = Path(tmp) / "out.wav"
                    subprocess.run(
                        [
                            self._binary,
                            "--model",
                            str(voice_file),
                            "--output_file",
                            str(wav_path),
                        ],
                        input=text.encode("utf-8"),
                        capture_output=True,
                        check=True,
                    )
                    duration = _wav_duration(str(wav_path))

                    codec = {"mp3": ("libmp3lame", "mp3"), "opus": ("libopus", "opus")}[format]
                    subprocess.run(
                        [
                            "ffmpeg",
                            "-y",
                            "-loglevel",
                            "error",
                            "-i",
                            str(wav_path),
                            "-codec:a",
                            codec[0],
                            str(output_path),
                        ],
                        check=True,
                    )
            size = output_path.stat().st_size
            return TTSResult(
                audio_path=output_path,
                duration_sec=duration,
                bytes=size,
                voice=voice_id,
                backend="piper",
                format=format,
            )

        return await asyncio.to_thread(_run)
