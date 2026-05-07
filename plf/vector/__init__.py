from .schema import VectorEntry, SearchResult, SearchResults
from .indexer import embed_entries, entry_to_text
from .searcher import search, search_by_scene, search_by_track, format_context


def create_index(
    plf,
    db_path: str = "./.lancedb",
    table_name: str = "plf_entries",
    embedding_model: str = "multilingual-e5-large",
) -> object:
    try:
        import lancedb
    except ImportError:
        raise ImportError(
            "LanceDB is required. Install with:\n"
            "  pip install lancedb"
        )

    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(f"intfloat/{embedding_model}")
    except ImportError:
        raise ImportError(
            "sentence-transformers is required. Install with:\n"
            "  pip install sentence-transformers"
        )

    db = lancedb.connect(db_path)
    entries = embed_entries(plf)

    texts = [e.text for e in entries]
    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=False,
    )

    rows = []
    for entry, vector in zip(entries, embeddings):
        rows.append({
            "id": entry.id,
            "track": entry.track,
            "i": entry.i,
            "o": entry.o,
            "text": entry.text,
            "plf_line": entry.plf_line,
            "scene_id": entry.scene_id,
            "proj": entry.proj,
            "src": entry.src,
            "vector": vector.tolist(),
        })

    try:
        db.drop_table(table_name)
    except Exception:
        pass

    table = db.create_table(table_name, rows)
    return table


def load_table(
    db_path: str = "./.lancedb",
    table_name: str = "plf_entries",
) -> object:
    try:
        import lancedb
    except ImportError:
        raise ImportError(
            "LanceDB is required. Install with:\n"
            "  pip install lancedb"
        )

    db = lancedb.connect(db_path)
    return db.open_table(table_name)


def query_plf(
    plf,
    query: str,
    table_name: str = "plf_entries",
    db_path: str = "./.lancedb",
    top_k: int = 10,
) -> SearchResults:
    table = create_index(plf, db_path, table_name)
    return search(query, table, top_k=top_k)
