"""CLI wrapper for the FilmCraft bridge (PLAN.md Fase FC-A).

    python -m plf.bridge load    edit.plf  -o out.fcproj   # command rebuild (F2)
    python -m plf.bridge native  edit.plf  -o out.fcproj   # one-session OTIO import
    python -m plf.bridge sync    out.fcproj [-o out.plf]   # sequence.inspect -> PLF
    python -m plf.bridge diff    edit.plf  out.fcproj      # dirty flags (§3.4)
    python -m plf.bridge generate out.fcproj [--context c.json] [--skip-existing]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .. import parse
from ..writer import write
from .bridge import load_plf_into_filmcraft
from .dirty import diff_plf
from .generate import DEFAULT_PIPELINE_URL, generate_plfs
from .native import load_plf_native
from .reverse import sync_project


def _load_plf(path: str):
    return parse(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m plf.bridge",
                                 description="PLF <-> FilmCraft bridge")
    ap.add_argument("--cli", default=None, help="path to filmcraft-cli")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_load = sub.add_parser("load", help="rebuild the PLF with timeline.* commands")
    p_load.add_argument("plf")
    p_load.add_argument("-o", "--out", required=True)

    p_nat = sub.add_parser("native", help="PLF -> enriched OTIO -> one file.import")
    p_nat.add_argument("plf")
    p_nat.add_argument("-o", "--out", required=True)
    p_nat.add_argument("--base-dir", default=None,
                       help="resolve relative CLIPS file: names against this dir")

    p_sync = sub.add_parser("sync", help="sequence.inspect -> PLF")
    p_sync.add_argument("project")
    p_sync.add_argument("-o", "--out", default=None)

    p_diff = sub.add_parser("diff", help="dirty flags between original PLF and project (§3.4)")
    p_diff.add_argument("plf")
    p_diff.add_argument("project")

    p_gen = sub.add_parser("generate", help="run the pipeline over the project's clips")
    p_gen.add_argument("project")
    p_gen.add_argument("--context", default=None, help="context.json for every clip")
    p_gen.add_argument("--pipeline-url", default=DEFAULT_PIPELINE_URL)
    p_gen.add_argument("--skip-existing", action="store_true")
    p_gen.add_argument("--dry-run", action="store_true", help="list the videos, call nothing")

    args = ap.parse_args(argv)

    if args.cmd == "load":
        report = load_plf_into_filmcraft(_load_plf(args.plf), args.out,
                                         **({"cli_path": args.cli} if args.cli else {}))
        print(f"{report.project}: {report.placed_shots} shots placed, "
              f"{report.added_markers} markers, media {report.imported_files}")
        return 0

    if args.cmd == "native":
        report = load_plf_native(_load_plf(args.plf), args.out,
                                 cli_path=args.cli, base_dir=args.base_dir)
        print(f"{report.project}: OTIO {report.otio_path}")
        print(f"  shots {report.placed_shots}/{report.expected_shots}, "
              f"markers {report.added_markers}/{report.expected_markers}, "
              f"captions {'imported' if report.captions_imported else 'no'}")
        for w in report.warnings:
            print(f"  warning: {w}")
        print(f"  verified: {'PASS' if report.verified else 'FAIL'}")
        return 0 if report.verified else 2

    if args.cmd == "sync":
        _, text = sync_project(args.project, cli_path=args.cli)
        out = args.out or str(Path(args.project).with_suffix(".plf"))
        Path(out).write_text(text, encoding="utf-8")
        print(f"wrote {out}")
        return 0

    if args.cmd == "diff":
        original = _load_plf(args.plf)
        synced, _ = sync_project(args.project, cli_path=args.cli)
        report = diff_plf(original, synced)
        if report.clean:
            print("clean — no differences")
            return 0
        for seg in report.segments:
            flag = "REGENERATE" if seg.regenerate else "direct-write"
            print(f"[{seg.kind:10s}] {flag:13s} {seg.track} @{seg.i:.2f}-{seg.o:.2f}  {seg.reason}")
        print(f"\n{len(report.structural)} structural (regenerate on save), "
              f"{len(report.metadata)} metadata (direct write)")
        return 3

    if args.cmd == "generate":
        if args.dry_run:
            from .fcproj import load_fcproj, project_video_paths

            for v in project_video_paths(load_fcproj(args.project)):
                print(v)
            return 0
        context = json.loads(Path(args.context).read_text(encoding="utf-8")) if args.context else {}
        results = generate_plfs(
            args.project, context=context, pipeline_url=args.pipeline_url,
            skip_existing=args.skip_existing,
        )
        failed = 0
        for r in results:
            print(f"[{r['state']:8s}] {Path(r['video']).name}"
                  + (f" -> {Path(r['out']).name}" if r["state"] == "done" else "")
                  + (f"  {r['error']}" if r.get("error") else ""))
            failed += r["state"] == "error"
        print(f"\n{len(results)} video(s), {failed} failed")
        return 2 if failed else 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
