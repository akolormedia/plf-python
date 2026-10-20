"""Translate a parsed PLF file into the FilmCraft commands that rebuild it.

The mapping mirrors the Phase 0 spike and Phase 1 OTIO converter:

- ``CLIPS`` (``file:``) are imported once; ``CLPxxx`` -> the engine item id is
  resolved by filename from the project tree.
- ``T:SH`` with ``raw:CLPxxx@in-out`` -> ``timeline.place`` on ``V1`` with
  ``sourceIn``/``duration`` in ticks (three-point editing, exact).
- ``T:TAG`` -> ``markers.add`` (name = the tag's ``lbl``, length = the tag span).
- Semantic tracks (``ACT``, ``DLG``, ``W`` …) have no FilmCraft counterpart and
  are not placed; they live only in the PLF (and, in Phase 1, the OTIO).

Time converts once at the boundary: ``ticks = round(seconds * TICKS_PER_SECOND)``.
"""
from __future__ import annotations

from ..schema import PLFFile, PLFEntry
from .client import Command, TICKS_PER_SECOND


def sec_to_ticks(seconds: float) -> int:
    """Single rounding at the boundary; treat the result as exact afterwards."""
    return round(seconds * TICKS_PER_SECOND)


def _parse_raw_ref(raw: str) -> tuple[str, float, float] | None:
    """Parse ``CLP001@4.12-12.50`` -> ``(clip_id, in_sec, out_sec)``."""
    if "@" not in raw or "-" not in raw.split("@", 1)[1]:
        return None
    clip_id, span = raw.split("@", 1)
    in_s, out_s = span.split("-", 1)
    try:
        return clip_id.strip(), float(in_s), float(out_s)
    except ValueError:
        return None


def referenced_clip_files(plf: PLFFile) -> list[str]:
    """The media filenames referenced by any ``T:SH`` ``raw`` span, in order.

    These are the files the bridge must import. Deduplicated, PLF ``CLIPS``
    order preserved.
    """
    used = {
        _parse_raw_ref(e.fields["raw"])[0]
        for e in plf.timeline
        if e.track == "SH" and _parse_raw_ref(e.fields.get("raw", ""))
    }
    files = [c.file for c in plf.clips if c.id in used]
    return files


def build_import_commands(plf: PLFFile) -> Command:
    """One ``file.import`` bringing in every referenced media file."""
    return Command("file.import", {"paths": referenced_clip_files(plf)})


def build_sequence_command(plf: PLFFile, name: str | None = None) -> Command:
    """``file.newSequence`` sized to the PLF header (fps, 16:9 default)."""
    # PLF aspect ratios are like "16:9"; map the common ones to a frame size.
    ar = plf.ar or "16:9"
    size = _AR_SIZES.get(ar, (1920, 1080))
    return Command(
        "file.newSequence",
        {
            "name": name or plf.proj or "PLF",
            "fps": float(plf.fps),
            "width": size[0],
            "height": size[1],
        },
    )


_AR_SIZES = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "4:3": (1440, 1080),
    "2.39:1": (2048, 858),
    "1.85:1": (1920, 1038),
}


def build_place_commands(
    plf: PLFFile, clip_to_item: dict[str, int], track: str = "V1"
) -> list[Command]:
    """``timeline.place`` for every ``T:SH``, in PLF timeline order.

    ``clip_to_item`` maps ``CLPxxx`` -> FilmCraft item id (from the import).
    """
    commands: list[Command] = []
    for entry in plf.timeline:
        if entry.track != "SH":
            continue
        ref = _parse_raw_ref(entry.fields.get("raw", ""))
        if ref is None:
            continue
        clip_id, src_in, src_out = ref
        item = clip_to_item.get(clip_id)
        if item is None:
            continue
        commands.append(
            Command(
                "timeline.place",
                {
                    "item": item,
                    "track": track,
                    "time": sec_to_ticks(entry.i),
                    "sourceIn": sec_to_ticks(src_in),
                    "duration": sec_to_ticks(src_out - src_in),
                    "video": True,
                    "audio": False,
                },
            )
        )
    return commands


def build_marker_commands(plf: PLFFile, fps: int | None = None) -> list[Command]:
    """``markers.add`` for every ``T:TAG`` (name = ``lbl``, length = span)."""
    rate = fps or plf.fps
    commands: list[Command] = []
    for entry in plf.timeline:
        if entry.track != "TAG":
            continue
        lbl = entry.fields.get("lbl", "")
        params: dict = {
            "time": sec_to_ticks(entry.i),
            "name": lbl,
            "durationFrames": round((entry.o - entry.i) * rate),
        }
        commands.append(Command("markers.add", params))
    return commands


def build_edit_commands(
    plf: PLFFile, sequence_item: int, clip_to_item: dict[str, int]
) -> list[Command]:
    """sequence.open + all places + all markers, for a known sequence id."""
    cmds = [Command("sequence.open", {"item": sequence_item})]
    cmds += build_place_commands(plf, clip_to_item)
    cmds += build_marker_commands(plf)
    return cmds
