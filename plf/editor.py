"""Apply Model B INSTRUCTION edits to PLF text (PLAN.md Fase V2).

`apply_edits` takes the original PLF text plus the edit list that
`parse_instruction` produced (each edit: action ADD/MODIFY/DELETE with i/o/
track/line/old_value/new_value) and returns the edited PLF text.

Guarantees:
- unmodified entries keep their original formatting (the writer reuses each
  entry's raw line);
- ADD entries are inserted verbatim and the timeline is re-sorted by i:;
- unmatched edits are reported in ``skipped`` instead of raising;
- the result is re-validated (``validate`` + ``validate_cross_track``) and
  any problems land in ``warnings`` — an edit that satisfies the LLM but
  breaks the format should never silently produce an invalid file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .parser import parse, _parse_raw_line
from .schema import PLFEntry
from .validator import validate, validate_cross_track
from .writer import write, _format_entry

_TOL = 0.01  # seconds; model output rounds to 2 decimals

_TOKEN_RE = re.compile(r'\w+:"[^"]*"|"[^"]*"|\S+')


def _normalize_line(line: str) -> str:
    """Model B writes single spaces; PLF fields separate on 2+ spaces.

    Re-tokenize preserving quoted values (key:"with spaces" stays one token)
    and rejoin with the canonical double-space separator.
    """
    return "  ".join(_TOKEN_RE.findall(line))


@dataclass
class ApplyResult:
    text: str
    applied: int
    skipped: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _find_entry(timeline: list[PLFEntry], i, o, track=None) -> PLFEntry | None:
    for entry in timeline:
        if i is not None and abs(entry.i - i) > _TOL:
            continue
        if o is not None and abs(entry.o - o) > _TOL:
            continue
        if track is not None and entry.track != track:
            continue
        return entry
    return None


_ARROW_RE = re.compile(r"(\w+):([^\s:]+)\s*(?:→|->)\s*([^\s]+)")


def apply_edits(content: str, edits: list[dict]) -> ApplyResult:
    plf = parse(content)
    applied = 0
    skipped: list[dict] = []

    for edit in edits:
        action = str(edit.get("action", "")).upper()
        try:
            if action == "ADD":
                line = (edit.get("line") or "").strip()
                normalized = _normalize_line(line)
                parsed = _parse_raw_line(normalized)
                plf.timeline.append(
                    PLFEntry(
                        i=parsed["i"],
                        o=parsed["o"],
                        track=parsed["track"],
                        fields=parsed["fields"],
                        _raw_line=normalized,
                    )
                )
                applied += 1
                continue

            target = _find_entry(plf.timeline, edit.get("i"), edit.get("o"), edit.get("track"))
            if target is None:
                skipped.append({**edit, "error": "no matching entry"})
                continue

            if action == "DELETE":
                plf.timeline.remove(target)
                applied += 1
            elif action == "MODIFY":
                line = edit.get("line") or ""
                match = _ARROW_RE.search(line.replace("→", " → "))
                if match and edit.get("new_value") is None:
                    key, _old, new = match.group(1), match.group(2), match.group(3)
                elif edit.get("new_value") is not None and match:
                    key, new = match.group(1), str(edit["new_value"])
                else:
                    skipped.append({**edit, "error": "cannot parse key:new value from line"})
                    continue
                target.fields[key] = new.strip('"')
                target._raw_line = _format_entry(target)
                applied += 1
            else:
                skipped.append({**edit, "error": f"unknown action '{action}'"})
        except (ValueError, IndexError) as e:
            skipped.append({**edit, "error": str(e)})

    plf.timeline.sort(key=lambda entry: (entry.i, entry.o))
    max_o = max((entry.o for entry in plf.timeline), default=0.0)
    if max_o > plf.dur:
        plf.dur = round(max_o, 2)

    warnings: list[str] = []
    result = validate(plf)
    if not result.is_valid:
        warnings.extend(err.message for err in result.errors)
    cross = validate_cross_track(plf)
    if not cross.is_valid:
        warnings.extend(err.message for err in cross.errors)

    return ApplyResult(text=write(plf), applied=applied, skipped=skipped, warnings=warnings)
