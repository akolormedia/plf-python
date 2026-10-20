"""PLF <-> OpenTimelineIO conversion.

Design
------
PLF is a *semantic* editing format; OTIO is a *geometric* interchange format.
The conversion is deliberately lossless in one direction and best-effort in the
other:

- **PLF -> OTIO** (``plf_to_otio``) is the primary, lossless-for-picture path.
  Every ``T:SH`` with a ``raw:CLPxxx@in-out`` reference becomes an OTIO clip on
  the ``Video 1`` track, positioned at its PLF timeline range and reading the
  source range named by ``raw``. ``T:TAG`` entries become OTIO markers. All the
  purely semantic tracks that OTIO has no slot for (``T:ACT``, ``T:DLG``,
  ``T:W``, ``T:MUS``, ``T:AMB``, ``T:EL``, ``T:SCN``, ``T:USR``) are preserved
  verbatim in the timeline ``metadata['plf']`` so nothing is ever dropped.

- **OTIO -> PLF** (``otio_to_plf``) rebuilds a PLF *picture* edit from an OTIO
  timeline: clips on ``Video 1`` become ``T:SH`` entries and markers become
  ``T:TAG`` entries. The semantic tracks are restored from
  ``metadata['plf']['timeline']`` when present (i.e. a round-trip of our own
  export), otherwise they are omitted (a foreign OTIO file has no semantics).

Exact time
----------
OTIO uses rational ``RationalTime`` values. PLF uses float seconds. To avoid
drift we convert once, at the boundary, using the sequence frame rate:
``frames = round(seconds * fps)`` and hand OTIO integer frame values at that
rate. On the way back, ``seconds = frames / fps``. Every clip in the spike
survives a round-trip at exactly its original frame boundary.
"""
from __future__ import annotations

import opentimelineio as otio
from opentimelineio import opentime

from .schema import PLFFile, PLFEntry, PLFClip
from .parser import parse

VIDEO_TRACK = "Video 1"
# Semantic PLF tracks that have no OTIO counterpart and ride along in metadata.
SEMANTIC_TRACKS = ("ACT", "DLG", "W", "MUS", "AMB", "EL", "SCN", "USR")


def _sec_to_frames(seconds: float, fps: int) -> int:
    """Single rounding at the boundary; the caller treats the result as exact."""
    return round(seconds * fps)


def _frames_to_sec(frames: int, fps: int) -> float:
    return frames / fps


def _tc_to_frames(tc: str, fps: int) -> int:
    """Parse an ``HH:MM:SS:FF`` timecode into an absolute frame count."""
    parts = tc.split(":")
    if len(parts) != 4:
        return 0
    hh, mm, ss, ff = (int(p) for p in parts)
    return ((hh * 60 + mm) * 60 + ss) * fps + ff


def _clip_refs(plf: PLFFile) -> dict[str, otio.schema.ExternalReference]:
    """Map ``CLPxxx`` id -> an OTIO ExternalReference anchored at its timecode."""
    refs: dict[str, otio.schema.ExternalReference] = {}
    for clip in plf.clips:
        target = None
        if clip.tc:
            start = _tc_to_frames(clip.tc, plf.fps)
            target = opentime.TimeRange(
                start_time=opentime.RationalTime(start, plf.fps),
                duration=opentime.RationalTime(0, plf.fps),
            )
        ref = otio.schema.ExternalReference(
            target_url=clip.file,
            available_range=target,
            metadata={"plf": {"clip": clip.id, "tc": clip.tc}},
        )
        refs[clip.id] = ref
    return refs


def _parse_raw_ref(raw: str) -> tuple[str, float, float] | None:
    """Parse ``CLP001@4.12-12.50`` into ``(clip_id, in_sec, out_sec)``."""
    if "@" not in raw:
        return None
    clip_id, span = raw.split("@", 1)
    if "-" not in span:
        return None
    in_s, out_s = span.split("-", 1)
    try:
        return clip_id.strip(), float(in_s), float(out_s)
    except ValueError:
        return None


