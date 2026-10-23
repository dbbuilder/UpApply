"""Voice kit: the vendored bundle loader and scripts/sync_voice_kit.py."""
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

from app.services.generation.voice import load_voice

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "sync_voice_kit.py"
spec = importlib.util.spec_from_file_location("sync_voice_kit", SCRIPT)
sync_voice_kit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_voice_kit)


def test_load_voice_returns_the_bundle_for_a_mapped_email():
    voice = load_voice("Chris@ServiceVision.net ")
    assert voice is not None
    assert voice["writer"] == "chris"
    assert voice["kit_version"].startswith("v")
    assert {"persona", "house_style", "rules", "registers", "exemplars"} <= set(voice)
    assert voice["rules"]["closing"]["call_offer"]
    assert "sales-proposal" in voice["registers"]


def test_load_voice_returns_none_without_a_mapping():
    assert load_voice("someone@example.com") is None
    assert load_voice("") is None
    assert load_voice(None) is None


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def test_sync_copies_the_bundle_and_stamps_the_kit_version(tmp_path):
    kit = tmp_path / "kit"
    (kit / "build").mkdir(parents=True)
    (kit / "build" / "ana.json").write_text(json.dumps({"writer": "ana", "persona": "Calm."}))
    _git(kit, "init", "-q")
    _git(kit, "add", ".")
    _git(kit, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", "kit")
    _git(kit, "tag", "v9.9.9")

    out = tmp_path / "voice"
    target = sync_voice_kit.sync(kit, "ana", out)

    assert target == out / "ana.json"
    data = json.loads(target.read_text())
    assert data["writer"] == "ana" and data["persona"] == "Calm."
    assert data["kit_version"].startswith("v9.9.9 (")


def test_sync_fails_cleanly_without_a_built_bundle(tmp_path):
    with pytest.raises(FileNotFoundError, match="nobody.json"):
        sync_voice_kit.sync(tmp_path, "nobody", tmp_path / "voice")
