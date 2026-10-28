"""Command line: python -m atlas_bg input... -o out_dir [options]"""
from __future__ import annotations

import argparse
import signal
import sys
import threading
from pathlib import Path

from . import __version__
from .batch import collect_files, run_batch
from .engine import PRESETS, Options, Remover, matting_available, parse_color
from .models import DEFAULT_MODEL, MODELS, ModelError, find_model, ram_warning


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="atlas-bg", description="Offline batch background remover")
    ap.add_argument("inputs", nargs="*", help="image files and/or folders")
    ap.add_argument("-o", "--out", default="no-bg", help="output folder (default ./no-bg)")
    ap.add_argument("-m", "--model", default=DEFAULT_MODEL, choices=list(MODELS))
    ap.add_argument("-f", "--format", default="png", choices=["png", "jpg", "webp"])
    ap.add_argument("--bg", default=None, help="background colour: white, #RRGGBB (default transparent)")
    ap.add_argument("--crop", action="store_true", help="crop to the subject")
    ap.add_argument("--margin", type=float, default=0.04, help="crop margin as a fraction")
    ap.add_argument("--preset", default="none", choices=list(PRESETS))
    ap.add_argument("--no-refine", action="store_true", help="disable edge refinement")
    ap.add_argument("--no-decontaminate", action="store_true", help="keep original edge colours")
    ap.add_argument("--matting", action="store_true", help="alpha matting (slow, needs pymatting)")
    ap.add_argument("--no-recursive", action="store_true")
    ap.add_argument("--list-models", action="store_true")
    ap.add_argument("--version", action="version", version=__version__)
    a = ap.parse_args(argv)

    if a.list_models:
        for k, s in MODELS.items():
            have = find_model(k)
            print(f"{k:18} {s.size_mb:4} MB  {s.license:10.10}  {'installed' if have else 'not downloaded'}  {s.note}")
        print(f"alpha matting available: {matting_available()}")
        return 0
    if not a.inputs:
        ap.error("no inputs")
    try:
        opts = Options(model=a.model, out_format=a.format, bg_color=parse_color(a.bg), crop=a.crop,
                       crop_margin=a.margin, preset=a.preset, refine=not a.no_refine,
                       decontaminate=not a.no_decontaminate, matting=a.matting)
    except ValueError as e:
        ap.error(str(e))
    out = Path(a.out)
    files = collect_files(a.inputs, recursive=not a.no_recursive, skip_dir=out)
    if not files:
        print("No images found.", file=sys.stderr)
        return 2
    cancel = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: cancel.set())

    def mprog(done, total):
        if total:
            print(f"\rdownloading model {done * 100 // total}%", end="", file=sys.stderr)

    rw = ram_warning(a.model)
    if rw:
        print(f"warning: model '{a.model}' needs about {rw[0]} MB RAM, only {rw[1]} MB free; "
              "it may be very slow or crash. Try -m isnet-general-use.", file=sys.stderr)
    try:
        remover = Remover(a.model, progress=mprog, cancel=cancel)
    except ModelError as e:
        print(f"\nModel error [{e.code}]: {e}", file=sys.stderr)
        return 3

    def prog(i, n, r):
        status = f"ok -> {r.out.name}" if r.ok else f"FAILED [{r.error_code}] {r.error}"
        w = f" (warn: {','.join(r.warnings)})" if r.warnings else ""
        print(f"[{i}/{n}] {r.src.name}: {status}{w} {r.seconds:.2f}s")

    res = run_batch(files, out, opts, remover, prog, cancel)
    ok = sum(r.ok for r in res)
    print(f"done: {ok} ok, {len(res) - ok} failed, {len(files) - len(res)} skipped (cancelled)")
    return 0 if ok == len(files) else 1


if __name__ == "__main__":
    sys.exit(main())