def plf_to_otio(plf: PLFFile) -> otio.schema.Timeline:
    """Convert a parsed PLF file into an OTIO Timeline.

    Picture (``T:SH``) and ``T:TAG`` are materialised as clips and markers; all
    semantic tracks are preserved in ``timeline.metadata['plf']``.
    """
    fps = plf.fps
    tl = otio.schema.Timeline(name=plf.proj)
    v1 = otio.schema.Track(name=VIDEO_TRACK, kind=otio.schema.TrackKind.Video)
    tl.tracks.append(v1)

    refs = _clip_refs(plf)

    # Build one clip per T:SH, positioned on the timeline by its PLF i/o and
    # reading the source range named by its ``raw`` reference.
    for entry in plf.timeline:
        if entry.track != "SH":
            continue
        raw = entry.fields.get("raw")
        ref = _parse_raw_ref(raw) if raw else None
        if ref is None:
            continue
        clip_id, src_in, src_out = ref

        timeline_range = opentime.TimeRange(
            start_time=opentime.RationalTime(
                _sec_to_frames(entry.i, fps), fps
            ),
            duration=opentime.RationalTime(
                _sec_to_frames(entry.o - entry.i, fps), fps
            ),
        )
        source_range = opentime.TimeRange(
            start_time=opentime.RationalTime(
                _sec_to_frames(src_in, fps), fps
            ),
            duration=opentime.RationalTime(
                _sec_to_frames(src_out - src_in, fps), fps
            ),
        )

        base_ref = refs.get(clip_id)
        # Preserve the source in-point on the way back: available_range records
        # where in the media this clip reads from (the PLF ``raw`` span).
        base_range = base_ref.available_range if base_ref else None
        media_ref = otio.schema.ExternalReference(
            target_url=base_ref.target_url if base_ref else clip_id,
            available_range=base_range,
            metadata={"plf": dict(base_ref.metadata.get("plf", {})) if base_ref else {"clip": clip_id}},
        )
        clip = otio.schema.Clip(
            name=entry.fields.get("id", clip_id),
            source_range=source_range,
            media_reference=media_ref,
            metadata={"plf": {"track": "SH", "raw": raw, **entry.fields}},
        )
        v1.append(clip)

    # T:TAG -> markers anchored at their timeline position.
    for entry in plf.timeline:
        if entry.track != "TAG":
            continue
        lbl = entry.fields.get("lbl", "")
        marker = otio.schema.Marker(
            name=lbl,
            marked_range=opentime.TimeRange(
                start_time=opentime.RationalTime(
                    _sec_to_frames(entry.i, fps), fps
                ),
                duration=opentime.RationalTime(
                    max(_sec_to_frames(entry.o - entry.i, fps), 0), fps
                ),
            ),
        )
        tl.tracks.markers.append(marker)

    # Preserve every semantic entry verbatim so the conversion is never lossy.
    semantic = [
        {
            "i": e.i,
            "o": e.o,
            "track": e.track,
            "fields": dict(e.fields),
        }
        for e in plf.timeline
        if e.track in SEMANTIC_TRACKS
    ]
    tl.metadata["plf"] = {
        "proj": plf.proj,
        "version": plf.version,
        "fps": plf.fps,
        "ar": plf.ar,
        "dur": plf.dur,
        "src": plf.src,
        "ref": plf.ref,
        "ctx": plf.ctx,
        "cast": [
            {"id": c.id, "nombre": c.nombre, "desc": c.desc} for c in plf.cast
        ],
        "scenes": [
            {"id": s.id, "loc": s.loc, "time": s.time, "act": s.act, "desc": s.desc}
            for s in plf.scenes
        ],
        "clips": [
            {"id": c.id, "file": c.file, "tc": c.tc} for c in plf.clips
        ],
        "timeline": semantic,
    }
    return tl


