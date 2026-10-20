"""Tests for plf.editor — applying Model B instruction edits to PLF text."""

from plf import apply_edits, parse

BASE = """PLF1.0 proj:test  fps:24  ar:16:9  dur:10.00  src:bruto
ctx:"prueba"

CAST:
  A1  nombre:Ana  desc:mujer traje

SCENES:
  SC01  loc:oficina  time:dia  act:1  desc:"oficina clara"

CLIPS:
  CLP001  file:test.mp4  tc:00:00:00:00

i:0.00    o:5.00    T:SH   id:s01  shot:MS  loc:int-office  trans_i:CT  trans_o:CT  cam:sta  mood:neu  raw:CLP001@0.00-5.00
i:5.00    o:10.00   T:SH   id:s02  shot:LS  loc:int-office  trans_i:CT  trans_o:CT  cam:sta  mood:neu  raw:CLP001@5.00-10.00
i:0.00    o:5.00    T:ACT  subj:A1  act:wait  arc:neutral
"""


def test_add_inserts_and_round_trips():
    result = apply_edits(BASE, [
        {"action": "ADD", "i": 10.0, "o": 12.0, "track": "TAG",
         "line": "i:10.00 o:12.00 T:TAG lbl:interior"},
    ])
    assert result.applied == 1
    assert result.skipped == []
    assert "lbl:interior" in result.text
    # new entry lands last (sorted by i:)
    lines = [l for l in result.text.splitlines() if l.strip().startswith("i:")]
    assert "TAG" in lines[-1]
    # round-trips
    plf = parse(result.text)
    tags = [e for e in plf.timeline if e.track == "TAG"]
    assert len(tags) == 1 and tags[0].fields["lbl"] == "interior"


def test_delete_removes_matching_entry():
    result = apply_edits(BASE, [
        {"action": "DELETE", "i": 5.0, "o": 10.0, "track": "SH", "line": ""},
    ])
    assert result.applied == 1
    plf = parse(result.text)
    shots = [e for e in plf.timeline if e.track == "SH"]
    assert len(shots) == 1 and shots[0].i == 0.0


def test_modify_changes_field_and_rewrites_line():
    result = apply_edits(BASE, [
        {"action": "MODIFY", "i": 0.0, "o": 5.0, "track": "SH",
         "line": "i:0.00 o:5.00 mood:neu→ale", "old_value": "neu", "new_value": "ale"},
    ])
    assert result.applied == 1
    plf = parse(result.text)
    shot = [e for e in plf.timeline if e.track == "SH" and e.i == 0.0][0]
    assert shot.fields["mood"] == "ale"
    assert "mood:ale" in shot._raw_line


def test_modify_ascii_arrow():
    result = apply_edits(BASE, [
        {"action": "MODIFY", "i": 5.0, "o": 10.0, "line": "i:5.00 o:10.00 cam:sta->pan"},
    ])
    assert result.applied == 1
    assert "cam:pan" in result.text


def test_unmatched_edit_is_skipped_not_raised():
    result = apply_edits(BASE, [
        {"action": "DELETE", "i": 99.0, "o": 100.0, "track": "SH", "line": ""},
        {"action": "BOGUS", "i": 0.0, "o": 1.0, "line": ""},
        {"action": "ADD", "line": "esto no es una linea"},
    ])
    assert result.applied == 0
    assert len(result.skipped) == 3
    assert all("error" in s for s in result.skipped)


def test_dur_extends_when_edit_goes_beyond():
    result = apply_edits(BASE, [
        {"action": "ADD", "line": "i:10.00 o:14.50 T:TAG lbl:final"},
    ])
    plf = parse(result.text)
    assert plf.dur == 14.50


def test_cross_track_violation_becomes_warning():
    # T:ACT referencing a CAST member that doesn't exist
    result = apply_edits(BASE, [
        {"action": "ADD", "line": "i:5.00 o:8.00 T:ACT subj:ZZ act:run arc:neutral"},
    ])
    assert result.applied == 1
    assert any("ZZ" in w for w in result.warnings)


def test_valid_edit_produces_no_warnings():
    result = apply_edits(BASE, [
        {"action": "MODIFY", "i": 0.0, "o": 5.0, "line": "i:0.00 o:5.00 mood:neu→sad"},
    ])
    assert result.warnings == []
    assert result.skipped == []


def test_unmodified_entries_keep_original_formatting():
    result = apply_edits(BASE, [
        {"action": "ADD", "line": "i:0.00 o:1.00 T:USR type:q \"¿quién?\""},
    ])
    # the original T:SH line survives verbatim (raw: field with spaces intact)
    assert "raw:CLP001@0.00-5.00" in result.text


def test_add_line_single_spaces_and_quoted_values_normalized():
    """Model B writes single spaces; apply_edits canonicalizes the line."""
    result = apply_edits(BASE, [
        {"action": "ADD",
         "line": 'i:0.00 o:1.00 T:EL sh:s01 obj:"carta abierta" attr:"objeto en mano"'},
    ])
    assert result.applied == 1
    plf = parse(result.text)
    el = [e for e in plf.timeline if e.track == "EL"][0]
    assert el.fields["obj"] == "carta abierta"
    assert el.fields["attr"] == "objeto en mano"
    assert "  " in el._raw_line  # canonical double-space separators
