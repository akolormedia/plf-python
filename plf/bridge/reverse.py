"""Reverse sync: FilmCraft sequence -> PLF.

FC-A chose ``sequence.inspect`` over re-reading an exported OTIO for the way
back: one bare ``filmcraft-cli inspect`` call returns the project tree *and*
the active sequence (clips with exact ``start``/``end``/``sourceIn`` ticks,
markers with ``start``/``duration``, fps, frame size), so nothing has to be
reconstructed from a second file. Tick -> seconds converts once:
``seconds = ticks / TICKS_PER_SECOND``.

What comes back is the *structural* edit — ``T:SH`` + ``T:TAG`` + ``CLIPS``.
Semantic tracks (``T:W`` …) live only in the original PLF (and in the
OTIO metadata); they are never touched by the editor, so the sync keeps the
timeline picture + markers and :mod:`.dirty` reports the difference against
the original.
"""
from __future__ import annotations

from math import gcd
from pathlib import Path

from ..schema import PLFClip, PLFEntry, PLFFile
from ..writer import write
from .client import FilmCraftClient, TICKS_PER_SECOND


def ticks_to_sec(ticks: int | float) -> float:
    """FilmCraft ticks -> seconds, rounded to PLF precision (2 decimals)."""
    return round(ticks / TICKS_PER_SECOND, 2)


def _ar_from_size(width: int | None, height: int | None) -> str:
    if not width or not height:
        return "16:9"
    g = gcd(width, height) or 1
    w, h = width // g, height // g
    return f"{w}:{h}"


def _media_names(tree: dict | None) -> dict[int, str]:
    """``item id -> display name`` from the project tree (files show up as
    Movie nodes named after the filename)."""
    names: dict[int, str] = {}

    def walk(node: dict) -> None:
        item, name = node.get("item"), node.get("name")
        if item is not None and name:
            names[int(item)] = str(name)
        for child in node.get("children", []) or []:
            walk(child)

    if tree:
        root = tree.get("root") or tree.get("project", {}).get("root", tree)
        walk(root)
    return names


def inspect_to_plf(data: dict, media_by_item: dict[int, str] | None = None) -> PLFFile:
    """Rebuild a PLF from a bare ``inspect`` (or a ``sequence.inspect``) dict.

    Accepts ``{"project": ..., "sequence": ...}`` (bare ``inspect``) or a
    bare sequence dict (``{"video": ..., "markers": ...}``).

    ``media_by_item`` (from :func:`plf.bridge.fcproj.fcproj_media_paths`) is
    the authoritative ``item id -> media path`` map; without it, the project
    tree's display names are used, which are the filenames for command-built
    projects but shot ids for OTIO-imported ones.
    """
    seq = data.get("sequence") if isinstance(data.get("sequence"), dict) else data
    settings = seq.get("settings") or {}
    frame_rate = settings.get("frame_rate") or {}
    fps = max(1, round(frame_rate.get("num", 24) / max(frame_rate.get("den", 1), 1)))

    plf = PLFFile(
        version="1.0",
        proj=seq.get("name") or "FilmCraft",
        fps=fps,
        ar=_ar_from_size(settings.get("width"), settings.get("height")),
        dur=ticks_to_sec(seq.get("duration") or 0),
        src="filmcraft",
        ctx="sync:sequence.inspect",
    )

    item_names = _media_names(data.get("project"))
    media_by_item = media_by_item or {}

    def media_name(it: dict) -> str:
        item_id = it.get("item")
        if item_id is not None and int(item_id) in media_by_item:
            return media_by_item[int(item_id)]
        if item_id is not None and int(item_id) in item_names:
            return item_names[int(item_id)]
        return it.get("name") or ""

    shots = sorted(
        (it for tr in seq.get("video") or [] for it in tr.get("items") or []),
        key=lambda it: it.get("start") or 0,
    )

    # Media in first-use order -> deterministic CLPxxx ids.
    clip_ids: dict[str, str] = {}
    for it in shots:
        name = media_name(it)
        if name and name not in clip_ids:
            clip_ids[name] = f"CLP{len(clip_ids) + 1:03d}"
            plf.clips.append(PLFClip(id=clip_ids[name], file=name, tc="00:00:00:00"))

    for n, it in enumerate(shots, 1):
        start = ticks_to_sec(it.get("start") or 0)
        end = ticks_to_sec(it.get("end") or 0)
        src_in = ticks_to_sec(it.get("sourceIn") or 0)
        src_out = ticks_to_sec(it.get("sourceOut") or (it.get("sourceIn") or 0) + (it.get("duration") or 0))
        name = media_name(it)
        clip_id = clip_ids.get(name)
        fields = {"id": f"sh{n:02d}"}
        if clip_id:
            fields["raw"] = f"{clip_id}@{src_in:.2f}-{src_out:.2f}"
        plf.timeline.append(
            PLFEntry(i=start, o=end, track="SH", fields=fields)
        )

    for m in sorted(seq.get("markers") or [], key=lambda m: m.get("start") or 0):
        start = ticks_to_sec(m.get("start") or 0)
        end = start + ticks_to_sec(m.get("duration") or 0)
        plf.timeline.append(
            PLFEntry(i=start, o=end, track="TAG", fields={"lbl": m.get("name") or ""})
        )

    return plf


def sync_project(project: str | Path, cli_path: str | None = None) -> tuple[PLFFile, str]:
    """Read a ``.fcproj`` back: returns ``(PLFFile, PLF text)``.

    Media paths come from the project file itself; the structure comes from
    one bare ``inspect`` call (tree + sequence + markers).
    """
    from .fcproj import fcproj_media_paths, load_fcproj

    client = FilmCraftClient(project, **({"cli_path": cli_path} if cli_path else {}))
    media_by_item = fcproj_media_paths(load_fcproj(project))
    plf = inspect_to_plf(client.inspect(), media_by_item=media_by_item)
    return plf, write(plf)
