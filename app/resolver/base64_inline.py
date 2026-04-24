"""data:audio/...;base64,... inline payload resolver."""
from __future__ import annotations

import base64
import re
import uuid as uuidlib
from pathlib import Path

from app.config import Settings
from app.resolver.types import ResolvedSource

_DATA_URI_RE = re.compile(
    r"^data:(?P<mime>[\w/\-.+]+)?(?:;charset=[^;]+)?;base64,(?P<payload>[A-Za-z0-9+/=\s]+)$",
    re.IGNORECASE,
)


async def try_base64(
    source: str, *, settings: Settings, work_dir: Path
) -> ResolvedSource | None:
    m = _DATA_URI_RE.match(source.strip())
    if not m:
        return None
    mime = (m.group("mime") or "audio/mpeg").lower()
    raw = "".join(m.group("payload").split())
    payload = base64.b64decode(raw, validate=True)
    if len(payload) > settings.inline_base64_max_bytes:
        raise ValueError(
            f"inline base64 payload exceeds the {settings.inline_base64_max_bytes} byte limit; "
            "use POST /upload instead"
        )
    from app.storage.files import upload_path

    uuid = str(uuidlib.uuid4())
    target = upload_path(settings.data_dir, uuid, mime)
    work_dir.mkdir(parents=True, exist_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return ResolvedSource(
        source_type="base64",
        audio_path=target,
        content_type=mime,
        cleanup_paths=[target],
    )
