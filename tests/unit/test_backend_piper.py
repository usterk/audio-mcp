"""Piper backend tests (mocked subprocess)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.backends.tts.piper import PiperBackend


def _fake_wave_info(seconds: float = 1.5):
    wave = MagicMock()
    wave.getnframes.return_value = int(22050 * seconds)
    wave.getframerate.return_value = 22050
    return wave


@pytest.mark.asyncio
async def test_invokes_piper_binary(tmp_path: Path) -> None:
    out = tmp_path / "out.wav"
    voice_dir = tmp_path / "voices"
    voice_dir.mkdir()
    (voice_dir / "pl_PL-gosia-medium.onnx").write_bytes(b"stub")
    (voice_dir / "pl_PL-gosia-medium.onnx.json").write_bytes(b"{}")

    captured = {}

    def fake_run(args, *, check, input, capture_output):
        captured["args"] = args
        out.write_bytes(b"RIFFxxxxWAVE")
        class R:
            stdout = b""
            stderr = b""
        return R()

    with patch("app.backends.tts.piper.subprocess.run", side_effect=fake_run), patch(
        "app.backends.tts.piper.wave.open", return_value=_fake_wave_info(0.5)
    ):
        backend = PiperBackend(binary="piper", voice_dir=voice_dir)
        result = await backend.synthesize(
            "Cześć",
            voice="gosia-medium",
            model="",
            output_path=out,
            format="wav",
            style="",
        )

    assert "piper" in captured["args"][0]
    assert "--model" in captured["args"]
    assert out.exists()
    assert result.voice == "gosia-medium"
    assert result.duration_sec == pytest.approx(0.5, abs=0.05)


@pytest.mark.asyncio
async def test_mp3_output_converts_via_ffmpeg(tmp_path: Path) -> None:
    out = tmp_path / "out.mp3"
    voice_dir = tmp_path / "voices"
    voice_dir.mkdir()
    (voice_dir / "pl_PL-gosia-medium.onnx").write_bytes(b"stub")
    (voice_dir / "pl_PL-gosia-medium.onnx.json").write_bytes(b"{}")

    calls: list[list[str]] = []

    def fake_run(args, *, check, input=None, capture_output=False):
        calls.append(list(args))
        if args[0].endswith("piper"):
            (tmp_path / "piper.wav").write_bytes(b"RIFFxxxxWAVE")
        else:
            out.write_bytes(b"\xff\xfbxxxx")

        class R:
            stdout = b""
            stderr = b""
        return R()

    with patch("app.backends.tts.piper.subprocess.run", side_effect=fake_run), patch(
        "app.backends.tts.piper.wave.open", return_value=_fake_wave_info(1.0)
    ):
        backend = PiperBackend(binary="piper", voice_dir=voice_dir)
        result = await backend.synthesize(
            "Cześć",
            voice="gosia-medium",
            model="",
            output_path=out,
            format="mp3",
            style="",
        )

    assert any("ffmpeg" in " ".join(c) for c in calls)
    assert result.format == "mp3"
    assert out.exists()
