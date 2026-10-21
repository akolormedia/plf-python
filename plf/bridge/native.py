"""Native load: PLF -> enriched OTIO -> one ``file.import`` in FilmCraft.

The Phase F2 bridge (:mod:`.bridge`) rebuilds an edit command by command
(``timeline.place`` per shot). The FC-A "native" path plays FilmCraft's own
importer instead: :func:`plf.otio_convert.plf_to_otio` materialises the
picture edit (``T:SH`` clips with exact source ranges) and the ``T:TAG``
markers (verified surviving ``file.exportOtio`` and ``file.import`` at
commit 105c09b — the spike's gap #1 is obsolete), then a single
``file.import`` loads the whole thing in one session.

Semantic tracks (``T:W``, ``T:DLG`` …) are *not* carried as OTIO caption
tracks: FilmCraft's OTIO reader classifies every non-Audio track as Video
(``interchange/src/otio.rs``), which would corrupt the load. Instead the
word track is written as an SRT sidecar and pulled in through FilmCraft's
dedicated ``captions.import`` so it lands as a real caption track.

Media paths are absolutised against ``base_dir`` first: an OTIO built from
relative ``CLIPS file:`` names only resolves if the importer's cwd happens
to match, which we don't control.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path

from ..otio_convert import plf_to_otio, save_otio
from ..schema import PLFFile
from ..srt import words_to_srt
from .client import FilmCraftClient, Command


@dataclass
class NativeReport:
    """What the native load did, for logging and tests."""

    project: str
    otio_path: str = ""
    srt_path: str = ""
    expected_shots: int = 0
    expected_markers: int = 0
    sequence_item: int | None = None
    placed_shots: int = 0
    added_markers: int = 0
    captions_imported: bool = False
    verified: bool = False
    warnings: list[str] = field(default_factory=list)


def _absolutise_media(plf: PLFFile, base_dir: Path | None) -> PLFFile:
    """Return a copy of ``plf`` whose ``CLIPS file:`` values are absolute.

    Unresolvable files keep their original value; the import report then
    shows up offline via ``offlineMedia`` and we surface a warning.
    """
    plf = copy.deepcopy(plf)
    bases = [b for b in (base_dir, Path.cwd()) if b]
    for clip in plf.clips:
        p = Path(clip.file)
        if p.is_absolute():
            continue
        for base in bases:
            if (base / p).is_file():
                clip.file = str((base / p).resolve())
                break
    return plf


def _count_project_captions(project: str | Path) -> int | None:
    """Total caption cues stored in a saved ``.fcproj`` (``None`` if the
    project file is absent or unreadable — e.g. a fake client in tests)."""
    import json

    try:
        with open(project, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    total = 0
    for item in (data.get("project") or {}).get("items", {}).values():
        kind = item.get("kind") or {}
        seq = kind.get("Sequence")
        if not isinstance(seq, dict):
            continue
        for track in seq.get("caption_tracks") or []:
            total += len(track.get("captions") or [])
    return total


def _sequence_item_from_tree(tree: dict) -> int | None:
    found: list[int] = []

    def walk(node: dict) -> None:
        if node.get("type") == "Sequence" and node.get("item") is not None:
            found.append(node["item"])
        for child in node.get("children", []) or []:
            walk(child)

    root = tree.get("root") or tree.get("project", {}).get("root", tree)
    walk(root)
    return found[-1] if found else None


def load_plf_native(
    plf: PLFFile,
    project: str | Path,
    cli_path: str | None = None,
    base_dir: str | Path | None = None,
    client: FilmCraftClient | None = None,
) -> NativeReport:
    """Rebuild a PLF edit as a FilmCraft project via a single OTIO import.

    Parameters
    ----------
    plf:
        A parsed PLF file (from :func:`plf.parse`).
    project:
        Path of the ``.fcproj`` to create/overwrite.
    cli_path:
        Override the ``filmcraft-cli`` binary location.
    base_dir:
        Directory to resolve relative ``CLIPS file:`` names against
        (defaults to the current working directory).
    client:
        Inject a pre-built client (tests); otherwise a
        :class:`FilmCraftClient` is created for ``project``.
    """
    project = Path(project)
    report = NativeReport(project=str(project))
    client = client or FilmCraftClient(
        project, **({"cli_path": cli_path} if cli_path else {})
    )

    # -- Build the enriched OTIO next to the project --------------------------
    src = _absolutise_media(plf, Path(base_dir) if base_dir else None)
    otio_path = project.with_name(project.stem + ".source.otio")
    save_otio(plf_to_otio(src), str(otio_path))
    report.otio_path = str(otio_path)
    missing = [c.file for c in src.clips if not Path(c.file).is_file()]
    if missing:
        report.warnings.append(f"media not found (will import offline): {missing}")

    report.expected_shots = sum(
        1 for e in plf.timeline if e.track == "SH" and e.fields.get("raw")
    )
    report.expected_markers = sum(1 for e in plf.timeline if e.track == "TAG")

    # -- Session 1: fresh project + the OTIO import ---------------------------
    client.new_project(name=plf.proj or "PLF")
    results = client.run([Command("file.import", {"paths": [str(otio_path)]})])
    res = results[0].value or {}
    seq_items = res.get("sequences") or res.get("items") or []
    if not seq_items:
        raise RuntimeError(f"OTIO import produced no sequence: {res!r}")
    report.sequence_item = int(seq_items[0])
    offline = res.get("offlineMedia") or []
    if offline:
        report.warnings.append(f"offline media after import: {offline}")

    # -- Session 2 (only when there is dialogue): SRT caption track -----------
    srt = words_to_srt(plf.timeline)
    if srt:
        srt_path = project.with_name(project.stem + ".source.srt")
        srt_path.write_text(srt, encoding="utf-8")
        report.srt_path = str(srt_path)
        try:
            cap = client.run([
                Command("sequence.open", {"item": report.sequence_item}),
                Command("captions.import", {"path": str(srt_path)}),
            ])
            cap_res = cap[-1].value
            report.captions_imported = True
            if isinstance(cap_res, dict) and cap_res.get("errors"):
                report.captions_imported = False
                report.warnings.append(f"captions.import: {cap_res['errors']}")
            # Confirm the track really landed in the saved project (the
            # command reports ok even when content detection silently no-ops).
            landed = _count_project_captions(project)
            if landed is not None and landed == 0:
                report.captions_imported = False
                report.warnings.append(
                    "captions.import reported ok but the project has no cues"
                )
        except Exception as e:  # captions are best-effort; picture+markers stand
            report.captions_imported = False
            report.warnings.append(f"captions.import failed: {e}")

    # -- Verify: read the sequence back ---------------------------------------
    data = client.inspect()
    seq = data.get("sequence") or {}
    report.placed_shots = sum(
        len(t.get("items") or []) for t in seq.get("video") or []
    )
    report.added_markers = len(seq.get("markers") or [])
    if report.sequence_item is None:
        report.sequence_item = _sequence_item_from_tree(data)

    report.verified = (
        report.placed_shots == report.expected_shots
        and report.added_markers == report.expected_markers
    )
    if not report.verified:
        report.warnings.append(
            "verify mismatch: "
            f"shots {report.placed_shots}/{report.expected_shots}, "
            f"markers {report.added_markers}/{report.expected_markers}"
        )
    return report
