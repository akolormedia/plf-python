"""Tests for the PLF -> FilmCraft bridge (Phase 2).

The command builders are pure and always tested. The end-to-end bridge
(:func:`load_plf_into_filmcraft`) needs a real ``filmcraft-cli`` binary, so it
is skipped when FilmCraft is not built.
"""
from pathlib import Path

import pytest

from plf import parse
from plf.bridge import (
    sec_to_ticks,
    referenced_clip_files,
    build_import_commands,
    build_sequence_command,
    build_place_commands,
    build_marker_commands,
    build_edit_commands,
    FilmCraftClient,
    Command,
    TICKS_PER_SECOND,
)

EXAMPLES_DIR = Path(__file__).parent.parent.parent / "plf-spec" / "examples"


def _load(name: str = "sol_en_playa.edit.plf"):
    return parse((EXAMPLES_DIR / name).read_text(encoding="utf-8"))


def _fake_items(plf):
    """A deterministic CLPxxx -> item-id map, as the import would resolve."""
    return {c.id: i + 1 for i, c in enumerate(plf.clips)}


# --- pure conversion -------------------------------------------------------


def test_sec_to_ticks_is_single_rounding():
    assert sec_to_ticks(0.0) == 0
    assert sec_to_ticks(1.0) == TICKS_PER_SECOND
    assert sec_to_ticks(4.12) == round(4.12 * TICKS_PER_SECOND)


def test_referenced_clip_files_deduplicated_in_plf_order():
    plf = _load()
    files = referenced_clip_files(plf)
    assert files == [
        "SOL_A001.mp4",
        "SOL_A002.mp4",
        "SOL_B001.mp4",
        "SOL_A004.mp4",
        "SOL_B005.mp4",
        "SOL_A006.mp4",
    ]


def test_build_import_command():
    plf = _load()
    cmd = build_import_commands(plf)
    assert cmd.id == "file.import"
    assert cmd.params["paths"][0] == "SOL_A001.mp4"


def test_build_sequence_command_uses_header():
    plf = _load()
    cmd = build_sequence_command(plf)
    assert cmd.id == "file.newSequence"
    assert cmd.params["fps"] == 24.0
    assert cmd.params["width"] == 1920
    assert cmd.params["height"] == 1080
    assert cmd.params["name"] == "SolEnLaPlaya"


def test_build_place_commands_exact_three_point():
    plf = _load()
    places = build_place_commands(plf, _fake_items(plf))
    assert len(places) == 24  # one per T:SH
    first = places[0]
    assert first.id == "timeline.place"
    assert first.params["item"] == 1  # CLP001 -> item 1
    assert first.params["track"] == "V1"
    assert first.params["time"] == 0  # s01 starts at t=0
    assert first.params["sourceIn"] == 0  # raw:CLP001@0.00-...
    assert first.params["duration"] == sec_to_ticks(4.12)
    # the second shot continues from the same source clip
    second = places[1]
    assert second.params["item"] == 1
    assert second.params["time"] == sec_to_ticks(4.12)
    assert second.params["sourceIn"] == sec_to_ticks(4.12)


def test_build_marker_commands():
    plf = _load()
    markers = build_marker_commands(plf)
    assert len(markers) == 9  # one per T:TAG
    m = markers[0]
    assert m.id == "markers.add"
    assert m.params["name"] == "emotional-breakdown,symbolic-gesture"
    assert m.params["time"] == sec_to_ticks(38.5)


def test_build_edit_commands_opens_sequence_first():
    plf = _load()
    cmds = build_edit_commands(plf, 13, _fake_items(plf))
    assert cmds[0].id == "sequence.open"
    assert cmds[0].params["item"] == 13
    assert sum(1 for c in cmds if c.id == "timeline.place") == 24
    assert sum(1 for c in cmds if c.id == "markers.add") == 9


# --- end-to-end (needs a built filmcraft-cli) ------------------------------


def _cli_path():
    p = FilmCraftClient.DEFAULT_CLI if hasattr(FilmCraftClient, "DEFAULT_CLI") else None
    from plf.bridge.client import DEFAULT_CLI

    return DEFAULT_CLI if Path(DEFAULT_CLI).exists() else None


def test_load_plf_into_filmcraft_end_to_end(tmp_path):
    cli = _cli_path()
    if not cli:
        pytest.skip("filmcraft-cli not built")

    # The example references SOL_*.mp4 by relative filename; create stand-ins
    # in the CWD the bridge runs from so the import resolves.
    import os
    import subprocess

    media_dir = tmp_path / "media"
    media_dir.mkdir()
    for name in ("SOL_A001", "SOL_A002", "SOL_B001", "SOL_A004", "SOL_B005", "SOL_A006"):
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=red:s=64x36:d=1",
                str(media_dir / f"{name}.mp4"),
            ],
            capture_output=True,
            check=False,
        )

    project = tmp_path / "sol.fcproj"
    prev = os.getcwd()
    os.chdir(media_dir)
    try:
        from plf.bridge import load_plf_into_filmcraft

        report = load_plf_into_filmcraft(_load(), project=str(project), cli_path=cli)
    finally:
        os.chdir(prev)

    assert report.placed_shots == 24
    assert report.added_markers == 9
    assert len(report.clip_to_item) == 6
    assert report.sequence_item is not None
    assert project.exists()

    # Read the sequence back: 24 clips at the exact PLF cut points.
    client = FilmCraftClient(str(project), cli_path=cli, save=False)
    client.run([Command("sequence.open", {"item": report.sequence_item})])
    seq = client.inspect().get("sequence") or client.inspect()
    clips = [c for tr in seq.get("video", []) for c in tr.get("items", [])]
    assert len(clips) == 24
    tps = TICKS_PER_SECOND
    assert clips[0]["start"] == 0
    assert abs(clips[1]["start"] / tps - 4.125) < 0.01  # 4.12s quantised to 24fps
    assert len(seq.get("markers", [])) == 9
