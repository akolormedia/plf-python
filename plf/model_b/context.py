from ..vector.searcher import search, format_context


def build_context(plf, query: str, table=None) -> str:
    header = _format_header(plf)

    if plf.dur < 1200:
        return header + "\n\n" + _format_timeline(plf)

    if table is None:
        return header + "\n\n" + _format_timeline(plf)

    results = search(query, table, top_k=10)
    segments_text = format_context(results, context_buffer=30.0)

    if not segments_text:
        return header + "\n\n" + _format_timeline(plf)

    return header + "\n\n" + segments_text


def _format_header(plf) -> str:
    header = (
        f"PLF1.0 proj:{plf.proj}  fps:{plf.fps}  "
        f"ar:{plf.ar}  dur:{plf.dur:.2f}  src:{plf.src}"
    )
    if plf.ref:
        header += f"  ref:{plf.ref}"
    if plf.ctx:
        header += f'\nctx:"{plf.ctx}"'

    if plf.cast:
        header += "\n\nCAST:"
        for c in plf.cast:
            header += f"\n  {c.id}  nombre:{c.nombre}  desc:{c.desc}"

    if plf.scenes:
        header += "\n\nSCENES:"
        for s in plf.scenes:
            header += (
                f'\n  {s.id}  loc:{s.loc}  time:{s.time}  '
                f'act:{s.act}  desc:"{s.desc}"'
            )

    return header


def _format_timeline(plf) -> str:
    lines = []
    for entry in plf.timeline:
        if entry._raw_line:
            lines.append(entry._raw_line)
    return "\n".join(lines)
