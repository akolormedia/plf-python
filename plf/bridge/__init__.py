"""PLF <-> FilmCraft bridge (Phases 2 / FC-A).

Drives FilmCraft's headless engine to rebuild a PLF edit as a real, openable
``.fcproj``. Two load paths plus the sync-back side:

- :mod:`.client` — the JSONL command channel,
- :mod:`.convert` — PLF -> ``timeline.*`` commands (F2, command rebuild),
- :func:`.bridge.load_plf_into_filmcraft` — the one-call command entry point,
- :mod:`.native` — FC-A native load: enriched OTIO -> single ``file.import``,
- :mod:`.reverse` — FC-A reverse sync: ``sequence.inspect`` -> PLF,
- :mod:`.dirty` — §3.4 dirty flags between original and synced timeline,
- :mod:`.generate` — run the generation pipeline over a project's clips.

CLI: ``python -m plf.bridge --help``.
"""
from .client import (
    FilmCraftClient,
    Command,
    CommandResult,
    BridgeError,
    TICKS_PER_SECOND,
)
from .convert import (
    sec_to_ticks,
    referenced_clip_files,
    build_import_commands,
    build_sequence_command,
    build_place_commands,
    build_marker_commands,
    build_edit_commands,
)
from .bridge import load_plf_into_filmcraft, BridgeReport
from .native import load_plf_native, NativeReport
from .reverse import inspect_to_plf, sync_project
from .dirty import diff_plf, DiffReport, DirtySegment
from .generate import generate_plfs

__all__ = [
    "FilmCraftClient",
    "Command",
    "CommandResult",
    "BridgeError",
    "TICKS_PER_SECOND",
    "sec_to_ticks",
    "referenced_clip_files",
    "build_import_commands",
    "build_sequence_command",
    "build_place_commands",
    "build_marker_commands",
    "build_edit_commands",
    "load_plf_into_filmcraft",
    "BridgeReport",
    "load_plf_native",
    "NativeReport",
    "inspect_to_plf",
    "sync_project",
    "diff_plf",
    "DiffReport",
    "DirtySegment",
    "generate_plfs",
]