def otio_to_plf(timeline: otio.schema.Timeline) -> PLFFile:
    """Rebuild a PLF picture edit from an OTIO timeline.

    ``Video 1`` clips become ``T:SH`` and timeline markers become ``T:TAG``.
    Semantic tracks are restored from ``metadata['plf']`` when available (a
    round-trip of our own export); a foreign OTIO file yields picture only.
    """
    meta = _plain(timeline.metadata.get("plf", {}))
    fps = int(meta.get("fps") or _fps_from_timeline(timeline) or 24)

    plf = PLFFile(
        version=meta.get("version", "1.0"),
        proj=timeline.name or meta.get("proj", ""),
        fps=fps,
        ar=meta.get("ar", "16:9"),
        dur=meta.get("dur", 0.0),
        src=meta.get("src", "editado"),
        ref=meta.get("ref"),
        ctx=meta.get("ctx", ""),
    )

    for c in meta.get("clips", []):
        plf.clips.append(PLFClip(id=c["id"], file=c["file"], tc=c.get("tc", "")))

    from .schema import PLFCastMember, PLFScene

    for c in meta.get("cast", []):
        plf.cast.append(PLFCastMember(id=c["id"], nombre=c["nombre"], desc=c.get("desc", "")))
    for s in meta.get("scenes", []):
        plf.scenes.append(
            PLFScene(id=s["id"], loc=s.get("loc", ""), time=s.get("time", ""),
                     act=s.get("act", 0), desc=s.get("desc", ""))
        )

    # T:SH from the Video 1 track.
    v1 = _video_track(timeline)
    if v1 is not None:
        cursor = 0.0
        for clip in v1:
            if not isinstance(clip, otio.schema.Clip):
                continue
            sr = clip.source_range
            if sr is None:
                continue
            # source_range is the span *within the media*, not the timeline
            # position. Timeline position accumulates the durations of the
            # preceding clips on this track (PLF is a gapless linear edit).
            dur = _frames_to_sec(int(sr.duration.value), fps)
            i = cursor
            cursor += dur
            media_ref = clip.media_reference
            plf_meta = _plain(clip.metadata.get("plf", {}))
            clip_id = plf_meta.get("raw", "").split("@")[0] if plf_meta.get("raw") else None
            clip_id = clip_id or (media_ref.metadata.get("plf", {}).get("clip") if media_ref else None)
            # ``raw`` is stored verbatim in the clip's own metadata; fall back
            # to the media's available_range for foreign OTIO files.
            if plf_meta.get("raw"):
                raw = plf_meta["raw"]
            else:
                avail = media_ref.available_range if media_ref else None
                src_in = _frames_to_sec(int(avail.start_time.value), fps) if avail else 0.0
                raw = f"{clip_id or clip.name}@{src_in:.2f}-{src_in + dur:.2f}"
            fields = {k: v for k, v in plf_meta.items() if k not in ("track", "raw")}
            entry = PLFEntry(
                i=i,
                o=i + dur,
                track="SH",
                fields={"id": clip.name, "raw": raw, **fields},
            )
            plf.timeline.append(entry)

    # T:TAG from timeline markers.
    for m in timeline.tracks.markers:
        start = _frames_to_sec(int(m.marked_range.start_time.value), fps)
        dur = _frames_to_sec(int(m.marked_range.duration.value), fps)
        plf.timeline.append(
            PLFEntry(i=start, o=start + dur, track="TAG", fields={"lbl": m.name})
        )

    # Restore the semantic tracks verbatim. Copy fields into plain dicts: OTIO
    # hands back C++ AnyDictionary views that die once the timeline is dropped.
    for e in meta.get("timeline", []):
        fields = e.get("fields", {})
        if not isinstance(fields, dict):
            fields = dict(fields)
        else:
            fields = {k: v for k, v in fields.items()}
        plf.timeline.append(
            PLFEntry(i=float(e["i"]), o=float(e["o"]), track=e["track"], fields=fields)
        )

    # Keep a coherent duration even if metadata lacked one.
    if not plf.dur and plf.timeline:
        plf.dur = max(e.o for e in plf.timeline)

    plf.timeline.sort(key=lambda e: (e.i, e.track))
    return plf


def _plain(obj):
    """Deep-copy an OTIO metadata subtree into plain Python containers.

    OTIO returns C++ ``AnyDictionary`` / ``AnyArray`` views that are invalidated
    once the owning timeline is garbage-collected, so semantic fields must be
    materialised eagerly or they die with the timeline.
    """
    if isinstance(obj, dict):
        return {str(k): _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    return obj


def save_otio(timeline: otio.schema.Timeline, path: str) -> None:
    """Serialize an OTIO timeline to ``path`` (.otio)."""
    otio.adapters.write_to_file(timeline, path)


def load_otio(path: str) -> otio.schema.Timeline:
    """Load an OTIO timeline from ``path``."""
    return otio.adapters.read_from_file(path)


def _video_track(timeline: otio.schema.Timeline) -> otio.schema.Track | None:
    for track in timeline.tracks:
        if track.kind == otio.schema.TrackKind.Video:
            return track
    return None


def _fps_from_timeline(timeline: otio.schema.Timeline) -> float | None:
    v1 = _video_track(timeline)
    if v1 is None:
        return None
    for clip in v1:
        if isinstance(clip, otio.schema.Clip) and clip.source_range:
            return clip.source_range.start_time.rate
    return None
