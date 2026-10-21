"""Dirty-flag diff between an original PLF and the timeline as synced back.

Implements CLAUDE.md §3.4 for the FilmCraft loop:

    structural edit (move clip, cut)  -> red solid  -> regenerate on save
    metadata edit  (fix TAG label)    -> red dashed -> direct write, no model

The original PLF carries the semantic tracks (``T:W``, ``ACT`` …) the editor
never sees, so only picture (``T:SH``) and markers (``T:TAG``) are compared;
everything else is untouched by construction.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..schema import PLFEntry, PLFFile

# Time slop (seconds) before a difference counts as a real edit. PLF times
# round to 2 decimals and FilmCraft ticks convert back without drift, but
# editors nudge by frames at boundaries.
EPS = 0.02


@dataclass
class DirtySegment:
    """One changed region, classified per §3.4."""

    kind: str                 # "structural" | "metadata"
    track: str                # "SH" | "TAG"
    i: float
    o: float
    reason: str
    original: PLFEntry | None = None
    synced: PLFEntry | None = None

    @property
    def regenerate(self) -> bool:
        """§3.4: structural changes trigger Model A on save; metadata doesn't."""
        return self.kind == "structural"


@dataclass
class DiffReport:
    segments: list[DirtySegment] = field(default_factory=list)

    @property
    def structural(self) -> list[DirtySegment]:
        return [s for s in self.segments if s.kind == "structural"]

    @property
    def metadata(self) -> list[DirtySegment]:
        return [s for s in self.segments if s.kind == "metadata"]

    @property
    def clean(self) -> bool:
        return not self.segments


def _span_key(e: PLFEntry) -> tuple[str, str]:
    """Match identity for a shot: its raw source span (media + window)."""
    return (e.track, e.fields.get("raw", ""))


def _match_shots(original: list[PLFEntry], synced: list[PLFEntry]):
    """Pair original/synced T:SH by raw span, then by timeline overlap.

    Yields ``(orig, sync | None)`` pairs plus leftover synced entries.
    """
    pairs = []
    used: set[int] = set()
    for o in original:
        hit = next(
            (j for j, s in enumerate(synced)
             if j not in used and _span_key(o) == _span_key(s)
             and _span_key(o)[1] != ""),
            None,
        )
        if hit is None:
            hit = next(
                (j for j, s in enumerate(synced)
                 if j not in used and s.i < o.o and s.o > o.i),
                None,
            )
        if hit is not None:
            used.add(hit)
            pairs.append((o, synced[hit]))
        else:
            pairs.append((o, None))
    leftovers = [s for j, s in enumerate(synced) if j not in used]
    return pairs, leftovers


def _match_tags(original: list[PLFEntry], synced: list[PLFEntry]):
    """Pair original/synced T:TAG by label, then by overlapping time."""
    pairs = []
    used: set[int] = set()
    for o in original:
        lbl = o.fields.get("lbl", "")
        hit = next(
            (j for j, s in enumerate(synced)
             if j not in used and s.fields.get("lbl", "") == lbl),
            None,
        )
        if hit is None:
            hit = next(
                (j for j, s in enumerate(synced)
                 if j not in used and s.i < o.o and s.o > o.i),
                None,
            )
        if hit is not None:
            used.add(hit)
            pairs.append((o, synced[hit]))
        else:
            pairs.append((o, None))
    leftovers = [s for j, s in enumerate(synced) if j not in used]
    return pairs, leftovers


def diff_plf(original: PLFFile, synced: PLFFile) -> DiffReport:
    """Compare the original PLF against the timeline synced back from the NLE."""
    report = DiffReport()

    o_shots = [e for e in original.timeline if e.track == "SH"]
    s_shots = [e for e in synced.timeline if e.track == "SH"]
    pairs, added = _match_shots(o_shots, s_shots)
    for o, s in pairs:
        if s is None:
            report.segments.append(DirtySegment(
                kind="structural", track="SH", i=o.i, o=o.o,
                reason="shot removed in the editor", original=o,
            ))
            continue
        moved = abs(o.i - s.i) > EPS or abs(o.o - s.o) > EPS
        recut = o.fields.get("raw", "") != s.fields.get("raw", "")
        if moved and recut:
            reason = f"shot moved and re-cut ({o.fields.get('raw','')} -> {s.fields.get('raw','')})"
        elif moved:
            reason = f"shot moved {o.i:.2f}-{o.o:.2f} -> {s.i:.2f}-{s.o:.2f}"
        elif recut:
            reason = f"source window changed ({o.fields.get('raw','')} -> {s.fields.get('raw','')})"
        else:
            continue
        report.segments.append(DirtySegment(
            kind="structural", track="SH", i=o.i, o=o.o, reason=reason,
            original=o, synced=s,
        ))
    for s in added:
        report.segments.append(DirtySegment(
            kind="structural", track="SH", i=s.i, o=s.o,
            reason="shot added in the editor", original=None, synced=s,
        ))

    o_tags = [e for e in original.timeline if e.track == "TAG"]
    s_tags = [e for e in synced.timeline if e.track == "TAG"]
    tpairs, tadded = _match_tags(o_tags, s_tags)
    for o, s in tpairs:
        if s is None:
            report.segments.append(DirtySegment(
                kind="structural", track="TAG", i=o.i, o=o.o,
                reason=f"marker {o.fields.get('lbl','')!r} deleted", original=o,
            ))
            continue
        moved = abs(o.i - s.i) > EPS or abs(o.o - s.o) > EPS
        renamed = o.fields.get("lbl", "") != s.fields.get("lbl", "")
        if moved:
            report.segments.append(DirtySegment(
                kind="structural", track="TAG", i=o.i, o=o.o,
                reason=f"marker {o.fields.get('lbl','')!r} moved "
                       f"{o.i:.2f}-{o.o:.2f} -> {s.i:.2f}-{s.o:.2f}",
                original=o, synced=s,
            ))
        elif renamed:
            report.segments.append(DirtySegment(
                kind="metadata", track="TAG", i=o.i, o=o.o,
                reason=f"marker renamed {o.fields.get('lbl','')!r} -> {s.fields.get('lbl','')!r}",
                original=o, synced=s,
            ))
    for s in tadded:
        report.segments.append(DirtySegment(
            kind="structural", track="TAG", i=s.i, o=s.o,
            reason=f"marker {s.fields.get('lbl','')!r} added in the editor",
            original=None, synced=s,
        ))

    report.segments.sort(key=lambda d: (d.i, d.track))
    return report
