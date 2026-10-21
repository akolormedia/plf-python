"""PLF ``T:W`` entries -> SRT sidecar.

FilmCraft's OTIO importer treats any non-Audio OTIO track as *Video*
(``interchange/src/otio.rs``), so caption tracks in the OTIO would corrupt a
native load. The supported path for semantic tracks is FilmCraft's dedicated
``captions.import`` command, which accepts an SRT/VTT sidecar — this module
builds one from the PLF's word track (``T:W``), grouping consecutive words
into readable cues.
"""
from __future__ import annotations

from .schema import PLFEntry

# Cue-building rules (timings stay exact to the words; only grouping changes).
MAX_GAP = 0.35      # seconds between words that still belong to one cue
MAX_CHARS = 42      # wrap the cue text around here
MAX_DURATION = 5.0  # seconds


def _ts(seconds: float) -> str:
    """Seconds -> ``HH:MM:SS,mmm`` with a single rounding at the boundary."""
    ms = round(seconds * 1000)
    if ms < 0:
        ms = 0
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _wrap(words: list[str]) -> str:
    """Join words, breaking into at most two lines near MAX_CHARS."""
    lines: list[str] = []
    current = ""
    for w in words:
        candidate = f"{current} {w}".strip()
        if current and len(candidate) > MAX_CHARS:
            lines.append(current)
            current = w
        else:
            current = candidate
    if current:
        lines.append(current)
    return "\n".join(lines)


def words_to_srt(entries: list[PLFEntry]) -> str:
    """Build an SRT document from ``T:W`` entries (other tracks ignored).

    Consecutive words group into one cue while they share a speaker, the gap
    between them stays under ``MAX_GAP`` and the cue stays short. Returns an
    empty string when there are no word entries.
    """
    words = [e for e in entries if e.track == "W" and e.fields.get("_word")]
    if not words:
        return ""

    cues: list[tuple[float, float, str, str]] = []  # (start, end, spk, text)
    current: list[tuple[float, float, str, str]] = []

    def flush() -> None:
        if not current:
            return
        start = current[0][0]
        end = max(current[-1][1], start)
        spk = current[0][2]
        cues.append((start, end, spk, _wrap([w for *_, w in current])))
        current.clear()

    for e in words:
        spk = e.fields.get("spk", "")
        word = e.fields["_word"]
        if current:
            prev = current[-1]
            gap = e.i - prev[1]
            span = e.i - current[0][0]
            if spk != prev[2] or gap > MAX_GAP or span > MAX_DURATION:
                flush()
        current.append((e.i, e.o, spk, word))
    flush()

    parts = []
    for n, (start, end, spk, text) in enumerate(cues, 1):
        # A one-word burst gets a readable minimum length.
        if end - start < 0.2:
            end = start + 0.2
        parts.append(f"{n}\n{_ts(start)} --> {_ts(end)}\n{text}\n")
    return "\n".join(parts)
