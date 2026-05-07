from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PLFCastMember:
    id: str
    nombre: str
    desc: str


@dataclass
class PLFScene:
    id: str
    loc: str
    time: str
    act: int
    desc: str


@dataclass
class PLFClip:
    id: str
    file: str
    tc: str


@dataclass
class PLFEntry:
    i: float
    o: float
    track: str
    fields: dict = field(default_factory=dict)
    _raw_line: str = ""


@dataclass
class PLFFile:
    version: str = "1.0"
    proj: str = ""
    fps: int = 24
    ar: str = "16:9"
    dur: float = 0.0
    src: str = "editado"
    ref: Optional[str] = None
    ctx: str = ""
    cast: list = field(default_factory=list)
    scenes: list = field(default_factory=list)
    clips: list = field(default_factory=list)
    timeline: list = field(default_factory=list)
