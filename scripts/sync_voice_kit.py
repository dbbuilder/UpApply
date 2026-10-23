#!/usr/bin/env python3
"""
Vendor a writer's voice bundle from the ServiceVision voice kit (dbbuilder-org/sv-writing-style).

Copies <kit>/build/<writer>.json to api/app/voice/<writer>.json and stamps the kit's git tag and
commit into it as "kit_version". The kit holds voice only, never facts.

Usage:
    python scripts/sync_voice_kit.py [--writer chris] [--kit /Users/admin/dev2/sv/writing-style]

Changing the voice: update the kit, tag it, re-run this script, open a PR with the new JSON.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

DEFAULT_KIT = "/Users/admin/dev2/sv/writing-style"
VOICE_DIR = Path(__file__).resolve().parents[1] / "api" / "app" / "voice"


def _git(kit: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(kit), *args], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else ""


def kit_version(kit: Path) -> str:
    """'v0.1.0 (7877e119f31b)' on a tagged commit; the nearest description otherwise."""
    commit = _git(kit, "rev-parse", "HEAD")
    if not commit:
        return "unknown"
    tag = _git(kit, "describe", "--tags", "--always", "--dirty")
    return f"{tag} ({commit[:12]})"


def sync(kit: Path, writer: str, out_dir: Path = VOICE_DIR) -> Path:
    source = kit / "build" / f"{writer}.json"
    if not source.is_file():
        raise FileNotFoundError(f"{source} not found; build it in the kit first (python3 tools/build.py {writer})")
    bundle = json.loads(source.read_text(encoding="utf-8"))
    bundle["kit_version"] = kit_version(kit)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{writer}.json"
    target.write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--writer", default="chris")
    parser.add_argument("--kit", default=DEFAULT_KIT)
    args = parser.parse_args()
    try:
        target = sync(Path(args.kit), args.writer)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"Wrote {target} ({json.loads(target.read_text())['kit_version']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
