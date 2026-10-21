"""Read ``.fcproj`` files (plain JSON) without starting FilmCraft.

The project file stores the authoritative media paths that
``sequence.inspect`` does not expose:

    project.items["12"].kind.Media.media.File.path  ->  "/abs/video.mp4"

Used by the reverse sync (``CLIPS file:``) and by ``generate`` (which
pipeline video to run).
"""
from __future__ import annotations

import json
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"}


def load_fcproj(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def fcproj_media_paths(fcproj: dict) -> dict[int, str]:
    """``item id -> absolute media path`` for every Media item."""
    out: dict[int, str] = {}
    root = fcproj.get("project") or fcproj
    for key, item in (root.get("items") or {}).items():
        kind = item.get("kind") or {}
        media = (kind.get("Media") or {}).get("media") or {}
        file_ref = media.get("File") or {}
        path = file_ref.get("path")
        if path:
            try:
                item_id = int(item.get("id", key))
            except (TypeError, ValueError):
                continue
            out[item_id] = path
    return out


def project_video_paths(fcproj: dict) -> list[str]:
    """Distinct video files referenced by the project, first-use order."""
    seen: list[str] = []
    for path in fcproj_media_paths(fcproj).values():
        if Path(path).suffix.lower() not in VIDEO_EXTS:
            continue
        if path not in seen:
            seen.append(path)
    return seen
