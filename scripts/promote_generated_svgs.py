#!/usr/bin/env python3
"""Promote only healthy generated SVGs, preserving last-known-good files."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


EXPECTED = [
    "userstats.svg",
    "streak.svg",
    "activity.svg",
    "pin-rns-llm.svg",
    "pin-human-attributes.svg",
    "pin-raman.svg",
    "pin-ros-autorace.svg",
    "pin-sound-detector.svg",
    "pin-ai-agents.svg",
]

BAD_MARKERS = (
    "something went wrong",
    "api rate limit",
    "error fetching",
    "error:",
    "could not resolve",
)


def healthy_svg(path: Path) -> bool:
    if not path.exists() or path.stat().st_size < 100:
        return False

    text = path.read_text(encoding="utf-8", errors="ignore")
    lowered = text.lower()

    if "<svg" not in lowered or "</svg>" not in lowered:
        return False

    return not any(marker in lowered for marker in BAD_MARKERS)


def main():
    if len(sys.argv) != 3:
        raise SystemExit("Usage: promote_generated_svgs.py GENERATED_DIR DEST_DIR")

    generated = Path(sys.argv[1])
    dest = Path(sys.argv[2])
    dest.mkdir(parents=True, exist_ok=True)

    promoted = 0
    preserved = 0

    for filename in EXPECTED:
        source = generated / filename
        target = dest / filename

        if healthy_svg(source):
            shutil.copy2(source, target)
            print(f"PROMOTED  {filename}")
            promoted += 1
        elif target.exists():
            print(f"PRESERVED {filename} (new generation unavailable/invalid)")
            preserved += 1
        else:
            print(f"MISSING   {filename}")

    print(f"Done: promoted={promoted}, preserved={preserved}")


if __name__ == "__main__":
    main()
