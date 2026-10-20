"""Tests for the PLF <-> OpenTimelineIO converter (Phase 1).

OTIO is an optional dependency (``pip install plf[otio]``); these tests skip
gracefully when it is not installed.
"""
from pathlib import Path

import pytest

from plf import parse, plf_to_otio, otio_to_plf, validate

opentimelineio = pytest.importorskip("opentimelineio")

EXAMPLES_DIR = Path(__file__).parent.parent.parent / "plf-spec" / "examples"


def _load(name: str):
    return parse((EXAMPLES_DIR / name).read_text(encoding="utf-8"))


def _roundtrip(plf_obj):
    """PLF -> OTIO (in memory) -> PLF, no file on disk."""
    return otio_to_plf(plf_to_otio(plf_obj))


def test_plf_to_otio_produces_one_clip_per_shot():
    plf = _load("sol_en_playa.edit.plf")
    tl = plf_to_otio(plf)
    video = tl.tracks[0]
    assert len(video) == 24  # 24 T:SH entries -> 24 clips
    assert len(tl.tracks.markers) == 9  # 9 T:TAG -> 9 markers


def test_plf_to_otio_clip_media_and_source_range():
    plf = _load("sol_en_playa.edit.plf")
    tl = plf_to_otio(plf)
    clip = tl.tracks[0][0]  # s01, raw:CLP001@0.00-4.12
    assert clip.name == "s01"
    assert clip.media_reference.target_url == "SOL_A001.mp4"
    # 0.00-4.12s @24fps -> 0..99 frames (4.12*24 = 98.88 -> 99)
    assert clip.source_range.start_time.value == 0
    assert clip.source_range.duration.value == 99


def test_plf_to_otio_preserves_semantic_tracks_in_metadata():
    plf = _load("sol_en_playa.edit.plf")
    tl = plf_to_otio(plf)
    meta = tl.metadata["plf"]
    tracks = {e["track"] for e in meta["timeline"]}
    # Every semantic (non-picture, non-marker) track survives in metadata.
    assert "ACT" in tracks
    assert "DLG" in tracks
    assert "W" in tracks
    assert len(meta["cast"]) == 3
    assert len(meta["clips"]) == 6


def test_roundtrip_preserves_shot_timings_within_half_frame():
    plf = _load("sol_en_playa.edit.plf")
    rt = _roundtrip(plf)
    orig = [e for e in plf.timeline if e.track == "SH"]
    back = [e for e in rt.timeline if e.track == "SH"]
    assert len(orig) == len(back) == 24
    tol = 0.5 / plf.fps  # half a frame; the grid is the only limit
    for a, b in zip(orig, back):
        assert abs(a.i - b.i) <= tol, (a.i, b.i)
        assert abs(a.o - b.o) <= tol, (a.o, b.o)


def test_roundtrip_preserves_raw_references_exactly():
    plf = _load("sol_en_playa.edit.plf")
    rt = _roundtrip(plf)
    orig = [e.fields["raw"] for e in plf.timeline if e.track == "SH"]
    back = [e.fields["raw"] for e in rt.timeline if e.track == "SH"]
    assert orig == back  # the ``raw`` span rides along verbatim


def test_roundtrip_preserves_semantic_tracks():
    plf = _load("sol_en_playa.edit.plf")
    rt = _roundtrip(plf)
    for track in ("ACT", "DLG", "W", "MUS", "AMB", "EL", "SCN", "USR"):
        assert [e for e in rt.timeline if e.track == track], f"lost {track}"


def test_roundtrip_preserves_header_and_sections():
    plf = _load("sol_en_playa.edit.plf")
    rt = _roundtrip(plf)
    assert rt.proj == plf.proj
    assert rt.fps == plf.fps
    assert rt.ar == plf.ar
    assert len(rt.cast) == len(plf.cast)
    assert len(rt.clips) == len(plf.clips)
    assert rt.ctx == plf.ctx


def test_roundtrip_validates():
    plf = _load("sol_en_playa.edit.plf")
    rt = _roundtrip(plf)
    result = validate(rt)
    assert result.is_valid, result.errors


def test_roundtrip_on_synthetic_pipeline_output():
    """The converter must handle a pipeline-produced .raw.plf too."""
    text = (
        "PLF1.0 proj:TestClip fps:24 ar:16:9 dur:6.00 src:bruto\n"
        'ctx:"synthetic"\n\n'
        "CAST:\n"
        "  X1  nombre:unknown  desc:unidentified-figure\n\n"
        "SCENES:\n"
        '  SC01  loc:test  time:tarde  act:1  desc:"test"\n\n'
        "CLIPS:\n"
        "  CLP001  file:test_clip.mp4  tc:00:00:00:00\n\n"
        "i:0.00    o:3.00    T:SH   id:s01  shot:LS  loc:test  "
        "trans_i:CT  trans_o:CT  cam:sta  mood:ale  raw:CLP001@0.00-3.00\n"
        "i:3.00    o:6.00    T:SH   id:s02  shot:LS  loc:test  "
        "trans_i:CT  trans_o:CT  cam:sta  mood:ale  raw:CLP001@3.00-6.00\n"
    )
    plf = parse(text)
    tl = plf_to_otio(plf)
    assert len(tl.tracks[0]) == 2
    assert tl.tracks[0][1].source_range.start_time.value == 72  # 3s @24fps
    assert tl.tracks[0][1].media_reference.target_url == "test_clip.mp4"
    rt = _roundtrip(plf)
    assert validate(rt).is_valid


def test_otio_to_plf_foreign_timeline_yields_picture_only():
    """A foreign OTIO file (no plf metadata) still produces valid T:SH."""
    import opentimelineio as otio

    tl = otio.schema.Timeline(name="Foreign")
    video = otio.schema.Track(name="Video 1", kind=otio.schema.TrackKind.Video)
    tl.tracks.append(video)
    ref = otio.schema.ExternalReference(target_url="foreign.mp4")
    clip = otio.schema.Clip(
        name="c1",
        media_reference=ref,
        source_range=opentimelineio.opentime.TimeRange(
            start_time=opentimelineio.opentime.RationalTime(0, 24),
            duration=opentimelineio.opentime.RationalTime(48, 24),
        ),
    )
    video.append(clip)
    plf = otio_to_plf(tl)
    sh = [e for e in plf.timeline if e.track == "SH"]
    assert len(sh) == 1
    assert sh[0].fields["raw"] == "c1@0.00-2.00"
