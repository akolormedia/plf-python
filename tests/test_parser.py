import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from plf import parse, write, validate, validate_cross_track
from plf import get_entries, get_entries_at, get_scene_at

EXAMPLES_DIR = Path(__file__).parent.parent.parent / "plf-spec" / "examples"


def load_plf(name: str) -> str:
    path = EXAMPLES_DIR / name
    return path.read_text(encoding="utf-8")


def test_parse_sol_en_playa():
    text = load_plf("sol_en_playa.edit.plf")
    plf = parse(text)

    assert plf.proj == "SolEnLaPlaya"
    assert plf.fps == 24
    assert plf.ar == "16:9"
    assert plf.dur == 332.16
    assert plf.src == "editado"
    assert plf.ref == "SolEnLaPlaya.raw.plf"
    assert "Carlos returns" in plf.ctx
    assert len(plf.cast) == 3
    assert plf.cast[0].id == "A1"
    assert plf.cast[0].nombre == "Carlos"
    assert len(plf.scenes) == 3
    assert plf.scenes[0].id == "SC01"
    assert plf.scenes[0].loc == "ext-beach-sunset"
    assert len(plf.clips) == 6
    assert plf.clips[0].id == "CLP001"
    assert len(plf.timeline) > 20


def test_parse_la_ultima_vez():
    text = load_plf("la_ultima_vez.edit.plf")
    plf = parse(text)

    assert plf.proj == "LaUltimaVez"
    assert plf.fps == 24
    assert plf.ar == "2.39:1"
    assert plf.dur == 487.40
    assert plf.src == "editado"
    assert "Laura returns" in plf.ctx
    assert len(plf.cast) == 5
    assert plf.cast[0].id == "A1"
    assert plf.cast[0].nombre == "Laura"
    assert len(plf.scenes) == 8
    assert len(plf.clips) == 8
    assert len(plf.timeline) > 40


def test_roundtrip_sol():
    text = load_plf("sol_en_playa.edit.plf")
    plf = parse(text)
    regenerated = write(plf)
    plf2 = parse(regenerated)

    assert plf2.proj == plf.proj
    assert plf2.fps == plf.fps
    assert plf2.dur == plf.dur
    assert plf2.src == plf.src
    assert plf2.ctx == plf.ctx
    assert len(plf2.cast) == len(plf.cast)
    assert len(plf2.scenes) == len(plf.scenes)
    assert len(plf2.clips) == len(plf.clips)
    assert len(plf2.timeline) == len(plf.timeline)

    for a, b in zip(plf.timeline, plf2.timeline):
        assert a.i == b.i, f"i mismatch: {a.i} vs {b.i}"
        assert a.o == b.o, f"o mismatch: {a.o} vs {b.o}"
        assert a.track == b.track, f"track mismatch: {a.track} vs {b.track}"
        assert a.fields == b.fields, f"fields mismatch for {a.track} at i={a.i:.2f}"


def test_roundtrip_luv():
    text = load_plf("la_ultima_vez.edit.plf")
    plf = parse(text)
    regenerated = write(plf)
    plf2 = parse(regenerated)

    assert plf2.proj == plf.proj
    assert plf2.dur == plf.dur
    assert len(plf2.cast) == len(plf.cast)
    assert len(plf2.scenes) == len(plf.scenes)
    assert len(plf2.timeline) == len(plf.timeline)

    for a, b in zip(plf.timeline, plf2.timeline):
        assert a.i == b.i
        assert a.o == b.o
        assert a.track == b.track
        assert a.fields == b.fields


def test_validate_sol():
    text = load_plf("sol_en_playa.edit.plf")
    plf = parse(text)
    result = validate(plf)
    assert result.is_valid, f"Validation errors: {result.errors}"


def test_validate_luv():
    text = load_plf("la_ultima_vez.edit.plf")
    plf = parse(text)
    result = validate(plf)
    assert result.is_valid, f"Validation errors: {result.errors}"


def test_cross_track_sol():
    text = load_plf("sol_en_playa.edit.plf")
    plf = parse(text)
    result = validate_cross_track(plf)
    assert result.is_valid, f"Cross-track errors: {result.errors}"


def test_cross_track_luv():
    text = load_plf("la_ultima_vez.edit.plf")
    plf = parse(text)
    result = validate_cross_track(plf)
    assert result.is_valid, f"Cross-track errors: {result.errors}"


def test_query_shots_sol():
    text = load_plf("sol_en_playa.edit.plf")
    plf = parse(text)
    shots = get_entries(plf, track="SH")
    assert len(shots) == 24


def test_query_shots_luv():
    text = load_plf("la_ultima_vez.edit.plf")
    plf = parse(text)
    shots = get_entries(plf, track="SH")
    assert len(shots) == 34


def test_query_actions_by_subject():
    text = load_plf("la_ultima_vez.edit.plf")
    plf = parse(text)
    actions = get_entries(plf, track="ACT", subj="A1")
    assert len(actions) > 5


def test_get_entries_at():
    text = load_plf("sol_en_playa.edit.plf")
    plf = parse(text)
    active = get_entries_at(plf, 60.0)
    assert len(active) > 0
    tracks = {e.track for e in active}
    assert "SH" in tracks or "SCN" in tracks


def test_get_scene_at():
    text = load_plf("la_ultima_vez.edit.plf")
    plf = parse(text)
    scene = get_scene_at(plf, 200.0)
    assert scene is not None
    scene2 = get_scene_at(plf, 400.0)
    assert scene2 is not None
