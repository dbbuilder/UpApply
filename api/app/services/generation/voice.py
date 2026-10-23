"""A writer's voice from the vendored ServiceVision voice kit (api/app/voice/, synced by
scripts/sync_voice_kit.py). Voice only: facts still come from the approved facts store."""
import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

VOICE_DIR = Path(__file__).resolve().parents[2] / "voice"


@lru_cache(maxsize=1)
def _index() -> dict:
    try:
        data = json.loads((VOICE_DIR / "index.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k).strip().lower(): str(v) for k, v in data.items()}


@lru_cache(maxsize=32)
def _bundle(writer: str) -> Optional[dict]:
    try:
        return json.loads((VOICE_DIR / f"{writer}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_voice(email: Optional[str]) -> Optional[dict]:
    """The kit bundle for this user, or None when the email has no mapping or no file."""
    writer = _index().get((email or "").strip().lower())
    return _bundle(writer) if writer else None
