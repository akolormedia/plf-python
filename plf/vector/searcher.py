from pathlib import Path
from .schema import SearchResult, SearchResults, VectorEntry

_embedding_model = None


def _get_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer("intfloat/multilingual-e5-large")
    return _embedding_model


def search(
    query: str,
    table,
    top_k: int = 10,
) -> SearchResults:
    results = SearchResults(query=query)

    model = _get_model()
    query_vector = model.encode(
        [query],
        normalize_embeddings=True,
        show_progress_bar=False,
    )[0].tolist()

    try:
        result = table.search(query_vector).limit(top_k).to_arrow()
    except Exception as e:
        return results

    for row in result.to_pylist():
        entry = VectorEntry(
            id=row["id"],
            track=row["track"],
            i=row["i"],
            o=row["o"],
            text=row["text"],
            plf_line=row["plf_line"],
            scene_id=row.get("scene_id", ""),
            proj=row.get("proj", ""),
            src=row.get("src", ""),
        )
        score = row.get("_distance", 0.0)
        results.results.append(SearchResult(
            entry=entry,
            distance=score,
        ))

    return results


def search_by_scene(
    query: str,
    table,
    scene_id: str,
    top_k: int = 10,
) -> SearchResults:
    results = SearchResults(query=query)

    model = _get_model()
    query_vector = model.encode(
        [query],
        normalize_embeddings=True,
        show_progress_bar=False,
    )[0].tolist()

    try:
        result = (
            table.search(query_vector)
            .where(f"scene_id = '{scene_id}'")
            .limit(top_k)
            .to_arrow()
        )
    except Exception:
        return results

    for row in result.to_pylist():
        entry = VectorEntry(
            id=row["id"],
            track=row["track"],
            i=row["i"],
            o=row["o"],
            text=row["text"],
            plf_line=row["plf_line"],
            scene_id=row.get("scene_id", ""),
            proj=row.get("proj", ""),
            src=row.get("src", ""),
        )
        results.results.append(SearchResult(
            entry=entry,
            distance=row.get("_distance", 0.0),
        ))

    return results


def search_by_track(
    query: str,
    table,
    track_type: str,
    top_k: int = 10,
) -> SearchResults:
    results = SearchResults(query=query)

    model = _get_model()
    query_vector = model.encode(
        [query],
        normalize_embeddings=True,
        show_progress_bar=False,
    )[0].tolist()

    try:
        result = (
            table.search(query_vector)
            .where(f"track = '{track_type}'")
            .limit(top_k)
            .to_arrow()
        )
    except Exception:
        return results

    for row in result.to_pylist():
        entry = VectorEntry(
            id=row["id"],
            track=row["track"],
            i=row["i"],
            o=row["o"],
            text=row["text"],
            plf_line=row["plf_line"],
            scene_id=row.get("scene_id", ""),
            proj=row.get("proj", ""),
            src=row.get("src", ""),
        )
        results.results.append(SearchResult(
            entry=entry,
            distance=row.get("_distance", 0.0),
        ))

    return results


def format_context(
    results: SearchResults,
    context_buffer: float = 30.0,
) -> str:
    if not results.results:
        return ""

    lines = []
    for r in results.results:
        i = r.entry.i
        o = r.entry.o

        scene_range = (
            f"SCENE: {r.entry.scene_id} "
            f"(i:{max(0, i - context_buffer):.2f}–"
            f"{o + context_buffer:.2f})"
        )
        lines.append(scene_range)
        lines.append(f"  {r.entry.plf_line}")

    return "\n".join(lines)
