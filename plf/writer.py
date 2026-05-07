from .schema import PLFFile, PLFEntry


def write(plf: PLFFile) -> str:
    lines = []

    _write_header(plf, lines)
    lines.append("")

    for entry in plf.timeline:
        if entry._raw_line:
            lines.append(entry._raw_line)
        else:
            lines.append(_format_entry(entry))

    return "\n".join(lines)


def _write_header(plf: PLFFile, lines: list[str]):
    header = f"PLF1.0 proj:{plf.proj}  fps:{plf.fps}  ar:{plf.ar}  dur:{plf.dur:.2f}  src:{plf.src}"
    if plf.ref:
        header += f"  ref:{plf.ref}"
    lines.append(header)

    if plf.ctx:
        lines.append(f'ctx:"{plf.ctx}"')

    if plf.cast:
        lines.append("")
        lines.append("CAST:")
        for c in plf.cast:
            lines.append(f"  {c.id}  nombre:{c.nombre}  desc:{c.desc}")

    if plf.scenes:
        lines.append("")
        lines.append("SCENES:")
        for s in plf.scenes:
            lines.append(
                f'  {s.id}  loc:{s.loc}  time:{s.time}  act:{s.act}  desc:"{s.desc}"'
            )

    if plf.clips:
        lines.append("")
        lines.append("CLIPS:")
        for c in plf.clips:
            lines.append(f"  {c.id}  file:{c.file}  tc:{c.tc}")


def _format_entry(entry: PLFEntry) -> str:
    parts = [
        f"i:{entry.i:.2f}",
        f"o:{entry.o:.2f}",
        f"T:{entry.track}",
    ]

    for key, value in entry.fields.items():
        if key.startswith("_"):
            if key == "_word":
                parts.append(f'"{value}"')
            elif key == "_text":
                parts.append(f'"{value}"')
        elif " " in str(value):
            parts.append(f'{key}:"{value}"')
        else:
            parts.append(f"{key}:{value}")

    return "    ".join(parts)
