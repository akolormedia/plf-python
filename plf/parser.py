import re
from .schema import PLFFile, PLFCastMember, PLFScene, PLFClip, PLFEntry


_FIELD_SEP = re.compile(r"\s{2,}")

VALID_TRACKS = {"SCN", "SH", "ACT", "EL", "AMB", "MUS", "DLG", "W", "TAG", "USR"}


def _parse_kv_fields(fields: list[str]) -> dict:
    result = {}
    for field in fields:
        if ":" not in field:
            continue
        key, _, value = field.partition(":")
        value = value.strip('"')
        result[key] = value
    return result


def _parse_quoted_text(field: str) -> str:
    return field.strip('"')


def _parse_raw_line(line: str) -> dict:
    parts = _FIELD_SEP.split(line.rstrip())
    kw = {}

    i_raw = parts[0]
    o_raw = parts[1]
    t_raw = parts[2]

    kw["i"] = float(i_raw.split(":")[1])
    kw["o"] = float(o_raw.split(":")[1])
    track = t_raw.split(":")[1]

    if track not in VALID_TRACKS:
        raise ValueError(f"Invalid track type: {track}")

    remaining = parts[3:]
    fields_dict = {}
    trailing_text = ""

    for field in remaining:
        if field.startswith('"'):
            trailing_text = _parse_quoted_text(field)
        elif ":" in field:
            key, _, value = field.partition(":")
            value = value.strip('"')
            fields_dict[key] = value

    if trailing_text:
        if track == "W":
            fields_dict["_word"] = trailing_text
        elif track == "USR":
            fields_dict["_text"] = trailing_text

    return {
        "i": kw["i"],
        "o": kw["o"],
        "track": track,
        "fields": fields_dict,
    }


def parse(text: str) -> PLFFile:
    lines = text.split("\n")
    plf = PLFFile()

    header_lines = []
    timeline_lines = []
    in_timeline = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("i:") and "o:" in stripped and "T:" in stripped:
            in_timeline = True
        if in_timeline:
            timeline_lines.append(line)
        else:
            header_lines.append(line)

    _parse_header(plf, header_lines)
    _parse_timeline(plf, timeline_lines)

    return plf


def _parse_header(plf: PLFFile, lines: list[str]):
    section = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("PLF1.0"):
            _parse_master_header(plf, stripped)
        elif stripped.startswith("ctx:"):
            plf.ctx = stripped[4:].strip().strip('"')
        elif stripped == "CAST:":
            section = "cast"
        elif stripped == "SCENES:":
            section = "scenes"
        elif stripped == "CLIPS:":
            section = "clips"
        elif section == "cast":
            member = _parse_cast_line(stripped)
            if member:
                plf.cast.append(member)
        elif section == "scenes":
            scene = _parse_scene_line(stripped)
            if scene:
                plf.scenes.append(scene)
        elif section == "clips":
            clip = _parse_clip_line(stripped)
            if clip:
                plf.clips.append(clip)


def _parse_master_header(plf: PLFFile, line: str):
    line = line[len("PLF1.0"):].strip()
    parts = line.split()
    for part in parts:
        if ":" not in part:
            continue
        key, _, value = part.partition(":")
        value = value.strip('"')
        if key == "proj":
            plf.proj = value
        elif key == "fps":
            plf.fps = int(value)
        elif key == "ar":
            plf.ar = value
        elif key == "dur":
            plf.dur = float(value)
        elif key == "src":
            plf.src = value
        elif key == "ref":
            plf.ref = value


def _parse_cast_line(line: str) -> PLFCastMember | None:
    parts = _FIELD_SEP.split(line)
    if len(parts) < 3:
        return None
    fields = _parse_kv_fields(parts)
    return PLFCastMember(
        id=parts[0],
        nombre=fields.get("nombre", ""),
        desc=fields.get("desc", ""),
    )


def _parse_scene_line(line: str) -> PLFScene | None:
    parts = _FIELD_SEP.split(line)
    if len(parts) < 4:
        return None
    fields = _parse_kv_fields(parts)
    return PLFScene(
        id=parts[0],
        loc=fields.get("loc", ""),
        time=fields.get("time", ""),
        act=int(fields.get("act", 0)),
        desc=fields.get("desc", ""),
    )


def _parse_clip_line(line: str) -> PLFClip | None:
    parts = _FIELD_SEP.split(line)
    if len(parts) < 3:
        return None
    fields = _parse_kv_fields(parts)
    return PLFClip(
        id=parts[0],
        file=fields.get("file", ""),
        tc=fields.get("tc", ""),
    )


def _parse_timeline(plf: PLFFile, lines: list[str]):
    for line in lines:
        stripped = line.rstrip()
        if not stripped:
            continue
        try:
            parsed = _parse_raw_line(stripped)
            entry = PLFEntry(
                i=parsed["i"],
                o=parsed["o"],
                track=parsed["track"],
                fields=parsed["fields"],
                _raw_line=stripped,
            )
            plf.timeline.append(entry)
        except (ValueError, IndexError) as e:
            raise ValueError(f"Error parsing timeline line: {stripped}") from e
