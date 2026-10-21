"""Fase FC-A: native load (OTIO import), reverse sync, dirty flags, generate.

The FilmCraft binary is not required: native load runs against a fake
client, reverse/dirty run on fixtures shaped from real ``inspect`` output
(commit 105c09b), generate against an injected poster.
"""

import json
from pathlib import Path

from plf import parse
from plf.bridge.client import CommandResult
from plf.bridge.dirty import diff_plf
from plf.bridge.fcproj import fcproj_media_paths, project_video_paths
from plf.bridge.generate import generate_plfs
from plf.bridge.native import load_plf_native
from plf.bridge.reverse import inspect_to_plf, ticks_to_sec
from plf.srt import words_to_srt
from plf.schema import PLFEntry, PLFFile
from plf.writer import write

TPS = 254_016_000_000
S3 = 3 * TPS  # 762048000000

# Fixture shaped from a real `filmcraft-cli inspect` at 105c09b.
INSPECT = {
    "project": {
        "root": {
            "id": 0, "name": "p", "children": [
                {"type": "Movie", "name": "test_clip.mp4", "item": 1},
                {"type": "Sequence", "name": "RT1", "item": 8},
            ],
        }
    },
    "sequence": {
        "name": "RT1",
        "duration": 2 * S3,
        "settings": {"frame_rate": {"num": 24, "den": 1}, "width": 1920, "height": 1080},
        "markers": [
            {"name": "pantalla", "start": 0, "duration": S3},
            {"name": "muro", "start": S3, "duration": 0},
        ],
        "video": [{
            "name": "Video 1",
            "items": [
                {"item": 1, "name": "test_clip.mp4", "start": 0, "end": S3,
                 "sourceIn": 0, "sourceOut": S3, "duration": S3},
                {"item": 1, "name": "test_clip.mp4", "start": S3, "end": 2 * S3,
                 "sourceIn": S3, "sourceOut": 2 * S3, "duration": S3},
            ],
        }],
        "audio": [],
    },
}

MINI_PLF = (
    "PLF1.0 proj:FCart fps:24 ar:16:9 dur:6.00 src:bruto\n"
    'ctx:"fc-a"\n\n'
    "CAST:\n"
    "  X1  nombre:unknown  desc:figure\n\n"
    "SCENES:\n"
    '  SC01  loc:test  time:tarde  act:1  desc:"t"\n\n'
    "CLIPS:\n"
    "  CLP001  file:test_clip.mp4  tc:00:00:00:00\n\n"
    "i:0.00    o:3.00    T:SH   id:s01  shot:LS  loc:test  "
    "trans_i:CT  trans_o:CT  cam:sta  mood:ale  raw:CLP001@0.00-3.00\n"
    "i:3.00    o:6.00    T:SH   id:s02  shot:LS  loc:test  "
    "trans_i:CT  trans_o:CT  cam:sta  mood:ale  raw:CLP001@3.00-6.00\n"
    "i:0.50    o:2.50    T:TAG  lbl:pantalla\n"
    "i:3.00    o:4.00    T:TAG  lbl:muro\n"
    "i:0.66    o:1.12    T:DLG  spk:A1  tone:neutral\n"
    'i:0.66    o:1.12    T:W    spk:A1  "Hoy"\n'
    'i:1.12    o:1.38    T:W    spk:A1  "tengo"\n'
)


def _make_plf():
    return parse(MINI_PLF)


# --------------------------------------------------------------------------
# reverse sync
# --------------------------------------------------------------------------

def test_ticks_to_sec_single_rounding():
    assert ticks_to_sec(S3) == 3.0
    assert ticks_to_sec(0) == 0.0


def test_inspect_to_plf_builds_shots_markers_clips():
    plf = inspect_to_plf(INSPECT)
    assert plf.proj == "RT1"
    assert plf.fps == 24
    assert plf.ar == "16:9"
    assert plf.dur == 6.0
    assert plf.src == "filmcraft"

    shots = [e for e in plf.timeline if e.track == "SH"]
    assert [(e.i, e.o) for e in shots] == [(0.0, 3.0), (3.0, 6.0)]
    assert shots[0].fields["raw"] == "CLP001@0.00-3.00"
    assert shots[1].fields["raw"] == "CLP001@3.00-6.00"

    tags = [e for e in plf.timeline if e.track == "TAG"]
    assert [(e.fields["lbl"], e.i, e.o) for e in tags] == [
        ("pantalla", 0.0, 3.0), ("muro", 3.0, 3.0),
    ]
    assert [(c.id, c.file) for c in plf.clips] == [("CLP001", "test_clip.mp4")]


