"""PLF <-> FilmCraft bridge (Phase 2).

Drives FilmCraft's headless engine to rebuild a PLF edit as a real, openable
``.fcproj``. See :mod:`.client` for the command channel, :mod:`.convert` for the
PLF -> command mapping, and :func:`.bridge.load_plf_into_filmcraft` for the
one-call entry point.
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
]
