"""Tests for plf.vector — pure functions and search with a mocked embedding model.

The heavy embedding model (multilingual-e5-large) is never downloaded here.
search() is tested with a fake model and a fake LanceDB table.
"""

from pathlib import Path

from plf import parse
from plf.vector import entry_to_text, embed_entries
from plf.vector.searcher import search, format_context
from plf.vector.schema import VectorEntry, SearchResult, SearchResults

EXAMPLES_DIR = Path(__file__).parent.parent.parent / "plf-spec" / "examples"


def load_plf(name: str):
    text = (EXAMPLES_DIR / name).read_text(encoding="utf-8")
    return parse(text)


class FakeModel:
    def encode(self, texts, normalize_embeddings=True, show_progress_bar=False):
        import numpy as np
        return np.zeros((len(texts), 4), dtype="float32")


class FakeTable:
    def __init__(self, rows):
        self._rows = rows

    def search(self, query_vector):
        return self

    def limit(self, n):
        self._rows = self._rows[:n]
        return self

    def to_arrow(self):
        rows = self._rows

        class FakeArrow:
            def to_pylist(self):
                return rows

        return FakeArrow()


def test_entry_to_text_shot():
    plf = load_plf("sol_en_playa.edit.plf")
    shot = next(e for e in plf.timeline if e.track == "SH")
    text = entry_to_text(shot)
    assert text.startswith("Shot s01:")
    assert "Location:" in text or "Camera:" in text


def test_entry_to_text_action():
    plf = load_plf("sol_en_playa.edit.plf")
    act = next(e for e in plf.timeline if e.track == "ACT")
    text = entry_to_text(act)
    assert text.startswith("Action:")
    assert "Duration:" in text


def test_entry_to_text_tag():
    plf = load_plf("la_ultima_vez.edit.plf")
    tag = next(e for e in plf.timeline if e.track == "TAG")
    text = entry_to_text(tag)
    assert text.startswith("Tag:")
    assert "Range:" in text


def test_embed_entries_matches_timeline():
    plf = load_plf("sol_en_playa.edit.plf")
    entries = embed_entries(plf)
    assert len(entries) == len(plf.timeline)
    assert all(isinstance(e, VectorEntry) for e in entries)
    assert all(e.text for e in entries)


def test_embed_entries_scene_id():
    plf = load_plf("sol_en_playa.edit.plf")
    entries = embed_entries(plf)
    with_scene = [e for e in entries if e.scene_id]
    assert len(with_scene) > 0
    assert all(e.scene_id.startswith("SC") for e in with_scene)


def test_search_with_mocked_model(monkeypatch):
    import plf.vector.searcher as searcher
    monkeypatch.setattr(searcher, "_get_model", lambda: FakeModel())

    plf = load_plf("sol_en_playa.edit.plf")
    entries = embed_entries(plf)
    rows = [
        {
            "id": e.id, "track": e.track, "i": e.i, "o": e.o,
            "text": e.text, "plf_line": e.plf_line,
            "scene_id": e.scene_id, "proj": e.proj, "src": e.src,
            "_distance": float(idx),
        }
        for idx, e in enumerate(entries[:5])
    ]
    table = FakeTable(rows)

    results = search("playa", table, top_k=5)
    assert isinstance(results, SearchResults)
    assert results.query == "playa"
    assert len(results.results) == 5
    assert results.best().entry.id == entries[0].id
    assert results.all_i_o()[0] == (entries[0].i, entries[0].o)


def test_format_context():
    entry = VectorEntry(
        id="SH_0.00", track="SH", i=0.0, o=4.12,
        text="Shot s01: ELS.", plf_line="i:0.00 o:4.12 T:SH id:s01",
        scene_id="SC01",
    )
    results = SearchResults(query="q", results=[SearchResult(entry=entry)])
    ctx = format_context(results, context_buffer=30.0)
    assert "SCENE: SC01" in ctx
    assert "i:0.00" in ctx  # max(0, 0-30) = 0
    assert entry.plf_line in ctx


def test_format_context_empty():
    results = SearchResults(query="q")
    assert format_context(results) == ""