def test_inspect_to_plf_prefers_fcproj_media_paths():
    # OTIO-imported projects display shot ids in the tree; the fcproj has
    # the real absolute paths.
    data = json.loads(json.dumps(INSPECT))
    data["project"]["root"]["children"][0]["name"] = "s01"
    plf = inspect_to_plf(data, media_by_item={1: "/media/real.mp4"})
    assert plf.clips[0].file == "/media/real.mp4"
    assert plf.timeline[0].fields["raw"].startswith("CLP001@")


def test_synced_plf_writes_and_reparses():
    text = write(inspect_to_plf(INSPECT))
    rt = parse(text)
    assert len([e for e in rt.timeline if e.track == "SH"]) == 2
    assert len([e for e in rt.timeline if e.track == "TAG"]) == 2
    assert rt.clips[0].file == "test_clip.mp4"


# --------------------------------------------------------------------------
# dirty flags (§3.4)
# --------------------------------------------------------------------------

def test_diff_clean():
    o = parse(MINI_PLF)
    s = parse(MINI_PLF)
    # semantic tracks exist only in the original — never dirty by construction
    report = diff_plf(o, s)
    assert report.clean, [d.reason for d in report.segments]


def test_diff_moved_shot_is_structural():
    o = parse(MINI_PLF)
    s = parse(MINI_PLF)
    s.timeline[0].i += 1.0
    s.timeline[0].o += 1.0
    report = diff_plf(o, s)
    assert len(report.structural) == 1
    assert report.structural[0].regenerate  # §3.4: structural -> Model A on save
    assert "moved" in report.structural[0].reason


def test_diff_removed_and_added_shots():
    o = parse(MINI_PLF)
    s = parse(MINI_PLF)
    removed = s.timeline.pop(1)
    report = diff_plf(o, s)
    assert any("removed" in d.reason for d in report.structural)

    s2 = parse(MINI_PLF)
    extra = PLFEntry(i=6.0, o=7.0, track="SH",
                     fields={"id": "s99", "raw": "CLP001@0.00-1.00"})
    s2.timeline.append(extra)
    report2 = diff_plf(o, s2)
    assert any("added" in d.reason for d in report2.structural)


def test_diff_marker_rename_is_metadata():
    o = parse(MINI_PLF)
    s = parse(MINI_PLF)
    tag = next(e for e in s.timeline if e.track == "TAG")
    tag.fields["lbl"] = "pantalla_b"
    report = diff_plf(o, s)
    assert len(report.metadata) == 1
    assert not report.metadata[0].regenerate
    assert report.clean is False


def test_diff_marker_move_is_structural():
    o = parse(MINI_PLF)
    s = parse(MINI_PLF)
    tag = next(e for e in s.timeline if e.track == "TAG")
    tag.i += 0.5
    report = diff_plf(o, s)
    assert any(d.kind == "structural" and d.track == "TAG" for d in report.segments)


def test_diff_source_recut_is_structural():
    o = parse(MINI_PLF)
    s = parse(MINI_PLF)
    s.timeline[0].fields["raw"] = "CLP001@0.50-3.00"
    report = diff_plf(o, s)
    assert any("source window" in d.reason for d in report.structural)


# --------------------------------------------------------------------------
# SRT sidecar (captions.import)
# --------------------------------------------------------------------------

def test_words_to_srt_groups_and_times():
    srt = words_to_srt(_make_plf().timeline)
    assert srt.startswith("1\n")
    assert "-->" in srt
    assert "Hoy tengo" in srt
    # 0.66s -> 00:00:00,660
    assert "00:00:00,660 --> " in srt


def test_words_to_srt_empty_without_words():
    p = parse(MINI_PLF)
    p.timeline = [e for e in p.timeline if e.track != "W"]
    assert words_to_srt(p.timeline) == ""


# --------------------------------------------------------------------------
# fcproj reading + generate
# --------------------------------------------------------------------------

def _fcproj(paths):
    return {"project": {"items": {
        str(i): {"id": i, "name": Path(p).name,
                 "kind": {"Media": {"media": {"File": {"path": p}}}}}
        for i, p in enumerate(paths, 1)
    }}}


def test_fcproj_media_paths(tmp_path):
    d = _fcproj(["/m/a.mp4", "/m/b.mov", "/m/notes.txt"])
    assert fcproj_media_paths(d) == {1: "/m/a.mp4", 2: "/m/b.mov", 3: "/m/notes.txt"}
    assert project_video_paths(d) == ["/m/a.mp4", "/m/b.mov"]


