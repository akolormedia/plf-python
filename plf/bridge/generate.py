"""Generate PLFs from a FilmCraft project: run the pipeline over its clips.

FC-A third leg — from a timeline (or raw material already imported into a
project), collect the media the project references and dispatch the
generation pipeline over each clip, writing one ``.raw.plf`` next to every
video (the same contract as Fase G's Generate tab and ``pipeline.batch``).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from .fcproj import load_fcproj, project_video_paths

DEFAULT_PIPELINE_URL = "http://127.0.0.1:8765"


def _post_to_pipeline(pipeline_url: str) -> Callable[[str, dict], str]:
    import httpx

    url = pipeline_url.rstrip("/") + "/generate"

    def poster(video_path: str, context: dict) -> str:
        r = httpx.post(
            url, json={"video_path": video_path, "context": context}, timeout=7200
        )
        if r.status_code != 200:
            raise RuntimeError(f"pipeline HTTP {r.status_code}: {r.text[:600]}")
        return r.text

    return poster


def generate_plfs(
    project: str | Path,
    context: dict | None = None,
    pipeline_url: str | None = None,
    poster: Callable[[str, dict], str] | None = None,
    skip_existing: bool = False,
) -> list[dict]:
    """Run the pipeline over every video of ``project``.

    Returns one result dict per video: ``{"video", "out", "state", "error"}``
    with state ``done`` | ``error`` | ``skipped``. ``poster`` is injectable
    for tests; by default it POSTs to the pipeline service.
    """
    context = context or {}
    videos = project_video_paths(load_fcproj(project))
    if poster is None:
        url = pipeline_url or os.environ.get("PLF_PIPELINE_URL", DEFAULT_PIPELINE_URL)
        poster = _post_to_pipeline(url)

    results: list[dict] = []
    for video in videos:
        out = str(Path(video).with_suffix(".raw.plf"))
        entry = {"video": video, "out": out, "state": "done", "error": None}
        if skip_existing and Path(out).is_file():
            entry["state"] = "skipped"
            results.append(entry)
            continue
        try:
            text = poster(video, context)
            Path(out).write_text(text, encoding="utf-8")
        except Exception as e:
            entry["state"] = "error"
            entry["error"] = str(e)
        results.append(entry)
    return results
