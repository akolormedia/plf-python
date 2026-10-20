"""High-level bridge: load a parsed PLF file into a FilmCraft project.

Orchestrates the client and the command builders across FilmCraft's session
boundary. The engine only keeps state (open sequence, imported items) within a
single CLI invocation, so the flow runs in two sessions:

1. **Setup** — import the referenced media, create the sequence. Read the
   project tree back to resolve ``CLPxxx`` -> item id (by filename) and find
   the new sequence's item id.
2. **Edit** — open the sequence, place every ``T:SH``, add every ``T:TAG``.

Both sessions save the project, so the result is a persistent ``.fcproj`` the
user can open in the FilmCraft app.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..schema import PLFFile
from .client import FilmCraftClient, Command, BridgeError
from .convert import (
    build_import_commands,
    build_sequence_command,
    build_edit_commands,
    referenced_clip_files,
)


@dataclass
class BridgeReport:
    """What a bridge load did, for logging and tests."""

    project: str
    imported_files: list[str] = field(default_factory=list)
    clip_to_item: dict[str, int] = field(default_factory=dict)
    sequence_item: int | None = None
    placed_shots: int = 0
    added_markers: int = 0


def _index_project_tree(tree: dict) -> tuple[dict[str, int], list[int]]:
    """Return ``(filename -> item id, sequence item ids)`` from ``inspect project``."""
    name_to_item: dict[str, int] = {}
    sequence_items: list[int] = []

    def walk(node: dict) -> None:
        ntype = node.get("type")
        name = node.get("name", "")
        item = node.get("item")
        if item is not None:
            if ntype == "Sequence":
                sequence_items.append(item)
            elif name:
                name_to_item[name] = item
        for child in node.get("children", []) or []:
            walk(child)

    # ``inspect project`` is flat (``{root, ...}``); bare ``inspect`` wraps the
    # tree under a ``project`` key (``{project: {root}, sequence: {...}}``).
    root = tree.get("root") or tree.get("project", {}).get("root", tree)
    walk(root)
    return name_to_item, sequence_items


def load_plf_into_filmcraft(
    plf: PLFFile,
    project: str | Path,
    cli_path: str | None = None,
    sequence_name: str | None = None,
) -> BridgeReport:
    """Rebuild a PLF edit as a FilmCraft project.

    Parameters
    ----------
    plf:
        A parsed PLF file (from :func:`plf.parse`).
    project:
        Path of the ``.fcproj`` to create/overwrite.
    cli_path:
        Override the ``filmcraft-cli`` binary location.
    sequence_name:
        Name for the new sequence (defaults to the PLF project name).
    """
    client = FilmCraftClient(project, **({"cli_path": cli_path} if cli_path else {}))
    report = BridgeReport(project=str(project))

    # -- Session 1: new project, import media, create the sequence ------------
    client.new_project(name=plf.proj or "PLF")

    files = referenced_clip_files(plf)
    report.imported_files = files
    setup: list[Command] = [build_import_commands(plf)]
    # Create the sequence in the same session so it is active for later edits.
    seq_cmd = build_sequence_command(plf, sequence_name)
    setup.append(seq_cmd)

    results = client.run(setup)
    for r in results:
        r.value  # raises BridgeError on failure

    # -- Resolve ids from the project tree ------------------------------------
    tree = client.inspect()
    name_to_item, sequence_items = _index_project_tree(tree)
    report.clip_to_item = {
        clip_id: name_to_item[Path(filename).name]
        for clip_id, filename in _clip_file_map(plf).items()
        if Path(filename).name in name_to_item
    }
    if not sequence_items:
        raise BridgeError("sequence was not created (no Sequence in project tree)")
    report.sequence_item = sequence_items[-1]

    # -- Session 2: open the sequence, place shots, add markers ---------------
    edits = build_edit_commands(plf, report.sequence_item, report.clip_to_item)
    edit_results = client.run(edits)
    for r in edit_results:
        r.value
        if r.id == "timeline.place":
            report.placed_shots += 1
        elif r.id == "markers.add":
            report.added_markers += 1

    return report


def _clip_file_map(plf: PLFFile) -> dict[str, str]:
    """``CLPxxx`` -> filename for every clip in the PLF header."""
    return {c.id: c.file for c in plf.clips}