def test_generate_plfs_writes_one_per_video(tmp_path):
    v1 = tmp_path / "one.mp4"
    v2 = tmp_path / "two.mov"
    v1.write_bytes(b"\x00")
    v2.write_bytes(b"\x00")
    proj = tmp_path / "p.fcproj"
    proj.write_text(json.dumps(_fcproj([str(v1), str(v2)])))

    calls = []

    def poster(video, context):
        calls.append((video, context))
        return "# PLF v1.0\ntitle  x\n"

    results = generate_plfs(proj, context={"language": "es"}, poster=poster)
    assert [r["state"] for r in results] == ["done", "done"]
    assert (tmp_path / "one.raw.plf").is_file()
    assert (tmp_path / "two.raw.plf").is_file()
    assert calls[0][1] == {"language": "es"}


def test_generate_plfs_skip_and_error(tmp_path):
    v1 = tmp_path / "one.mp4"
    v1.write_bytes(b"\x00")
    (tmp_path / "one.raw.plf").write_text("# existing")
    proj = tmp_path / "p.fcproj"
    proj.write_text(json.dumps(_fcproj([str(v1)])))

    def poster(video, context):
        raise RuntimeError("pipeline down")

    results = generate_plfs(proj, poster=poster, skip_existing=True)
    assert results[0]["state"] == "skipped"
    assert (tmp_path / "one.raw.plf").read_text() == "# existing"

    results = generate_plfs(proj, poster=poster, skip_existing=False)
    assert results[0]["state"] == "error"
    assert "pipeline down" in results[0]["error"]


# --------------------------------------------------------------------------
# native load (fake client)
# --------------------------------------------------------------------------

class FakeClient:
    """Enough FilmCraftClient for load_plf_native: records sessions and
    returns the fixture inspect."""

    def __init__(self, project, **kwargs):
        self.project = str(project)
        self.sessions = []
        self.created = None

    def new_project(self, name="PLF"):
        self.created = name

    def run(self, commands):
        self.sessions.append(commands)
        out = []
        for c in commands:
            if c.id == "file.import":
                out.append(CommandResult("file.import", True, {
                    "sequences": [1], "items": [], "errors": [],
                    "documents": [{"format": "OpenTimelineIO"}],
                    "linkedMedia": 1, "offlineMedia": [],
                }))
            else:
                out.append(CommandResult(c.id, True, {"ok": True}))
        return out

    def inspect(self):
        return json.loads(json.dumps(INSPECT))


def test_native_load_verifies_counts(tmp_path):
    media = tmp_path / "test_clip.mp4"
    media.write_bytes(b"\x00")
    plf = _make_plf()
    client = FakeClient(tmp_path / "out.fcproj")
    report = load_plf_native(plf, tmp_path / "out.fcproj",
                             base_dir=tmp_path, client=client)

    assert report.verified, report.warnings
    assert report.expected_shots == 2
    assert report.placed_shots == 2
    assert report.expected_markers == 2
    assert report.added_markers == 2
    assert report.sequence_item == 1
    assert Path(report.otio_path).is_file()
    # media was absolutised inside the OTIO source
    assert report.otio_path.endswith("out.source.otio")
    # words present -> SRT written and captions.import attempted
    assert Path(report.srt_path).is_file()
    assert report.captions_imported
    # session 2 opened the sequence before importing captions
    assert [c.id for c in client.sessions[-1]] == ["sequence.open", "captions.import"]
    # CLIPS file: was resolved against base_dir (no missing-media warning)
    assert not any("not found" in w for w in report.warnings)


def test_native_load_warns_on_missing_media(tmp_path):
    plf = _make_plf()
    client = FakeClient(tmp_path / "out.fcproj")
    report = load_plf_native(plf, tmp_path / "out.fcproj",
                             base_dir=tmp_path, client=client)
    assert any("not found" in w for w in report.warnings)
    assert report.verified  # structure still verifies


def test_native_load_no_words_no_captions_session(tmp_path):
    media = tmp_path / "test_clip.mp4"
    media.write_bytes(b"\x00")
    plf = _make_plf()
    plf.timeline = [e for e in plf.timeline if e.track != "W"]
    client = FakeClient(tmp_path / "out.fcproj")
    report = load_plf_native(plf, tmp_path / "out.fcproj",
                             base_dir=tmp_path, client=client)
    assert len(client.sessions) == 1  # only the OTIO import
    assert not report.srt_path
    assert report.captions_imported is False
    assert report.verified
