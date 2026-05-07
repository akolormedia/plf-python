from dataclasses import dataclass, field
from typing import Optional


@dataclass
class VectorEntry:
    id: str
    track: str
    i: float
    o: float
    text: str
    plf_line: str
    scene_id: str = ""
    proj: str = ""
    src: str = ""


@dataclass
class SearchResult:
    entry: VectorEntry
    score: float = 0.0
    distance: float = 0.0


@dataclass
class SearchResults:
    query: str
    results: list[SearchResult] = field(default_factory=list)

    def best(self) -> Optional[SearchResult]:
        return self.results[0] if self.results else None

    def all_i_o(self) -> list[tuple[float, float]]:
        return [(r.entry.i, r.entry.o) for r in self.results]

    def plf_lines(self) -> list[str]:
        return [r.entry.plf_line for r in self.results]


LANCE_TABLE_SCHEMA = {
    "id": "string",
    "track": "string",
    "i": "float",
    "o": "float",
    "text": "string",
    "plf_line": "string",
    "scene_id": "string",
    "proj": "string",
    "src": "string",
    "vector": "vector(1024)",
}
